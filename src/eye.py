"""Vision module — camera capture + Ollama local VLM image description."""
import base64
import os
import subprocess
import cv2
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MAX_SIZE = 448  # max dimension for Ollama, keeps memory low


def capture() -> tuple[str, str]:
    """Capture from default camera. Returns (base64_small, filepath_original)."""
    import platform
    backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
    cap = cv2.VideoCapture(0, backend)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("无法打开摄像头 — 请确认终端有摄像头权限")
    cap.read()  # warmup
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError("摄像头读取失败")

    # Save original to data/photos/
    photo_dir = os.path.join(os.path.dirname(__file__), "..", "data", "photos")
    os.makedirs(photo_dir, exist_ok=True)
    photo_path = os.path.join(photo_dir, "capture.jpg")
    cv2.imwrite(photo_path, frame)

    # Resize for Ollama (smaller = faster, less memory)
    h, w = frame.shape[:2]
    scale = MAX_SIZE / max(h, w)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    b64 = base64.b64encode(buf).decode()

    return b64, photo_path


def describe(image_b64: str, query: str, model: str = "qwen3.5:2b") -> str:
    """Send image + query to local Ollama VLM, return text description.

    Note: qwen3.5-2b always generates internal thinking tokens before content.
    The 'thinking' field is discarded — only 'content' is returned.
    Image is pre-resized to MAX_SIZE to keep memory under 4GB GPU limit.
    """
    body = {
        "model": model,
        "stream": False,
        "keep_alive": "10m",
        "messages": [
            {"role": "user", "content": query, "images": [image_b64]}
        ],
    }
    for attempt in range(2):
        try:
            resp = requests.post(OLLAMA_URL, json=body, timeout=300)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama 请求失败 ({resp.status_code}): {resp.text[:200]}")
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"Ollama 错误: {data['error']}")
            return data["message"]["content"]
        except requests.exceptions.Timeout:
            if attempt == 0:
                # Model may have crashed — kill and let ollama reload on retry
                requests.post("http://localhost:11434/api/generate",
                              json={"model": model, "keep_alive": "0s"}, timeout=5)
                continue
            raise RuntimeError("Ollama 视觉请求超时，请重试")


def show_photo(path: str) -> None:
    """Open photo with system viewer so user can see what was captured."""
    import platform
    if platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    elif platform.system() == "Windows":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
