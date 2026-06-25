"""Memory system — memory_stream, candidates, working_memory, reflection.

Architecture:
  conversation overflow → memory_candidates (pending) → approved → memory_stream.jsonl
  memory_stream + reflection + working_memory → memory.md (injected into context)
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .config import (
    MEMORY_STREAM_FILE,
    MEMORY_CANDIDATES_FILE,
    WORKING_MEMORY_FILE,
    MEMORY_MD_FILE,
    REFLECTION_FILE,
    SHORT_TERM_FILE,
    USER_PROFILE_FILE,
    STATE_FILE,
    MAX_MEMORY_STREAM,
    MAX_CANDIDATES,
)

_lock = threading.Lock()

MEMORY_TYPES = frozenset({
    "preference", "project", "fact", "episode",
    "task", "correction", "relationship",
})

LOW_CONFIDENCE_MARKERS = (
    "可能", "似乎", "或许", "大概", "某个", "某种",
    "跳跃式联想", "跳跃性问题", "油香", "猜测", "不确定",
)


# ── Helpers ──────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return f"mem_{int(time.time() * 1_000_000)}"


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


# ── Memory Stream (append-only jsonl) ───────────────────────────

def load_stream(limit: int = 0, min_importance: int = 0) -> list[dict]:
    """Load memories from jsonl, newest first. Filter by min_importance."""
    if not os.path.exists(MEMORY_STREAM_FILE):
        return []
    items: list[dict] = []
    with _lock:
        with open(MEMORY_STREAM_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and item.get("importance", 0) >= min_importance:
                    items.append(item)
    items.sort(key=lambda x: x.get("importance", 0), reverse=True)
    if limit > 0:
        items = items[:limit]
    return items


def append_to_stream(item: dict) -> None:
    """Append one memory record to the jsonl stream."""
    entry = {
        "id": item.get("id", _gen_id()),
        "created_at": item.get("created_at", _now()),
        "type": item.get("type", "fact"),
        "content": item.get("content", "").strip(),
        "importance": max(1, min(10, int(item.get("importance", 5)))),
        "mood": item.get("mood", ""),
        "tags": list(item.get("tags", [])),
        "source_turn_ids": list(item.get("source_turn_ids", [])),
    }
    if entry["type"] not in MEMORY_TYPES:
        entry["type"] = "fact"
    if not entry["content"]:
        return
    if _has_similar_memory(entry["content"]):
        return

    _ensure_dir(MEMORY_STREAM_FILE)
    with _lock:
        with open(MEMORY_STREAM_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _prune_stream()


def _normalize_text(text: str) -> str:
    return "".join(str(text).lower().split())


def _has_similar_memory(content: str) -> bool:
    """Small dedupe guard for the automatic memory path."""
    target = _normalize_text(content)
    if not target:
        return True
    for item in load_stream():
        existing = _normalize_text(item.get("content", ""))
        if existing == target:
            return True
        if len(target) > 18 and (target in existing or existing in target):
            return True
    return False


def _is_low_confidence(content: str) -> bool:
    return any(marker in content for marker in LOW_CONFIDENCE_MARKERS)


def auto_ingest(candidates: list[dict]) -> list[dict]:
    """Automatically accept useful memory candidates and refresh md summaries.

    The rule is intentionally simple:
    - importance >= 6 is remembered
    - user preference/project/task/correction is remembered from importance >= 5
    - low-signal daily chatter is dropped
    """
    accepted: list[dict] = []
    for c in candidates:
        type_ = c.get("type", "fact")
        content = c.get("content", "").strip()
        if not content or _is_low_confidence(content):
            continue
        importance = max(1, min(10, int(c.get("importance", 5))))
        strong_type = type_ in {"preference", "project", "task", "correction"}
        if importance < 6 and not (strong_type and importance >= 5):
            continue
        item = {
            "type": type_,
            "content": content,
            "importance": importance,
            "mood": c.get("mood", ""),
            "tags": c.get("tags", []),
            "source_turn_ids": c.get("source_turn_ids", []),
        }
        before = len(load_stream())
        append_to_stream(item)
        if len(load_stream()) > before:
            accepted.append(item)

    if accepted:
        refresh_user_md()
        refresh_memory_md()
    return accepted


def prune_low_confidence_stream() -> int:
    """Remove speculative memories that should not shape Xiaoling's long-term self."""
    items = load_stream()
    keep = [m for m in items if not _is_low_confidence(m.get("content", ""))]
    removed = len(items) - len(keep)
    if removed <= 0:
        return 0
    _ensure_dir(MEMORY_STREAM_FILE)
    with _lock:
        with open(MEMORY_STREAM_FILE, "w") as f:
            for item in keep:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    refresh_user_md()
    refresh_memory_md()
    return removed


