"""LLM brain — DeepSeek chat with personality + layered memory + MoodEngine."""
import json
import os
import re
import threading
from openai import OpenAI

from .config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_COMPRESS_MODEL,
    SOUL,
    USER_PROFILE_FILE,
    MEMORY_MD_FILE,
    SHORT_TERM_FILE,
    FACTS_FILE,
    EPISODES_FILE,
    STATE_FILE,
    SHORT_TERM_TURNS,
    MAX_FACTS,
    MAX_EPISODES,
)
from .moods import MOODS

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
第二行开始直接输出要说的话。不要输出 face 字段。不要用 [mood:xxx] 标签。
回答要适合边显示边朗读：中文自然、短句优先、2-4 句话。"""

_COMPRESS_PROMPT = """根据对话片段提取记忆。已有事实供参考（避免重复）：
{existing_facts}

对话片段：
{new_turns}

严格输出 JSON（不要 markdown 包裹）：
{{"facts": ["一句话长期事实"], "episodes": ["重要片段概括"], "mood": "固定mood或空字符串"}}

- mood 只能从这里选：{moods}
- facts 只写稳定、可复用、未来有帮助的信息，例如用户身份、偏好、目标、项目、研究方向、明确要求
- 不要把临时玩笑、角色扮演设定、一次性的夸张说法写入 facts
- episodes 只写真正重要的互动片段、关系节点或科研工作节点
- 日常寒暄、重复问候、无长期价值的视觉描述忽略
- facts 最多 3 条，episodes 最多 1 条
- mood 只在情绪明显变化时写；无变化写空字符串"""

_memory_lock = threading.Lock()
_compression_lock = threading.Lock()


# ── MoodEngine ──────────────────────────────────────────────────

_MOOD_KEYWORDS = {
    "开心": "happy", "高兴": "happy", "哈哈": "happy", "棒": "happy",
    "生气": "angry", "愤怒": "angry",
    "难过": "sad", "伤心": "sad", "唉": "sad",
    "惊讶": "surprised", "哇": "surprised", "真的吗": "surprised",
    "思考": "thinking", "嗯": "thinking",
    "困惑": "confused",
    "害怕": "afraid", "怕": "afraid", "紧张": "afraid",
    "花痴": "lovestruck", "喜欢": "lovestruck",
    "酷": "cool", "装酷": "cool",
    "困": "sleepy", "累": "sleepy", "晚安": "sleepy",
    "爱": "soothing", "谢谢": "soothing", "温柔": "soothing",
    "好玩": "playful", "哈哈": "playful",
    "厉害": "excited", "太棒": "excited", "牛逼": "excited",
    "专注": "focused", "认真": "focused",
}

_MOOD_TAG_RE = re.compile(r'\[mood:(\w+)\]')
_JSON_HEADER_RE = re.compile(r'^\s*(\{.*?\})(?:\s*\n|$)', re.S)


class MoodEngine:
    """Tracks current mood. Receives mood tags from LLM output and
    keyword hints from user input."""

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
        """Strip mood metadata, update mood, return cleaned text."""
        _, text = self.parse_json_header(text)
        global _MOOD_TAG_RE
        match = _MOOD_TAG_RE.match(text)  # match at start only
        if match:
            mood = match.group(1)
            self.apply_mood(mood)
            return _MOOD_TAG_RE.sub("", text, count=1).lstrip()
        # Fallback: check anywhere in text (backward compat)
        match = _MOOD_TAG_RE.search(text)
        if match:
            self.apply_mood(match.group(1))
        return _MOOD_TAG_RE.sub("", text).strip()

    def hint_from_user(self, text: str) -> str:
        """Optional: detect user's emotional tone to bias assistant mood."""
        for keyword, mood in _MOOD_KEYWORDS.items():
            if keyword in text:
                return mood
        return ""

    def hint_from_reply(self, text: str) -> str:
        """Analyze assistant's own reply for mood signals (fallback when no tag)."""
        if any(w in text for w in ["？", "呢", "吧", "吗", "想", "考虑", "maybe"]):
            return "thinking"
        if any(w in text for w in ["！", "太棒", "厉害", "哇", "牛逼", "真好"]):
            return "excited"
        if any(w in text for w in ["谢谢", "温柔", "好哒", "放心", "没事"]):
            return "soothing"
        if any(w in text for w in ["伤心", "难过", "唉", "可惜", "遗憾"]):
            return "sad"
        if any(w in text for w in ["害怕", "紧张", "慌", "担心"]):
            return "afraid"
        if any(w in text for w in ["生气", "火大", "离谱"]):
            return "angry"
        if any(w in text for w in ["喜欢", "可爱", "心动"]):
            return "lovestruck"
        if any(w in text for w in ["酷", "帅", "稳住"]):
            return "cool"
        if any(w in text for w in ["笑", "哈哈", "嘿嘿", "开玩笑"]):
            return "playful"
        if any(w in text for w in ["困", "累", "睡了", "晚安", "哈欠"]):
            return "sleepy"
        if any(w in text for w in ["哦", "原来", "这样啊", "明白"]):
            return "thinking"
        # Check punctuation ratio for excitement
        excl = text.count("！")
        if excl >= 2:
            return "excited"
        return ""


