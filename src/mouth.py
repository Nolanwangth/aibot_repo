"""TTS mouth — edge-tts synthesis + pygame audio playback."""
import asyncio
import re
import threading
import tempfile
import os
import edge_tts
import pygame
from .config import TTS_VOICE

_stop_flag = False


def _ensure_mixer():
    if not pygame.mixer.get_init():
        pygame.mixer.init()


def stop_playback():
    global _stop_flag
    _stop_flag = True
    if pygame.mixer.get_init():
        pygame.mixer.music.stop()


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


def speak(text: str) -> bytes:
    # Strip parenthetical content before TTS — show, don't read
    clean = re.sub(r"[（(][^）)]*[）)]", "", text)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    return asyncio.run(_synthesize(clean))


def say(text: str) -> None:
    """Synthesize + play in background thread. Returns immediately."""
    if not text.strip():
        return
    global _stop_flag
    _stop_flag = False
    print("🔊 播放中...")
    threading.Thread(target=_speak_and_play, args=(text,), daemon=True).start()


def _speak_and_play(text: str):
    if _stop_flag:
        return
    audio = speak(text)
    if _stop_flag:
        return
    _ensure_mixer()
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
    finally:
        os.unlink(tmp_path)