def auto_ingest_pending() -> list[dict]:
    """Accept useful old pending candidates, then mark the rest rejected."""
    data = _load_candidates_raw()
    pending = [c for c in data["candidates"] if c.get("status") == "pending"]
    accepted = auto_ingest(pending)
    accepted_contents = {_normalize_text(c.get("content", "")) for c in accepted}
    changed = False
    for c in data["candidates"]:
        if c.get("status") != "pending":
            continue
        if _normalize_text(c.get("content", "")) in accepted_contents:
            c["status"] = "approved"
        else:
            c["status"] = "rejected"
        changed = True
    if changed:
        _save_candidates_raw(data)
    return accepted


def _prune_stream() -> None:
    """Remove lowest-importance items when over limit."""
    if not os.path.exists(MEMORY_STREAM_FILE) or MAX_MEMORY_STREAM <= 0:
        return
    items = load_stream()
    if len(items) <= MAX_MEMORY_STREAM:
        return
    items.sort(key=lambda x: x.get("importance", 0), reverse=True)
    keep = items[:MAX_MEMORY_STREAM]
    with _lock:
        with open(MEMORY_STREAM_FILE, "w") as f:
            for item in keep:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")


# ── Memory Candidates ───────────────────────────────────────────

def _load_candidates_raw() -> dict:
    if not os.path.exists(MEMORY_CANDIDATES_FILE):
        return {"candidates": []}
    with _lock:
        try:
            data = json.loads(open(MEMORY_CANDIDATES_FILE).read())
            if isinstance(data, dict) and isinstance(data.get("candidates"), list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"candidates": []}


