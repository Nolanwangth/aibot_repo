"""Main orchestration — always-on VAD listening + vision + animated face."""
import sys
import threading
import time

from .ear import listen_vad, transcribe
from .brain import chat_stream, generate_vision_query, chat_with_vision
from .brain import _save_turn as save_memory
from .eye import capture, describe, show_photo
from .mouth import say, stop_playback, is_playing
from .face import Face

_face = Face()
_listening = True
_running = True

VISION_TRIGGERS = ["看看", "看", "穿", "拍", "照片", "摄像头", "镜头", "眼前",
                   "自拍", "帅", "美", "穿搭", "衣服", "打扮", "发型", "妆",
                   "这是什么", "那是", "这个", "那个", "面前", "周围", "桌上"]


def _is_vision_request(text: str) -> bool:
    return any(kw in text for kw in VISION_TRIGGERS)


def _handle_chat(text: str):
    _face.set_state("thinking")
    sys.stdout.write("\n💬 小灵: ")
    sys.stdout.flush()

    chunks = []
    for token in chat_stream(text):
        sys.stdout.write(token)
        sys.stdout.flush()
        chunks.append(token)

    reply = "".join(chunks)
    print()
    save_memory(text, reply)

    if not reply.strip():
        return

    _face.set_state("speaking")
    say(reply)  # non-blocking, runs in background thread


def _handle_vision(text: str):
    print("👁️  视觉模式启动...")
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
    print(f"💬 小灵: {reply}")

    if not reply.strip():
        return

    _face.set_state("speaking")
    say(reply)


def _process(text: str) -> None:
    """Route text (from mic or keyboard) to chat or vision."""
    try:
        if _is_vision_request(text):
            _handle_vision(text)
        else:
            _handle_chat(text)
    except Exception as e:
        print(f"❌ 出错了: {e}")


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
    print("🤖 小灵 — AI 桌面陪伴精灵")
    print("=" * 50)
    print("直接说话即可，说完自动识别")
    print("小灵说话时直接开口就能打断她")
    print("说出「看看」触发视觉模式")
    print("按 [空格] 暂停/恢复监听")
    print("按 [ESC] 退出\n")

    _face.run()


if __name__ == "__main__":
    main()