# ── Memory IO ────────────────────────────────────────────────────

def _load_short_term() -> list[dict]:
    if os.path.exists(SHORT_TERM_FILE):
        with _memory_lock:
            with open(SHORT_TERM_FILE) as f:
                return json.load(f)
    return []


def _save_short_term(messages: list[dict]) -> None:
    os.makedirs(os.path.dirname(SHORT_TERM_FILE), exist_ok=True)
    with _memory_lock:
        with open(SHORT_TERM_FILE, "w") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)


def _load(path: str, default):
    if os.path.exists(path):
        with _memory_lock:
            with open(path) as f:
                return json.load(f)
    return default


def _save(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _memory_lock:
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _load_facts() -> list:
    return _load(FACTS_FILE, [])


def _load_episodes() -> list:
    return _load(EPISODES_FILE, [])


def _load_state() -> dict:
    state = _load(STATE_FILE, {})
    if state.get("mood") and state["mood"] not in ALLOWED_MOODS:
        state = {k: v for k, v in state.items() if k != "mood"}
    return state


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


def _write_memory_md() -> None:
    facts = _load_facts()
    episodes = _load_episodes()
    state = _load_state()

    lines = ["# 小灵记忆", ""]
    if state.get("mood"):
        lines.extend(["## 最近互动基调", state["mood"], ""])
    if facts:
        lines.append("## 关于用户的长期事实")
        lines.extend(f"- {fact}" for fact in facts)
        lines.append("")
    if episodes:
        lines.append("## 重要互动片段")
        lines.extend(f"- {episode}" for episode in episodes)
        lines.append("")

    os.makedirs(os.path.dirname(MEMORY_MD_FILE), exist_ok=True)
    with _memory_lock:
        with open(MEMORY_MD_FILE, "w") as f:
            f.write("\n".join(lines).strip() + "\n")


# ── Memory Compression ───────────────────────────────────────────

def _compress_turns(turns: list[dict]) -> None:
    if not turns:
        return
    with _compression_lock:
        new_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '小灵'}: {m.get('content', '')}"
            for m in turns
        )
        prompt = _COMPRESS_PROMPT.format(
            existing_facts=json.dumps(_load_facts(), ensure_ascii=False) or "（暂无）",
            new_turns=new_text,
            moods=" / ".join(ORDERED_MOODS()),
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

        new_facts = [str(item).strip() for item in data.get("facts", []) if str(item).strip()]
        if new_facts:
            facts = _load_facts()
            seen = {str(item).strip() for item in facts}
            for fact in new_facts:
                if fact not in seen:
                    facts.insert(0, fact)
                    seen.add(fact)
            _save(FACTS_FILE, facts[:MAX_FACTS])

        new_episodes = [str(item).strip() for item in data.get("episodes", []) if str(item).strip()]
        if new_episodes:
            episodes = _load_episodes()
            seen = {str(item).strip() for item in episodes}
            for episode in new_episodes:
                if episode not in seen:
                    episodes.insert(0, episode)
                    seen.add(episode)
            _save(EPISODES_FILE, episodes[:MAX_EPISODES])

        mood = str(data.get("mood", "")).strip()
        if mood in ALLOWED_MOODS:
            state = _load_state()
            state["mood"] = mood
            _save(STATE_FILE, state)

        _write_memory_md()


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
    facts = _load_facts()
    episodes = _load_episodes()
    messages = [
        {"role": "system", "content": _load_runtime_soul()},
        {"role": "system", "content": MOOD_PROTOCOL.format(moods=" / ".join(ORDERED_MOODS()))},
    ]

    state = _load_state()
    if state.get("mood"):
        messages.append({"role": "system", "content": f"【最近互动基调】{state['mood']}"})

    user_profile = _load_text(USER_PROFILE_FILE)
    if user_profile:
        messages.append({"role": "system", "content": "【用户画像 user.md】\n" + user_profile})

    memory_md = _load_text(MEMORY_MD_FILE)
    if memory_md:
        messages.append({"role": "system", "content": "【长期记忆 memory.md】\n" + memory_md})

    if facts and not memory_md:
        lines = [f"- {f}" for f in facts[:10]]
        messages.append({"role": "system", "content": "【关于他你知道这些】\n" + "\n".join(lines)})

    if episodes and not memory_md:
        lines = [f"- {e}" for e in episodes[:5]]
        messages.append({"role": "system", "content": "【你们之间的事】\n" + "\n".join(lines)})

    messages.extend(short_term)

    if extra:
        messages.append({"role": "user", "content": extra})

    fc = len(facts)
    ec = len(episodes)
    tc = len(short_term) // 2
    print(f"\n📋 上下文: Soul + {fc}事实 + {ec}片段 + {tc}轮对话")
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
        "calm", "happy", "thinking", "excited", "confused", "surprised",
        "focused", "angry", "sad", "afraid", "playful", "lovestruck",
        "cool", "soothing", "sleepy",
    ]