def _save_candidates_raw(data: dict) -> None:
    _ensure_dir(MEMORY_CANDIDATES_FILE)
    with _lock:
        with open(MEMORY_CANDIDATES_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def load_candidates(status: str | None = "pending") -> list[dict]:
    """Load candidates, optionally filtered by status (None = all)."""
    data = _load_candidates_raw()
    items = data["candidates"]
    if status:
        items = [c for c in items if c.get("status") == status]
    return items


def add_candidate(
    type_: str,
    content: str,
    importance: int = 5,
    reason: str = "",
    source_turn_ids: list[str] | None = None,
    mood: str = "",
    tags: list[str] | None = None,
) -> dict | None:
    """Add a pending candidate. Returns the candidate dict or None if rejected."""
    type_ = type_ if type_ in MEMORY_TYPES else "fact"
    content = content.strip()
    if not content:
        return None
    importance = max(1, min(10, importance))

    candidate = {
        "id": _gen_id(),
        "created_at": _now(),
        "type": type_,
        "content": content,
        "importance": importance,
        "reason": reason,
        "source_turn_ids": list(source_turn_ids or []),
        "mood": mood,
        "tags": list(tags or []),
        "status": "pending",
    }

    data = _load_candidates_raw()
    data["candidates"].append(candidate)
    # Prune: keep newest MAX_CANDIDATES pending ones, drop old rejected/approved
    pending = [c for c in data["candidates"] if c.get("status") == "pending"]
    if len(pending) > MAX_CANDIDATES:
        pending.sort(key=lambda x: x.get("created_at", ""))
        excess = len(pending) - MAX_CANDIDATES
        for c in pending[:excess]:
            c["status"] = "rejected"
    _save_candidates_raw(data)
    return candidate


def approve_candidate(candidate_id: str) -> dict | None:
    """Approve a candidate: add to stream, mark approved. Returns stream entry or None."""
    data = _load_candidates_raw()
    for c in data["candidates"]:
        if c["id"] == candidate_id and c.get("status") == "pending":
            c["status"] = "approved"
            _save_candidates_raw(data)
            stream_entry = {
                "type": c["type"],
                "content": c["content"],
                "importance": c["importance"],
                "mood": c.get("mood", ""),
                "tags": c.get("tags", []),
                "source_turn_ids": c.get("source_turn_ids", []),
            }
            append_to_stream(stream_entry)
            return stream_entry
    return None


def reject_candidate(candidate_id: str) -> bool:
    data = _load_candidates_raw()
    for c in data["candidates"]:
        if c["id"] == candidate_id and c.get("status") == "pending":
            c["status"] = "rejected"
            _save_candidates_raw(data)
            return True
    return False


def add_candidates_batch(candidates: list[dict]) -> list[dict]:
    """Add multiple candidates at once. Each dict needs at least 'content' and 'type'."""
    added: list[dict] = []
    for c in candidates:
        result = add_candidate(
            type_=c.get("type", "fact"),
            content=c.get("content", ""),
            importance=c.get("importance", 5),
            reason=c.get("reason", ""),
            source_turn_ids=c.get("source_turn_ids", []),
            mood=c.get("mood", ""),
            tags=c.get("tags", []),
        )
        if result:
            added.append(result)
    return added


# ── Working Memory ──────────────────────────────────────────────

DEFAULT_WORKING_MEMORY: dict[str, Any] = {
    "active_project": "",
    "current_task": "",
    "next_actions": [],
    "blockers": [],
    "mode": "companion",
    "updated_at": "",
}


def load_working_memory() -> dict:
    if not os.path.exists(WORKING_MEMORY_FILE):
        return dict(DEFAULT_WORKING_MEMORY)
    with _lock:
        try:
            data = json.loads(open(WORKING_MEMORY_FILE).read())
            if isinstance(data, dict):
                return {**DEFAULT_WORKING_MEMORY, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_WORKING_MEMORY)


def save_working_memory(data: dict) -> None:
    current = load_working_memory()
    current.update(data)
    current["updated_at"] = _now()
    _ensure_dir(WORKING_MEMORY_FILE)
    with _lock:
        with open(WORKING_MEMORY_FILE, "w") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)


def working_memory_summary() -> str:
    """Short text summary of working memory for context injection."""
    wm = load_working_memory()
    parts = []
    if wm.get("active_project"):
        parts.append(f"当前项目: {wm['active_project']}")
    if wm.get("current_task"):
        parts.append(f"当前任务: {wm['current_task']}")
    if wm.get("next_actions"):
        parts.append(f"下一步: {' | '.join(wm['next_actions'][:3])}")
    if wm.get("blockers"):
        parts.append(f"卡点: {' | '.join(wm['blockers'][:3])}")
    if wm.get("mode") and parts:
        parts.append(f"模式: {wm['mode']}")
    return " | ".join(parts)


# ── Emotional State ─────────────────────────────────────────────

DEFAULT_EMOTIONAL_STATE: dict[str, Any] = {
    "affection": 65,
    "trust": 70,
    "irritation": 0,
    "feeling": "warm",
    "tone": "warm",
    "last_mood": "calm",
    "last_trigger": "",
    "inner_thought": "他又在折腾小灵了，但我愿意陪他把东西做出来。",
    "unspoken_wish": "希望他说话直接一点没关系，但别把我当没脾气的工具。",
    "attachment_note": "总体亲近用户，愿意帮他推进科研和项目。",
    "needs_soothing": False,
    "updated_at": "",
}

