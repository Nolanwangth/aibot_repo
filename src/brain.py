"""LLM brain — DeepSeek chat with personality + layered memory."""
import json
import os
from openai import OpenAI

from .config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    SOUL,
    SHORT_TERM_FILE,
    FACTS_FILE,
    EPISODES_FILE,
    STATE_FILE,
    SHORT_TERM_TURNS,
    MAX_FACTS,
    MAX_EPISODES,
)

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

_COMPRESS_PROMPT = """根据对话片段提取记忆。已有事实供参考（避免重复）：
{existing_facts}

对话片段：
{new_turns}

严格输出 JSON（不要 markdown 包裹）：
{{"facts": ["一句话事实"], "episodes": ["重要片段概括"], "mood": "当前情绪基调，无变化则空字符串"}}

- 只提取值得跨轮记住的信息，日常寒暄忽略
- facts 最多 3 条，episodes 最多 1 条
- mood 只在情绪明显变化时写"""


# ── Memory IO ────────────────────────────────────────────────────

def _load_short_term() -> list[dict]:
    if os.path.exists(SHORT_TERM_FILE):
        with open(SHORT_TERM_FILE) as f:
            return json.load(f)
    return []


def _save_short_term(messages: list[dict]) -> None:
    os.makedirs(os.path.dirname(SHORT_TERM_FILE), exist_ok=True)
    with open(SHORT_TERM_FILE, "w") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def _load(path: str, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _save(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_facts() -> list:
    return _load(FACTS_FILE, [])


def _load_episodes() -> list:
    return _load(EPISODES_FILE, [])


def _load_state() -> dict:
    return _load(STATE_FILE, {})


# ── Memory Compression ───────────────────────────────────────────

def _compress_turns(turns: list[dict]) -> None:
    new_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else '小灵'}: {m['content']}"
        for m in turns
    )
    prompt = _COMPRESS_PROMPT.format(
        existing_facts=json.dumps(_load_facts(), ensure_ascii=False) or "（暂无）",
        new_turns=new_text,
    )
    resp = _client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        **_chat_kwargs(DEEPSEEK_MODEL, 0.3, 200),
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

    # Merge facts (deduplicate, keep newest first, trim)
    if data.get("facts"):
        facts = _load_facts()
        seen = set(facts)
        for f in data["facts"]:
            if f not in seen:
                facts.insert(0, f)
                seen.add(f)
        _save(FACTS_FILE, facts[:MAX_FACTS])

    # Append episodes (newest first, trim)
    if data.get("episodes"):
        episodes = _load_episodes()
        for ep in data["episodes"]:
            episodes.insert(0, ep)
        _save(EPISODES_FILE, episodes[:MAX_EPISODES])

    # Update mood
    if data.get("mood"):
        state = _load_state()
        state["mood"] = data["mood"]
        _save(STATE_FILE, state)


# ── Context Builder ──────────────────────────────────────────────

def _build_context(extra: str = "") -> list[dict]:
    messages = [{"role": "system", "content": SOUL}]

    state = _load_state()
    if state.get("mood"):
        messages.append({"role": "system", "content": f"【最近互动基调】{state['mood']}"})

    facts = _load_facts()
    if facts:
        lines = [f"- {f}" for f in facts[:10]]
        messages.append({"role": "system", "content": "【关于他你知道这些】\n" + "\n".join(lines)})

    episodes = _load_episodes()
    if episodes:
        lines = [f"- {e}" for e in episodes[:5]]
        messages.append({"role": "system", "content": "【你们之间的事】\n" + "\n".join(lines)})

    messages.extend(_load_short_term())

    if extra:
        messages.append({"role": "user", "content": extra})

    fc = len(facts)
    ec = len(episodes)
    tc = len(_load_short_term()) // 2
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
        _compress_turns(overflow)

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
    _save_turn(user_text, reply)
    return reply
