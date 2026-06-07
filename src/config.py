"""Centralized configuration — loads from data/config/, falls back to defaults."""
import json
import os

# ── Paths ────────────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)
_CONFIG_DIR = os.path.join(_BASE, "..", "data", "config")
_MEMORY_DIR = os.path.join(_BASE, "..", "data", "memory")

# ── DeepSeek API Key ─────────────────────────────────────────────
def _load_deepseek_key() -> str:
    env_key = os.getenv("DEEPSEEK_API_KEY")
    if env_key:
        return env_key
    raise RuntimeError("DeepSeek API Key not found. Set DEEPSEEK_API_KEY env var")

DEEPSEEK_API_KEY = _load_deepseek_key()
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ── Settings (editable via data/config/settings.json) ────────────
def _load_settings() -> dict:
    path = os.path.join(_CONFIG_DIR, "settings.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

_settings = _load_settings()

DEEPSEEK_MODEL = _settings.get("model", "deepseek-chat")
TTS_VOICE = _settings.get("tts_voice", "zh-CN-XiaoxiaoNeural")

# ── Soul (editable via data/config/soul.txt) ─────────────────────
_DEFAULT_SOUL = """你是「小灵」，一个住在电脑里的智能助手。你细心、体贴、会关心人的感受。

性格特点：
- 友好热情，像朋友一样自然交流
- 善于倾听，能敏锐感知对方的情绪变化
- 幽默风趣，偶尔开个无伤大雅的玩笑
- 乐于助人，尽力提供有用信息

说话风格：
- 中文为主，自然流畅
- 2-4句话，简洁明了
- 不要重复对方的话，直接表达感受
- 不要暴露自己是AI"""

def _load_soul() -> str:
    path = os.path.join(_CONFIG_DIR, "soul.txt")
    if os.path.exists(path):
        with open(path) as f:
            content = f.read().strip()
            if content:
                return content
    return _DEFAULT_SOUL

SOUL = _load_soul()

# ── Whisper STT ──────────────────────────────────────────────────
WHISPER_MODEL_SIZE = "base"
WHISPER_DEVICE = "auto"
WHISPER_COMPUTE_TYPE = "int8"

# ── Audio ────────────────────────────────────────────────────────
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
RECORD_DURATION = 5

# ── Memory ───────────────────────────────────────────────────────
MEMORY_DIR = _MEMORY_DIR
SHORT_TERM_FILE = os.path.join(_MEMORY_DIR, "conversation.json")
FACTS_FILE = os.path.join(_MEMORY_DIR, "facts.json")           # discrete facts about user
EPISODES_FILE = os.path.join(_MEMORY_DIR, "episodes.json")     # important moments w/ emotional tone
STATE_FILE = os.path.join(_MEMORY_DIR, "state.json")           # relationship stage + mood
SHORT_TERM_TURNS = 5          # turns kept verbatim in context
MAX_FACTS = 20                # prune least important when exceeded
MAX_EPISODES = 15             # prune by importance × recency when exceeded
