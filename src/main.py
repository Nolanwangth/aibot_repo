"""Main orchestration — always-on VAD listening + vision + animated pixel-art face."""
import sys
import threading
import time
import re
import json
import traceback
from http.server import ThreadingHTTPServer

from .ear import listen_vad, transcribe
from .brain import chat_stream, generate_vision_query, chat_with_vision
from .brain import _save_turn as save_memory, MoodState
from . import memory_manager as mem
from .eye import capture, describe, show_photo
from .mouth import say_stream, stop_playback, is_playing
from .face import Face
from .config import PROACTIVE_ENABLED, PROACTIVE_IDLE_SECONDS, SPEECH_OUTPUT_ENABLED

_face = Face()
_mood = MoodState()
_listening = True
_running = True
_last_reply = ""  # last clean response, readable by web handler
_last_interaction_at = time.monotonic()
_busy_lock = threading.Lock()
_busy = False

PROACTIVE_VISION_PROMPT = (
    "看看我现在在干什么，描述我的状态、桌面或周围环境，"
    "判断我是在工作、发呆、离开，还是需要你提醒我一下。"
)
PROACTIVE_USER_TEXT = (
    "你已经安静了一分钟，主动看了一眼我在干什么。"
    "像真的陪在旁边一样自然说一句，不要说'根据画面描述'，不要太长。"
)

VISION_TRIGGERS = ["看看", "看", "穿", "拍", "照片", "摄像头", "镜头", "眼前",
                   "自拍", "帅", "美", "穿搭", "衣服", "打扮", "发型", "妆",
                   "这是什么", "那是", "这个", "那个", "面前", "周围", "桌上"]

# Sentence-splitting pattern for streaming TTS
_SENTENCE_SPLIT = re.compile(r'([。！？\n])')


def _is_vision_request(text: str) -> bool:
    return any(kw in text for kw in VISION_TRIGGERS)


def _touch_interaction() -> None:
    global _last_interaction_at
    _last_interaction_at = time.monotonic()


def _try_begin_task() -> bool:
    global _busy
    with _busy_lock:
        if _busy:
            return False
        _busy = True
        return True


def _end_task() -> None:
    global _busy
    with _busy_lock:
        _busy = False


def _speak_if_enabled(text: str) -> None:
    if not SPEECH_OUTPUT_ENABLED or not text.strip():
        return
    _face.set_state("speaking")
    say_stream(text)


def _run_chat_text(text: str) -> str:
    """Shared chat path for voice STT text and Web UI text."""
    global _last_reply
    mem.update_emotional_state_from_user(text)
    _face.set_state("thinking")
    sys.stdout.write("\n💬 小灵: ")
    sys.stdout.flush()

    buffer = ""
    full_reply = ""
    header_buffer = ""
    header_done = False
    mood_seen = False
    tts_buffer = ""

    for token in chat_stream(text):
        full_reply += token

        if not header_done:
            header_buffer += token
            if "\n" in header_buffer:
                first_line, rest = header_buffer.split("\n", 1)
                try:
                    data = json.loads(first_line.strip())
                    mood = data.get("mood", "")
                    if _mood.apply_mood(mood):
                        mood_seen = True
                        print(f"\n🎭 表情: {mood}")
                    buffer += rest.lstrip()
                    if rest:
                        sys.stdout.write(rest.lstrip())
                        sys.stdout.flush()
                except json.JSONDecodeError:
                    print(f"\n⚠️  首行非 JSON: {first_line[:50]}")
                    buffer += header_buffer
                    sys.stdout.write(header_buffer)
                    sys.stdout.flush()
                header_done = True
            elif len(header_buffer) > 120:
                buffer += header_buffer
                sys.stdout.write(header_buffer)
                sys.stdout.flush()
                header_done = True
            continue

        sys.stdout.write(token)
        sys.stdout.flush()
        buffer += token

        # Sentence splitting for streaming TTS
        parts = _SENTENCE_SPLIT.split(buffer)
        if len(parts) >= 3:
            sentence = parts[0] + parts[1]
            remaining = "".join(parts[2:])
            clean = _mood.parse_llm_output(sentence)
            if clean.strip():
                tts_buffer += clean
                if tts_buffer.count("。") + tts_buffer.count("！") + tts_buffer.count("？") >= 2 or len(tts_buffer) >= 40:
                    _speak_if_enabled(tts_buffer)
                    tts_buffer = ""
            buffer = remaining

    # Flush remaining buffer
    if not header_done and header_buffer.strip():
        buffer += header_buffer
        sys.stdout.write(header_buffer)
        sys.stdout.flush()

    if tts_buffer.strip():
        _speak_if_enabled(tts_buffer)
        tts_buffer = ""

    if buffer.strip():
        clean = _mood.parse_llm_output(buffer)
        if clean.strip():
            _speak_if_enabled(clean)

    print()

    clean_reply = _mood.parse_llm_output(full_reply)
    _last_reply = clean_reply
    save_memory(text, clean_reply)

    return clean_reply


def _handle_chat(text: str):
    if _is_vision_request(text):
        _handle_vision(text)
    else:
        _run_chat_text(text)


def _handle_web_chat(text: str) -> str:
    """Web chat uses the exact same model/terminal/TTS path as voice text."""
    if not _try_begin_task():
        return "我还在处理上一句话，等我一下。"
    try:
        _touch_interaction()
        clean_reply = _run_chat_text(text)
        _face.set_state("idle")
        return clean_reply
    finally:
        _touch_interaction()
        _end_task()