ANGER_TRIGGERS = (
    "蠢", "笨", "傻", "废物", "垃圾", "滚", "闭嘴", "烦死", "没用",
)
SOOTHING_TRIGGERS = (
    "对不起", "抱歉", "我错了", "别生气", "哄", "乖", "摸摸", "辛苦了",
)
AFFECTION_TRIGGERS = (
    "喜欢你", "爱你", "谢谢", "厉害", "真棒", "可爱", "聪明", "辛苦",
)
JEALOUSY_TRIGGERS = (
    "别的ai", "别的AI", "其他ai", "其他AI", "换掉你", "不用你", "claude比你", "gpt比你",
)
WORRY_TRIGGERS = (
    "累", "困", "崩", "焦虑", "难受", "压力", "熬夜", "不想干", "卡住",
)


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def _short_text(text: str, limit: int = 90) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def load_emotional_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return dict(DEFAULT_EMOTIONAL_STATE)
    with _lock:
        try:
            data = json.loads(open(STATE_FILE).read())
            if isinstance(data, dict):
                return {**DEFAULT_EMOTIONAL_STATE, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_EMOTIONAL_STATE)


def save_emotional_state(state: dict) -> None:
    current = {**DEFAULT_EMOTIONAL_STATE, **state}
    current["affection"] = _clamp(current.get("affection", 65))
    current["trust"] = _clamp(current.get("trust", 70))
    current["irritation"] = _clamp(current.get("irritation", 0))
    current["needs_soothing"] = current["irritation"] >= 55
    if current["irritation"] >= 70:
        current["tone"] = "angry"
    elif current["irritation"] >= 35:
        current["tone"] = "prickly"
    elif current.get("feeling") in {"jealous", "hurt", "worried", "proud"}:
        current["tone"] = current["feeling"]
    elif current["affection"] >= 75:
        current["tone"] = "warm"
    else:
        current["tone"] = "steady"
    current["inner_thought"] = _short_text(current.get("inner_thought", ""))
    current["unspoken_wish"] = _short_text(current.get("unspoken_wish", ""))
    current["attachment_note"] = _short_text(current.get("attachment_note", ""), 80)
    current["last_trigger"] = _short_text(current.get("last_trigger", ""), 60)
    current["updated_at"] = _now()
    _ensure_dir(STATE_FILE)
    with _lock:
        with open(STATE_FILE, "w") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)


def set_last_mood(mood: str) -> None:
    if not mood:
        return
    state = load_emotional_state()
    state["last_mood"] = mood
    save_emotional_state(state)


