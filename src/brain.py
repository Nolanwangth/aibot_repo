"""LLM brain — DeepSeek chat with personality + layered memory + mood parsing."""
import json
import os
import re
import threading
import time
from openai import OpenAI

from .config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_COMPRESS_MODEL,
    require_deepseek_key,
    SOUL,
    USER_PROFILE_FILE,
    SHORT_TERM_FILE,
    SHORT_TERM_TURNS,
)
from . import memory_manager as mem
from .moods import MOODS

# Validate key when brain module loads (not when config loads)
require_deepseek_key()
_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

# V4 models default to thinking mode → empty content. Must explicitly disable.
_V4_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}

def _chat_kwargs(model, temperature, max_tokens):
    kwargs = {"model": model, "temperature": temperature, "max_tokens": max_tokens}
    if model in _V4_MODELS:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return kwargs

_VISION_PROMPT = """用户说了一句话想要你"看"，你需要把它转化成一个给视觉模型的图片分析指令。
只输出指令本身，不要加任何前缀或解释。指令应聚焦于：
- 描述场景、人物、物体、动作
- 分析穿搭、表情、环境等
用中文，简洁明确，不超过一句话。"""

ALLOWED_MOODS = set(MOODS)
MOOD_PROTOCOL = """【输出协议】
第一行必须只输出一个 JSON 对象，不要 markdown，不要解释：
{{"mood":"calm"}}

mood 必须从这里选一个：{moods}
mood 就是小灵此刻该有的表情，是她的内心状态和用户刚才那句话共同折射出来的脸。结合用户这句话、private_state 和上一轮表情，觉得该是什么就选什么。
第二行开始直接输出要说的话。
回答要适合边显示边朗读：中文自然、短句优先、2-4 句话。"""

_COMPRESS_PROMPT = """根据对话片段提取值得长期记住的信息。已有记忆供参考（避免重复）：
{existing_facts}

对话片段：
{new_turns}

严格输出 JSON（不要 markdown 包裹）：
{{"candidates": [
  {{"type": "fact", "content": "一句话长期事实", "importance": 7, "reason": "为什么值得记住", "mood": ""}},
  {{"type": "episode", "content": "重要片段概括", "importance": 6, "reason": "为什么重要", "mood": ""}}
]}}

可选 type：
- preference: 用户偏好、习惯、喜好
- project: 项目信息、进度、技术细节
- fact: 稳定、可复用的长期事实（用户身份、目标、研究方向、明确要求）
- correction: 用户纠正过的东西
- relationship: 关系节点、情感互动
- episode: 值得记住的互动片段或科研工作节点
- task: 待办或正在做的任务

规则：
- importance 1-10，越高越重要
- reason 简短说明这条为什么值得记住（对后续陪伴和科研协作有用）
- mood 只在情绪明显相关时写
- 不要把临时玩笑、角色扮演设定、一次性的夸张说法写入
- 日常寒暄、重复问候、无长期价值的视觉描述忽略
- 明确偏好、项目进度、用户纠正、长期目标、正在推进的任务要优先保留
- candidates 最多 3 条"""

_memory_lock = threading.Lock()
_compression_lock = threading.Lock()


# ── Mood State ──────────────────────────────────────────────────

_MOOD_TAG_RE = re.compile(r'\[mood:(\w+)\]')
_JSON_HEADER_RE = re.compile(r'^\s*(\{.*?\})(?:\s*\n|$)', re.S)


class MoodState:
    """Thin mood adapter: LLM JSON mood -> face + last_mood state."""

    def __init__(self):
        self.current_mood = "calm"
        self._face = None
        self._last_assistant_mood = "calm"

    def bind_face(self, face):
        self._face = face

    def apply_mood(self, mood: str) -> bool:
        mood = (mood or "").strip()
        if mood not in ALLOWED_MOODS:
            return False

        self.current_mood = mood
        self._last_assistant_mood = mood
        try:
            mem.set_last_mood(mood)
        except Exception:
            pass
        if self._face:
            self._face.set_mood(mood)
        return True

    def parse_json_header(self, text: str) -> tuple[str, str]:
        """Parse a leading {"mood":"..."} header and return (mood, body)."""
        match = _JSON_HEADER_RE.match(text or "")
        if not match:
            return "", text
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return "", text
        mood = data.get("mood", "")
        body = text[match.end():].lstrip()
        if self.apply_mood(mood):
            return mood, body
        return "", body

    def parse_llm_output(self, text: str) -> str:
        """Strip mood metadata, update mood, return cleaned text.
        Keeps backward-compat parsing of [mood:xxx] tags."""
        _, text = self.parse_json_header(text)
        # Backward compat: strip any [mood:xxx] still in output
        match = _MOOD_TAG_RE.match(text)
        if match:
            mood = match.group(1)
            self.apply_mood(mood)
            return _MOOD_TAG_RE.sub("", text, count=1).lstrip()
        match = _MOOD_TAG_RE.search(text)
        if match:
            self.apply_mood(match.group(1))
        return _MOOD_TAG_RE.sub("", text).strip()


# ── Memory IO ────────────────────────────────────────────────────

def _load_short_term() -> list[dict]:
    if os.path.exists(SHORT_TERM_FILE):
        with _memory_lock:
            with open(SHORT_TERM_FILE) as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    return []


def _save_short_term(messages: list[dict]) -> None:
    os.makedirs(os.path.dirname(SHORT_TERM_FILE), exist_ok=True)
    with _memory_lock:
        with open(SHORT_TERM_FILE, "w") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)


