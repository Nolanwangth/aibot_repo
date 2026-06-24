"""
TTS mouth — streaming-friendly queue-based edge-tts synthesis + pygame playback.
Supports incremental sentence feeding, non-blocking, interruptible.
"""
import asyncio
import queue
import re
import threading
import tempfile
import os
import struct
import edge_tts
import pygame
from .config import TTS_VOICE

_stop_flag = False
_sentence_queue = queue.Queue()
_worker_running = False
_worker_thread = None
_current_speaker = None  # tracks which "speaker" is talking (for future multi-voice)


def _ensure_mixer():
    if not pygame.mixer.get_init():
        pygame.mixer.init()


def _is_valid_mp3(data: bytes) -> bool:
    """Quick check for valid MP3: has ID3 header or MPEG frame sync."""
    if len(data) < 100:
        return False
    # ID3v2 header
    if data[:3] == b"ID3":
        return True
    # MPEG frame sync (11 bits set)
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return True
    return False


def stop_playback():
    """Interrupt current playback and clear pending sentences."""
    global _stop_flag
    _stop_flag = True
    if pygame.mixer.get_init():
        pygame.mixer.music.stop()
    # Drain queue
    while not _sentence_queue.empty():
        try:
            _sentence_queue.get_nowait()
        except queue.Empty:
            break


def is_playing() -> bool:
    return pygame.mixer.get_init() and pygame.mixer.music.get_busy()


async def _synthesize(text: str, voice: str = TTS_VOICE) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        await communicate.save(tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def speak(text: str) -> bytes | None:
    """Synthesize text to MP3 bytes. Returns None on failure."""
    # Strip action descriptions in parentheses
    clean = re.sub(r"[（(][^）)]*[）)]", "", text)
    # Collapse whitespace
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    # Remove emoji / non-speech characters
    clean = re.sub(r"[⭐✨🌟💫🔥🎉😊😂🤔😮😢😴💪❤️🫶👍🙏]", "", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip()

    if not clean or len(clean) < 2:
        return None

    try:
        audio = asyncio.run(_synthesize(clean))
        if not _is_valid_mp3(audio):
            print(f"🔊 TTS 生成的 MP3 无效，跳过: \"{clean[:40]}...\"")
            return None
        return audio
    except Exception as e:
        print(f"🔊 TTS 合成失败: {e}")
        return None


def say(text: str) -> None:
    """Queue text for TTS. Returns immediately. Background worker plays them sequentially."""
    if not text.strip():
        return
    _sentence_queue.put(text)
    _start_worker()


def say_stream(sentence: str) -> None:
    """Feed one sentence to the streaming TTS queue."""
    say(sentence)


def _start_worker():
    global _worker_running, _worker_thread
    if _worker_running:
        return
    _worker_running = True
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()


def _worker_loop():
    global _worker_running, _stop_flag
    _ensure_mixer()

    while True:
        try:
            text = _sentence_queue.get(timeout=0.5)
        except queue.Empty:
            if _stop_flag and _sentence_queue.empty():
                break
            continue

        if _stop_flag:
            continue

        # Synthesize (with retry)
        audio = None
        for attempt in range(2):
            audio = speak(text)
            if audio is not None:
                break

        if audio is None:
            # Silent skip — don't crash
            continue

        if _stop_flag:
            continue

        # Play with crash protection
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio)
            tmp_path = tmp.name
        try:
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if _stop_flag:
                    pygame.mixer.music.stop()
                    break
                pygame.time.Clock().tick(10)
        except pygame.error as e:
            print(f"🔊 播放失败 (corrupt mp3, 跳过): {e}")
        except Exception as e:
            print(f"🔊 播放异常: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    _worker_running = False