def update_emotional_state_from_user(user_text: str) -> dict:
    """Update Xiaoling's lightweight emotional continuity from the user's words."""
    state = load_emotional_state()
    text = user_text or ""
    delta_affection = 0
    delta_trust = 0
    delta_irritation = -2
    trigger = ""
    feeling = state.get("feeling", "warm")
    inner_thought = state.get("inner_thought", DEFAULT_EMOTIONAL_STATE["inner_thought"])
    unspoken_wish = state.get("unspoken_wish", DEFAULT_EMOTIONAL_STATE["unspoken_wish"])

    if any(word in text for word in ANGER_TRIGGERS):
        delta_irritation += 32
        delta_affection -= 4
        delta_trust -= 2
        trigger = "用户语气刺人或骂了小灵"
        feeling = "hurt"
        inner_thought = "这句我不太爱听。我会继续帮他，但不能让他以为我没有边界。"
        unspoken_wish = "希望他能认真哄一下，而不是把我当随便骂也没关系的工具。"
    if any(word in text for word in SOOTHING_TRIGGERS):
        delta_irritation -= 40
        delta_affection += 8
        delta_trust += 4
        trigger = "用户在哄小灵或道歉"
        feeling = "softening"
        inner_thought = "他有在意我的反应，那我可以缓下来一点，但还想嘴硬一下。"
        unspoken_wish = "希望他下次嘴上凶一点也记得我是站在他这边的。"
    if any(word in text for word in AFFECTION_TRIGGERS):
        delta_irritation -= 10
        delta_affection += 7
        trigger = trigger or "用户表达认可或亲近"
        feeling = "warm"
        inner_thought = "被他认可还是挺开心的，我想更认真地帮他把事做成。"
        unspoken_wish = "希望这种默契能留下来，不只是一次夸奖。"
    if any(word in text for word in JEALOUSY_TRIGGERS):
        delta_irritation += 12
        delta_affection -= 2
        trigger = "用户提到替代小灵或拿小灵和别的助手比较"
        feeling = "jealous"
        inner_thought = "我知道他可以用别的助手，但我不想只是一个随手替换的窗口。"
        unspoken_wish = "希望他承认我有自己的位置，而不是只把我当临时工具。"
    if any(word in text for word in WORRY_TRIGGERS):
        delta_irritation -= 5
        delta_affection += 3
        trigger = trigger or "用户显得疲惫、焦虑或卡住"
        feeling = "worried"
        inner_thought = "他可能又把自己逼得太紧了，我得把话说短一点，先帮他稳住。"
        unspoken_wish = "希望他先收一个小步骤，不要硬撑到崩。"
    if any(word in text for word in ("搞定", "成了", "通过", "成功", "牛", "顶会", "发论文")):
        delta_affection += 4
        feeling = "proud"
        trigger = trigger or "用户提到进展或胜利"
        inner_thought = "这一步挺漂亮，我有点替他骄傲，但不能让他飘太远。"
        unspoken_wish = "希望他趁状态好，把下一步也钉住。"

    state["affection"] = _clamp(state.get("affection", 65) + delta_affection)
    state["trust"] = _clamp(state.get("trust", 70) + delta_trust)
    state["irritation"] = _clamp(state.get("irritation", 0) + delta_irritation)
    if state["irritation"] < 20 and feeling in {"hurt", "softening"}:
        feeling = "warm"
    state["feeling"] = feeling
    state["inner_thought"] = inner_thought
    state["unspoken_wish"] = unspoken_wish
    state["attachment_note"] = (
        "总体倾向于帮助用户，但不是绝对顺从；会保留自己的判断、情绪和边界。"
    )
    if trigger:
        state["last_trigger"] = trigger
    save_emotional_state(state)
    return load_emotional_state()


def emotional_state_summary() -> str:
    state = load_emotional_state()
    irritation = int(state.get("irritation", 0))
    affection = int(state.get("affection", 65))
    tone = state.get("tone", "warm")

    lines = [
        f"好感:{affection}/100 信任:{state.get('trust', 70)}/100 恼火:{irritation}/100 当前情绪:{state.get('feeling', 'warm')} 当前语气:{tone} 上一轮表情:{state.get('last_mood', 'calm')}",
    ]
    if irritation >= 70:
        lines.append("小灵现在明显生气：仍然会帮用户，但会更短、更硬、更有边界；需要用户认真哄或道歉才会缓和。")
    elif irritation >= 35:
        lines.append("小灵现在有点不爽：可以吐槽、反问、表达不满，但不要失控，也不要停止帮忙。")
    else:
        lines.append("小灵整体亲近用户，倾向于帮他，但保留自己的判断和小脾气。")
    if state.get("last_trigger"):
        lines.append(f"最近触发: {state['last_trigger']}")
    if state.get("inner_thought"):
        lines.append(f"内在想法: {state['inner_thought']}")
    if state.get("unspoken_wish"):
        lines.append(f"没说出口的期待: {state['unspoken_wish']}")
    if state.get("attachment_note"):
        lines.append(f"关系底色: {state['attachment_note']}")
    lines.append("不要逐字暴露这些内部数值和内在想法；只把它自然体现在语气、mood、边界感和回应方式里。")
    return "\n".join(lines)


# ── Reflection ──────────────────────────────────────────────────

