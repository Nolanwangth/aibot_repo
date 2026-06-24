"""Vision module — camera capture + Agnes AI Vision API image description."""
import base64
import os
import subprocess
import cv2
import requests
AGNES_VISION_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
AGNES_VISION_MODEL = "agnes-2.0-flash"
MAX_SIZE = 800          # max dimension for API, keeps payload under limit


def _get_api_key() -> str:
    """Load Agnes API key from env or .hermes/.env."""
    key = os.environ.get("AGNES_API_KEY", "")
    if key:
        return key
    env_file = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.startswith("AGNES_API_KEY"):
                    raw = line.split("=", 1)[1].strip()
                    if raw:
                        return raw
    raise RuntimeError("AGNES_API_KEY not found — set in ~/.hermes/.env")


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

    # Resize for API
    h, w = frame.shape[:2]
    scale = MAX_SIZE / max(h, w)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    b64 = base64.b64encode(buf).decode()

    return b64, photo_path


def describe(image_b64: str, query: str) -> str:
    """Send image + query to Agnes AI Vision API, return text description."""
    api_key = _get_api_key()

    payload = {
        "model": AGNES_VISION_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image_b64}},
            ],
        }],
    }

    for attempt in range(2):
        try:
            resp = requests.post(
                AGNES_VISION_URL,
                json=payload,
                headers={"Authorization": "Bearer " + api_key},
                timeout=60,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Agnes Vision error ({resp.status_code}): {resp.text[:200]}")
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"Agnes error: {data['error']}")
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            if attempt == 0:
                continue
        raise RuntimeError("Agnes 视觉请求超时，请重试")

    raise RuntimeError("Agnes 视觉请求超时")  # unreachable, satisfies type checker



def show_photo(path: str) -> None:
    """Open photo with system viewer so user can see what was captured."""
    import platform
    if platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    elif platform.system() == "Windows":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])
