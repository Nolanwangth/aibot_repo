"""Centralized configuration — loads from data/config/, falls back to defaults."""
import json
import os

# ── Paths ────────────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)
_CONFIG_DIR = os.path.join(_BASE, "..", "data", "config")
_MEMORY_DIR = os.path.join(_BASE, "..", "data", "memory")

# ── DeepSeek API Key ─────────────────────────────────────────────
def _load_deepseek_key() -> str:
    return os.getenv("DEEPSEEK_API_KEY", "")

DEEPSEEK_API_KEY = _load_deepseek_key()

def require_deepseek_key() -> str:
    """Raise if key is not set. Call at API usage site, not at import time."""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DeepSeek API Key not found. Set DEEPSEEK_API_KEY env var")
    return DEEPSEEK_API_KEY
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
DEEPSEEK_COMPRESS_MODEL = _settings.get("compress_model", "deepseek-v4-flash")
TTS_VOICE = _settings.get("tts_voice", "zh-CN-XiaoxiaoNeural")
SPEECH_OUTPUT_ENABLED = bool(_settings.get("speech_output_enabled", True))
PROACTIVE_ENABLED = bool(_settings.get("proactive_enabled", True))
PROACTIVE_IDLE_SECONDS = max(10, int(_settings.get("proactive_idle_seconds", 60)))

# ── Soul (editable via data/config/soul.md) ──────────────────────
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
    md_path = os.path.join(_CONFIG_DIR, "soul.md")
    if os.path.exists(md_path):
        with open(md_path) as f:
            content = f.read().strip()
            if content:
                return content

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
USER_PROFILE_FILE = os.path.join(_CONFIG_DIR, "user.md")       # editable user profile
MEMORY_MD_FILE = os.path.join(_MEMORY_DIR, "memory.md")        # human-readable memory digest
SHORT_TERM_FILE = os.path.join(_MEMORY_DIR, "conversation.json")
FACTS_FILE = os.path.join(_MEMORY_DIR, "facts.json")           # (legacy) discrete facts about user
EPISODES_FILE = os.path.join(_MEMORY_DIR, "episodes.json")     # (legacy) important moments
STATE_FILE = os.path.join(_MEMORY_DIR, "state.json")           # relationship stage + mood

# New memory system paths
MEMORY_STREAM_FILE = os.path.join(_MEMORY_DIR, "memory_stream.jsonl")       # append-only memory stream
MEMORY_CANDIDATES_FILE = os.path.join(_MEMORY_DIR, "memory_candidates.json") # pending candidates
WORKING_MEMORY_FILE = os.path.join(_MEMORY_DIR, "working_memory.json")      # current state
REFLECTION_FILE = os.path.join(_MEMORY_DIR, "reflection.md")                # periodic reflection

SHORT_TERM_TURNS = 5          # turns kept verbatim in context
MAX_FACTS = 20                # prune least important when exceeded (legacy)
MAX_EPISODES = 15             # prune by importance × recency when exceeded (legacy)
MAX_MEMORY_STREAM = 200       # max items in memory stream before pruning low-importance
MAX_CANDIDATES = 30           # max pending candidates