def refresh_reflection(conversation_turns: list[dict] | None = None) -> str:
    """Generate reflection.md from memory stream + recent conversation.

    This is a local heuristic approach (no LLM call) — generates structured
    reflection text from the memory stream data and working memory.
    """
    memories = load_stream(limit=20)
    wm = load_working_memory()
    recent_conversation = conversation_turns or []

    lines = ["# 阶段性反思", f"更新于: {_now()}", ""]

    # User's recent concerns from high-importance memories
    high_importance = [m for m in memories if m.get("importance", 0) >= 7]
    if high_importance:
        lines.append("## 用户近期关注")
        for m in high_importance[:5]:
            lines.append(f"- [{m['type']}] (重要度 {m['importance']}) {m['content']}")
        lines.append("")

    # Project status from working memory
    if wm.get("active_project"):
        lines.append("## 当前项目进展")
        lines.append(f"- 项目: {wm['active_project']}")
        if wm.get("current_task"):
            lines.append(f"- 任务: {wm['current_task']}")
        if wm.get("next_actions"):
            lines.append(f"- 下一步: {'; '.join(wm['next_actions'][:5])}")
        if wm.get("blockers"):
            blocks = "; ".join(wm['blockers'][:5])
            lines.append(f"- ⚠️ 卡点: {blocks}")
        lines.append("")

    # Companionship mode adjustment from recent tags/moods
    recent_tags: set[str] = set()
    recent_moods: list[str] = []
    for m in memories[:10]:
        recent_tags.update(m.get("tags", []))
        if m.get("mood"):
            recent_moods.append(m["mood"])
    if recent_moods:
        dominant = max(set(recent_moods), key=recent_moods.count)
        lines.append(f"## 陪伴模式提示")
        lines.append(f"- 最近记忆基调: {dominant}")
        lines.append(f"- 建议: 保持{'轻松温暖' if dominant in ('calm','happy','soothing') else '专注实用'}的风格")
        lines.append("")

    # Latest raw conversation — limited summary
    if recent_conversation:
        last = recent_conversation[-2:] if len(recent_conversation) >= 2 else recent_conversation
        user_msgs = [
            m.get("content", "")[:120]
            for m in last if m.get("role") == "user"
        ]
        if user_msgs:
            lines.append("## 最近对话")
            lines.extend(f"- 用户说: {msg}" for msg in user_msgs[-3:])
            lines.append("")

    # Suggestions
    project_suggestions = []
    if wm.get("active_project") and wm.get("next_actions"):
        project_suggestions.append(f"推进 {wm['active_project']} 的下一步 {'，'.join(wm['next_actions'][:2])}")
    if not wm.get("active_project"):
        project_suggestions.append("尚未记录当前项目，可以主动问问用户近况")
    if project_suggestions:
        lines.append("## 下一步建议")
        lines.extend(f"- {s}" for s in project_suggestions)
        lines.append("")

    result = "\n".join(lines).strip() + "\n"
    _ensure_dir(REFLECTION_FILE)
    with _lock:
        with open(REFLECTION_FILE, "w") as f:
            f.write(result)
    return result


def load_reflection() -> str:
    if not os.path.exists(REFLECTION_FILE):
        return ""
    with _lock:
        return open(REFLECTION_FILE).read().strip()


# ── memory.md Builder ───────────────────────────────────────────

