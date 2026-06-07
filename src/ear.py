"""Audio input — microphone recording + speech-to-text via faster-whisper."""
import threading
import sounddevice as sd
import numpy as np

from .config import AUDIO_SAMPLE_RATE, AUDIO_CHANNELS

_whisper_model = None

# ── VAD tuning ───────────────────────────────────────────────────
CHUNK_MS = 30                   # frame size for energy detection
SILENCE_FRAMES = 40             # ~1.2s of silence to end speech
SPEECH_FRAMES = 3               # consecutive energy frames to start speech
MAX_SPEECH_SECS = 30            # hard cap on recording length
THRESHOLD = 1600                # int16 RMS — must exceed this to count as speech


def _get_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        from .config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
    return _whisper_model


def record(duration: float = 5, sample_rate: int = AUDIO_SAMPLE_RATE) -> np.ndarray:
    """Record audio for `duration` seconds. Returns float32 normalized to [-1, 1]."""
    print(f"🎤 聆听中... ({duration}秒)")
    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=AUDIO_CHANNELS,
        dtype="int16",
    )
    sd.wait()
    return audio.flatten().astype(np.float32) / 32768.0


def transcribe(audio: np.ndarray, sample_rate: int = AUDIO_SAMPLE_RATE) -> str:
    """Transcribe audio to simplified Chinese text using faster-whisper.

    Uses built-in Silero VAD to skip silence before decoding — cleaner input
    means faster inference and fewer hallucinated words.
    """
    from opencc import OpenCC
    cc = OpenCC("t2s")
    model = _get_model()
    segments, _info = model.transcribe(
        audio,
        language="zh",
        beam_size=3,
        vad_filter=True,
        vad_parameters={"threshold": 0.4, "min_speech_duration_ms": 300},
    )
    text = " ".join(seg.text.strip() for seg in segments)
    return cc.convert(text)


# ── Always-on VAD listening ──────────────────────────────────────

def listen_vad(sample_rate: int = AUDIO_SAMPLE_RATE) -> np.ndarray | None:
    """Monitor mic until speech detected then silence. Returns speech audio or None.

    Fixed-threshold RMS energy detection. Streams audio in 30ms chunks.
    Speech begins after SPEECH_FRAMES consecutive loud frames.
    Speech ends after SILENCE_FRAMES consecutive quiet frames.
    """
    chunk_size = sample_rate * CHUNK_MS // 1000
    max_frames = MAX_SPEECH_SECS * 1000 // CHUNK_MS

    frames = []            # collected audio during speech
    state = "waiting"      # waiting → speech → done
    silence_count = 0
    energy_count = 0
    energy_buffer = []     # pre-trigger frames for padding
    frame_idx = 0

    result_audio = None
    event = threading.Event()

    def callback(indata, _frames, _time, _status):
        nonlocal state, silence_count, energy_count, result_audio, frame_idx
        if state == "done":
            return

        chunk = indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        is_loud = rms > THRESHOLD

        frame_idx += 1

        if state == "waiting":
            energy_buffer.append(chunk)
            if len(energy_buffer) > SPEECH_FRAMES:
                energy_buffer.pop(0)  # rolling window
            if is_loud:
                energy_count += 1
                if energy_count >= SPEECH_FRAMES:
                    state = "speech"
                    frames.extend(energy_buffer)
                    energy_buffer.clear()
                    silence_count = 0
            else:
                energy_count = 0

        elif state == "speech":
            frames.append(chunk)
            if is_loud:
                silence_count = 0
            else:
                silence_count += 1
                if silence_count >= SILENCE_FRAMES:
                    state = "done"
                    result_audio = np.concatenate(frames)
                    event.set()

        if frame_idx >= max_frames and state == "speech":
            state = "done"
            result_audio = np.concatenate(frames) if frames else None
            event.set()

    with sd.InputStream(
        samplerate=sample_rate,
        channels=AUDIO_CHANNELS,
        dtype="int16",
        blocksize=chunk_size,
        callback=callback,
    ):
        event.wait(timeout=MAX_SPEECH_SECS + 5)

    if result_audio is None:
        return None
    return result_audio.flatten().astype(np.float32) / 32768.0
