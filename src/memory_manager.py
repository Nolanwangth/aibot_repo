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
    MAX_MEMORY_STREAM,
    MAX_CANDIDATES,
)

_lock = threading.Lock()

MEMORY_TYPES = frozenset({
    "preference", "project", "fact", "episode",
    "task", "correction", "relationship",
})


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

    _ensure_dir(MEMORY_STREAM_FILE)
    with _lock:
        with open(MEMORY_STREAM_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _prune_stream()


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
    if wm.get("mode"):
        parts.append(f"模式: {wm['mode']}")
    return " | ".join(parts) if parts else "暂无工作状态"


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
    reflection = load_reflection()
    # Auto-refresh reflection if empty or stale
    if not reflection:
        reflection = refresh_reflection(conversation_turns)

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

    # Reflection summary (last 3 lines of actionable content)
    if reflection:
        refl_lines = [l for l in reflection.split("\n") if l.strip() and not l.startswith("#")]
        if refl_lines:
            actionable = [l for l in refl_lines if "建议" in l or "⚠" in l or "推进" in l or "主动" in l]
            if actionable:
                lines.append("## 反思提醒")
                lines.extend(actionable[:3])
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