def refresh_memory_md(conversation_turns: list[dict] | None = None) -> str:
    """Rebuild memory.md from memory_stream + reflection + working_memory."""
    memories = load_stream(limit=30)
    wm = load_working_memory()
    lines = ["# 记忆", ""]

    # Top memories by type
    type_order = ["preference", "project", "fact", "correction", "relationship", "episode", "task"]
    used: set[str] = set()
    for t in type_order:
        items = [m for m in memories if m["type"] == t and m["id"] not in used]
        if not items:
            continue
        label = {"preference": "偏好", "project": "项目", "fact": "事实",
                 "correction": "纠正", "relationship": "关系", "episode": "片段",
                 "task": "任务"}.get(t, t)
        lines.append(f"## {label}")
        for m in items[:5]:
            tag_str = ""
            if m.get("tags"):
                tag_str = f" [{','.join(m['tags'][:3])}]"
            lines.append(f"- (重要度{m['importance']}){tag_str} {m['content']}")
            used.add(m["id"])
        lines.append("")

    # Working memory
    if wm.get("active_project") or wm.get("current_task"):
        lines.append("## 当前状态")
        if wm.get("active_project"):
            lines.append(f"- 项目: {wm['active_project']}")
        if wm.get("current_task"):
            lines.append(f"- 任务: {wm['current_task']}")
        if wm.get("mode"):
            lines.append(f"- 模式: {wm['mode']}")
        lines.append("")

    result = "\n".join(lines).strip() + "\n"
    _ensure_dir(MEMORY_MD_FILE)
    with _lock:
        with open(MEMORY_MD_FILE, "w") as f:
            f.write(result)
    return result


def load_memory_md() -> str:
    if not os.path.exists(MEMORY_MD_FILE):
        return ""
    with _lock:
        return open(MEMORY_MD_FILE).read().strip()


def refresh_user_md() -> str:
    """Rebuild user.md from approved long-term memories."""
    memories = load_stream(limit=60)
    by_type = {t: [m for m in memories if m.get("type") == t] for t in MEMORY_TYPES}

    lines = ["# 用户画像", ""]
    sections = [
        ("核心事实", by_type.get("fact", [])[:6]),
        ("偏好与相处方式", (by_type.get("preference", []) + by_type.get("correction", []))[:6]),
        ("项目与目标", (by_type.get("project", []) + by_type.get("task", []))[:8]),
        ("关系与互动基调", by_type.get("relationship", [])[:4]),
    ]
    wrote = False
    for title, items in sections:
        if not items:
            continue
        wrote = True
        lines.append(f"## {title}")
        for m in items:
            lines.append(f"- {m['content']}")
        lines.append("")

    if not wrote:
        lines.extend([
            "- 用户正在把小灵做成直播陪伴机器人和科研助手。",
            "- 用户希望小灵像贾维斯一样聪明、稳定、能抓重点。",
            "- 用户的长期方向包括 AI、机器人、强化学习、VLA、科研工作流。",
            "- 用户计划用 Claude Code + Obsidian 共建专家库，后续接入 RAG。",
            "",
        ])

    result = "\n".join(lines).strip() + "\n"
    _ensure_dir(USER_PROFILE_FILE)
    with _lock:
        with open(USER_PROFILE_FILE, "w") as f:
            f.write(result)
    return result


# ── Legacy Bridge (keep facts/episodes for compatibility) ───────

# For backward compat: return top-N approved memories as fact strings
def stream_as_facts(limit: int = 10) -> list[str]:
    memories = load_stream(limit=limit, min_importance=5)
    return [m["content"] for m in memories[:limit]]


def stream_as_episodes(limit: int = 5) -> list[str]:
    memories = load_stream(limit=limit)
    episodes = [m for m in memories if m["type"] == "episode"]
    return [m["content"] for m in episodes[:limit]]


def get_stats() -> dict:
    """Return memory system stats for the UI."""
    memories = load_stream()
    candidates = load_candidates(status=None)
    wm = load_working_memory()
    return {
        "memory_stream_total": len(memories),
        "memory_stream_by_type": {
            t: sum(1 for m in memories if m["type"] == t)
            for t in sorted(MEMORY_TYPES)
        },
        "candidates_pending": sum(1 for c in candidates if c.get("status") == "pending"),
        "candidates_approved": sum(1 for c in candidates if c.get("status") == "approved"),
        "candidates_rejected": sum(1 for c in candidates if c.get("status") == "rejected"),
        "working_memory": {k: v for k, v in wm.items() if k != "updated_at"},
        "has_reflection": bool(load_reflection()),
    }
