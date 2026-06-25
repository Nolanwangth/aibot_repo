"""Main orchestration — always-on VAD listening + vision + animated pixel-art face."""
import sys
import threading
import time
import re
import json
import traceback

from .ear import listen_vad, transcribe
from .brain import chat_stream, generate_vision_query, chat_with_vision
from .brain import _save_turn as save_memory, MoodEngine
from .eye import capture, describe, show_photo
from .mouth import say_stream, stop_playback, is_playing
from .face import Face

_face = Face()
_mood = MoodEngine()
_listening = True
_running = True

VISION_TRIGGERS = ["看看", "看", "穿", "拍", "照片", "摄像头", "镜头", "眼前",
                   "自拍", "帅", "美", "穿搭", "衣服", "打扮", "发型", "妆",
                   "这是什么", "那是", "这个", "那个", "面前", "周围", "桌上"]

# Sentence-splitting pattern for streaming TTS
_SENTENCE_SPLIT = re.compile(r'([。！？\n])')


def _is_vision_request(text: str) -> bool:
    return any(kw in text for kw in VISION_TRIGGERS)


def _stream_chat_to_tts(text: str):
    """Accumulate LLM tokens, split at sentence boundaries,
    clean mood tags, and feed sentences to streaming TTS."""
    _face.set_state("thinking", mood="thinking")
    sys.stdout.write("\n💬 小灵: ")
    sys.stdout.flush()

    buffer = ""
    full_reply = ""
    header_buffer = ""
    header_done = False
    mood_seen = False
    tts_buffer = ""   # accumulates sentences before sending to TTS

    # Set face to thinking initially
    _face.set_state("thinking")

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
                    clean = _mood.parse_llm_output(header_buffer)
                    buffer += clean
                    sys.stdout.write(clean)
                    sys.stdout.flush()
                header_done = True
            elif len(header_buffer) > 120:
                clean = _mood.parse_llm_output(header_buffer)
                buffer += clean
                sys.stdout.write(clean)
                sys.stdout.flush()
                header_done = True
            continue

        sys.stdout.write(token)
        sys.stdout.flush()
        buffer += token

        # Check for sentence boundary
        parts = _SENTENCE_SPLIT.split(buffer)
        if len(parts) >= 3:
            sentence = parts[0] + parts[1]
            remaining = "".join(parts[2:])
            clean = _mood.parse_llm_output(sentence)
            if clean.strip():
                # Buffer until we have enough text (2+ sentences or 40+ chars)
                tts_buffer += clean
                if tts_buffer.count("。") + tts_buffer.count("！") + tts_buffer.count("？") >= 2 or len(tts_buffer) >= 40:
                    _face.set_state("speaking")
                    say_stream(tts_buffer)
                    tts_buffer = ""
            buffer = remaining

    # Flush remaining buffer
    if not header_done and header_buffer.strip():
        clean = _mood.parse_llm_output(header_buffer)
        buffer += clean
        sys.stdout.write(clean)
        sys.stdout.flush()

    # Flush accumulated TTS buffer
    if tts_buffer.strip():
        _face.set_state("speaking")
        say_stream(tts_buffer)
        tts_buffer = ""

    if buffer.strip():
        clean = _mood.parse_llm_output(buffer)
        if clean.strip():
            _face.set_state("speaking")
            say_stream(clean)

    print()

    # Save full turn (without mood tags) to memory
    clean_reply = _mood.parse_llm_output(full_reply)
    save_memory(text, clean_reply)

    # Fallback: infer mood from content if no mood tag was found
    if not mood_seen:
        # First try user's input tone
        hint = _mood.hint_from_user(text)
        if hint:
            _mood.apply_mood(hint)
            print(f"🎭 表情: {hint}（关键词推断）")
        else:
            # Then try LLM reply content
            hint = _mood.hint_from_reply(clean_reply)
            if hint:
                _mood.apply_mood(hint)
                print(f"🎭 表情: {hint}（内容推断）")


def _handle_chat(text: str):
    _stream_chat_to_tts(text)


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

    _face.set_state("thinking", mood="thinking")
    reply = chat_with_vision(text, description)
    clean = _mood.parse_llm_output(reply)
    print(f"💬 小灵: {clean}")

    if not clean.strip():
        return

    _face.set_state("speaking")
    say_stream(clean)

    save_memory(text, clean)


def _process(text: str) -> None:
    """Route text (from mic or keyboard) to chat or vision."""
    try:
        if _is_vision_request(text):
            _handle_vision(text)
        else:
            _handle_chat(text)
    except Exception as e:
        print(f"❌ 出错了: {e}")
        traceback.print_exc()


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

        print(f"📝 你说: {text}")
        _process(text)


def main():
    _face.setup()
    _mood.bind_face(_face)

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