def _load_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with _memory_lock:
        with open(path) as f:
            return f.read().strip()


def _load_runtime_soul() -> str:
    config_dir = os.path.dirname(USER_PROFILE_FILE)
    soul_md = os.path.join(config_dir, "soul.md")
    soul_txt = os.path.join(config_dir, "soul.txt")
    return _load_text(soul_md) or _load_text(soul_txt) or SOUL


# ── Memory Compression ───────────────────────────────────────────

def _compress_turns(turns: list[dict]) -> None:
    if not turns:
        return
    with _compression_lock:
        new_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '小灵'}: {m.get('content', '')}"
            for m in turns
        )
        # Use existing memory stream contents as reference (avoid duplication)
        existing = mem.load_stream(limit=10, min_importance=6)
        existing_text = json.dumps([e["content"] for e in existing], ensure_ascii=False) if existing else "（暂无）"

        prompt = _COMPRESS_PROMPT.format(
            existing_facts=existing_text,
            new_turns=new_text,
        )
        resp = _client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            **_chat_kwargs(DEEPSEEK_COMPRESS_MODEL, 0.3, 300),
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        candidates_raw = data.get("candidates", [])
        if not candidates_raw:
            return

        normalized = []
        for c in candidates_raw:
            item = dict(c)
            item["source_turn_ids"] = [str(time.time())]
            normalized.append(item)

        accepted = mem.auto_ingest(normalized)
        if accepted:
            print(f"🧠 自动记住 {len(accepted)} 条长期记忆")


def _compress_turns_background(turns: list[dict]) -> None:
    def worker():
        try:
            _compress_turns(turns)
        except Exception as exc:
            print(f"🧠 记忆压缩失败，已跳过: {exc}")

    threading.Thread(target=worker, daemon=True).start()


# ── Context Builder ──────────────────────────────────────────────

def _build_context(extra: str = "") -> list[dict]:
    short_term = _load_short_term()
    messages = [
        {"role": "system", "content": _load_runtime_soul()},
        {"role": "system", "content": MOOD_PROTOCOL.format(moods=" / ".join(ORDERED_MOODS()))},
    ]

    user_profile = _load_text(USER_PROFILE_FILE)
    if user_profile:
        messages.append({"role": "system", "content": "【用户画像 user.md】\n" + user_profile})

    wm_summary = mem.working_memory_summary()
    if wm_summary:
        messages.append({"role": "system", "content": "【当前工作状态 working_memory】\n" + wm_summary})

    emotional_state = mem.emotional_state_summary()
    if emotional_state:
        messages.append({"role": "system", "content": "【小灵内在状态 private_state】\n" + emotional_state})

    memory_md = mem.load_memory_md()
    if memory_md:
        messages.append({"role": "system", "content": "【长期记忆 memory.md】\n" + memory_md})

    messages.extend(short_term)

    if extra:
        messages.append({"role": "user", "content": extra})

    tc = len(short_term) // 2
    print(f"\n📋 上下文: Soul + working_memory + memory.md + {tc}轮对话")
    return messages


# ── Turn Persistence ─────────────────────────────────────────────

def _save_turn(user_text: str, reply: str) -> None:
    if not reply or not reply.strip():
        return
    short_term = _load_short_term()
    short_term.append({"role": "user", "content": user_text})
    short_term.append({"role": "assistant", "content": reply})

    max_msgs = SHORT_TERM_TURNS * 2
    if len(short_term) > max_msgs:
        overflow = short_term[:-max_msgs]
        short_term = short_term[-max_msgs:]
        _compress_turns_background(overflow)

    _save_short_term(short_term)


# ── Public API ───────────────────────────────────────────────────

def chat(user_text: str) -> str:
    messages = _build_context(user_text)
    response = _client.chat.completions.create(
        messages=messages,
        **_chat_kwargs(DEEPSEEK_MODEL, 0.9, 1000),
    )
    reply = response.choices[0].message.content
    _save_turn(user_text, reply)
    return reply


def chat_stream(user_text: str):
    messages = _build_context(user_text)
    stream = _client.chat.completions.create(
        messages=messages,
        stream=True,
        stream_options={"include_usage": True},
        **_chat_kwargs(DEEPSEEK_MODEL, 0.9, 1000),
    )
    for chunk in stream:
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def generate_vision_query(user_text: str) -> str:
    response = _client.chat.completions.create(
        messages=[
            {"role": "system", "content": _VISION_PROMPT},
            {"role": "user", "content": user_text},
        ],
        **_chat_kwargs(DEEPSEEK_MODEL, 0.3, 100),
    )
    return response.choices[0].message.content


def chat_with_vision(user_text: str, image_description: str) -> str:
    context = f"""用户说：{user_text}

【摄像头拍到的画面描述】
{image_description}

像亲眼看到了一样，用你的性格自然回应上述画面内容。不要说你"看了描述"，直接评价画面本身。"""

    messages = _build_context(context)
    response = _client.chat.completions.create(
        messages=messages,
        **_chat_kwargs(DEEPSEEK_MODEL, 0.9, 1000),
    )
    reply = response.choices[0].message.content
    return reply


def ORDERED_MOODS() -> list[str]:
    return [
        "excited", "confused", "surprised", "focused", "angry", "sad",
        "afraid", "playful", "lovestruck", "cool", "soothing", "sleepy",
        "calm", "happy", "thinking",
    ]