def _handle_vision(text: str):
    print("\n👁️  视觉模式启动...")
    print("🔍 分析意图中...")
    vision_query = generate_vision_query(text)
    print(f"   查询: {vision_query}")

    print("📸 拍照中...")
    image_b64, photo_path = capture()
    show_photo(photo_path)
    print(f"   ✓ 已拍照 (原图: {photo_path})")

    print("🖼️  图像理解中...")
    description = describe(image_b64, vision_query)
    print(f"   画面: {description[:80]}...")

    _face.set_state("thinking")
    reply = chat_with_vision(text, description)
    clean = _mood.parse_llm_output(reply)
    print(f"💬 小灵: {clean}")

    if not clean.strip():
        return

    _speak_if_enabled(clean)

    save_memory(text, clean)
    global _last_reply
    _last_reply = clean


def _handle_proactive_vision() -> None:
    """Proactively look through the camera after a quiet period."""
    global _last_reply
    if not _try_begin_task():
        return
    try:
        print("\n👁️  小灵安静看了一眼你在干什么...")
        _face.set_state("thinking")

        image_b64, photo_path = capture()
        print(f"   ✓ 已主动观察 (原图: {photo_path})")

        vision_query = generate_vision_query(PROACTIVE_VISION_PROMPT)
        print(f"   查询: {vision_query}")
        description = describe(image_b64, vision_query)
        print(f"   画面: {description[:80]}...")

        reply = chat_with_vision(PROACTIVE_USER_TEXT, description)
        clean = _mood.parse_llm_output(reply)
        if not clean.strip():
            return

        print(f"💬 小灵: {clean}")
        _speak_if_enabled(clean)
        save_memory("小灵主动观察用户状态", clean)
        _last_reply = clean
    except Exception as exc:
        print(f"👁️  主动观察失败，已跳过: {exc}")
        traceback.print_exc()
    finally:
        _touch_interaction()
        _end_task()


def _process(text: str) -> None:
    """Route text (from mic or keyboard) to chat or vision."""
    if not _try_begin_task():
        print("⏳ 小灵还在处理上一件事，先跳过这次输入")
        return
    try:
        _touch_interaction()
        if _is_vision_request(text):
            _handle_vision(text)
        else:
            _handle_chat(text)
    except Exception as e:
        print(f"❌ 出错了: {e}")
        traceback.print_exc()
    finally:
        _touch_interaction()
        _end_task()


def _listen_loop():
    while _running:
        if not _listening:
            _face.set_state("idle")
            time.sleep(0.1)
            continue

        _face.set_state("idle")
        audio = listen_vad()
        if audio is None:
            continue

        with _busy_lock:
            busy = _busy
        if busy:
            continue

        # Voice detected while TTS playing → interrupt
        if is_playing():
            stop_playback()
            print("\n⏸️  语音打断")

        _face.set_state("listening")
        print("📝 转写中...")
        text = transcribe(audio)
        if not text.strip():
            print("😶 没听清...")
            continue

        _touch_interaction()
        print(f"📝 你说: {text}")
        _process(text)


def _proactive_loop():
    while _running:
        time.sleep(5)
        if not _running or not _listening:
            continue
        with _busy_lock:
            busy = _busy
        if busy or is_playing():
            continue
        if not PROACTIVE_ENABLED:
            continue
        idle_for = time.monotonic() - _last_interaction_at
        if idle_for >= PROACTIVE_IDLE_SECONDS:
            _handle_proactive_vision()


def main():
    _face.setup()
    _mood.bind_face(_face)
    _touch_interaction()

    def toggle_listening(_event=None):
        global _listening
        _listening = not _listening
        if _listening:
            print("🎙️  语音监听：开")
        else:
            stop_playback()
            _face.set_state("idle")
            print("🔇 语音监听：关（按空格开启）")

    def quit_app(_event=None):
        global _running, _listening
        _running = False
        _listening = False
        stop_playback()
        print("\n👋 再见~")
        _face._root.after(100, _face._root.quit)

    _face._root.bind("<space>", toggle_listening)
    _face._root.bind("<Escape>", quit_app)

    threading.Thread(target=_listen_loop, daemon=True).start()
    threading.Thread(target=_proactive_loop, daemon=True).start()

    # Auto-start web console in background
    try:
        from .context_ui import ContextHandler
        from . import context_ui as _cui
        _cui.EMBEDDED_MODE = True  # enable TTS/face in chat handler
        _cui.EMBEDDED_CHAT_HANDLER = _handle_web_chat
        _web = ThreadingHTTPServer(("127.0.0.1", 8765), ContextHandler)
        threading.Thread(target=_web.serve_forever, daemon=True).start()
        print("🌐 Web 管理台: http://127.0.0.1:8765  （左侧「对话」可打字聊天）")
    except Exception as e:
        print(f"⚠️  Web 管理台启动失败: {e}")

    print("=" * 50)
    print("🤖 小灵 — AI 桌面陪伴精灵 v0.4.0")
    print("=" * 50)
    print("直接说话即可，说完自动识别")
    print("小灵说话时直接开口就能打断她")
    print("说出「看看」触发视觉模式")
    print("按 [空格] 暂停/恢复监听")
    print("按 [ESC] 退出\n")

    _face.run()


if __name__ == "__main__":
    main()
