"""Local web console for inspecting and editing Xiaoling context files."""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import memory_manager as mem

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "data" / "config"
MEMORY_DIR = ROOT / "data" / "memory"

TEXT_FILES = {
    "soul": CONFIG_DIR / "soul.txt",
    "user": CONFIG_DIR / "user.md",
    "memory": MEMORY_DIR / "memory.md",
    "reflection": MEMORY_DIR / "reflection.md",
}

JSON_FILES = {
    "settings": CONFIG_DIR / "settings.json",
    "conversation": MEMORY_DIR / "conversation.json",
    "facts": MEMORY_DIR / "facts.json",
    "episodes": MEMORY_DIR / "episodes.json",
    "state": MEMORY_DIR / "state.json",
    "memory_candidates": MEMORY_DIR / "memory_candidates.json",
    "memory_stream": MEMORY_DIR / "memory_stream.jsonl",
    "working_memory": MEMORY_DIR / "working_memory.json",
}

MOODS = [
    "calm", "happy", "thinking", "excited", "confused", "surprised",
    "focused", "angry", "sad", "afraid", "playful", "lovestruck",
    "cool", "soothing", "sleepy",
]

MOOD_PROTOCOL = """【输出协议】
第一行必须只输出一个 JSON 对象，不要 markdown，不要解释：
{{"mood":"calm"}}

mood 必须从这里选一个：{moods}
第二行开始直接输出要说的话。不要输出 face 字段。不要用 [mood:xxx] 标签。
回答要适合边显示边朗读：中文自然、短句优先、2-4 句话。"""


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    if isinstance(default, list):
        return data if isinstance(data, list) else default
    if isinstance(default, dict):
        return data if isinstance(data, dict) else default
    return data


def _runtime_soul() -> str:
    return _read_text(TEXT_FILES["soul"]).strip() or _read_text(CONFIG_DIR / "soul.txt").strip()


def _state() -> dict:
    state = _read_json(JSON_FILES["state"], {})
    if state.get("mood") and state["mood"] not in MOODS:
        return {k: v for k, v in state.items() if k != "mood"}
    return state


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_default_for(key: str):
    return [] if key in {"conversation", "facts", "episodes"} else {}


def _normalize_json_for(key: str, data):
    default = _json_default_for(key)
    if isinstance(default, list):
        return data if isinstance(data, list) else default
    return data if isinstance(data, dict) else default


def build_memory_markdown() -> str:
    facts = _read_json(JSON_FILES["facts"], [])
    episodes = _read_json(JSON_FILES["episodes"], [])
    state = _state()

    lines = ["# 小灵记忆", ""]
    if state.get("mood"):
        lines.extend(["## 最近互动基调", str(state["mood"]), ""])
    if facts:
        lines.append("## 关于用户的长期事实")
        lines.extend(f"- {fact}" for fact in facts)
        lines.append("")
    if episodes:
        lines.append("## 重要互动片段")
        lines.extend(f"- {episode}" for episode in episodes)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def refresh_memory_markdown() -> None:
    _write_text(TEXT_FILES["memory"], build_memory_markdown())


def assemble_context() -> list[dict[str, str]]:
    soul = _runtime_soul()

    messages = [
        {"role": "system", "name": "soul.txt", "content": soul},
        {
            "role": "system",
            "name": "mood protocol",
            "content": MOOD_PROTOCOL.format(moods=" / ".join(MOODS)),
        },
    ]

    user_profile = _read_text(TEXT_FILES["user"]).strip()
    if user_profile:
        messages.append({"role": "system", "name": "user.md", "content": "【用户画像 user.md】\n" + user_profile})

    wm_summary = mem.working_memory_summary()
    if wm_summary:
        messages.append({"role": "system", "name": "working_memory", "content": "【当前工作状态】\n" + wm_summary})

    memory_md = mem.load_memory_md()
    if memory_md:
        messages.append({"role": "system", "name": "memory.md", "content": "【长期记忆 memory.md】\n" + memory_md})
    else:
        # Fallback to legacy
        facts = _read_json(JSON_FILES["facts"], [])
        episodes = _read_json(JSON_FILES["episodes"], [])
        if facts:
            messages.append({
                "role": "system",
                "name": "facts.json",
                "content": "【关于他你知道这些】\n" + "\n".join(f"- {fact}" for fact in facts[:10]),
            })
        if episodes:
            messages.append({
                "role": "system",
                "name": "episodes.json",
                "content": "【你们之间的事】\n" + "\n".join(f"- {episode}" for episode in episodes[:5]),
            })

    messages.extend(_read_json(JSON_FILES["conversation"], []))
    return messages


def snapshot() -> dict:
    text = {key: _read_text(path) for key, path in TEXT_FILES.items()}
    data = {key: _read_json(path, [] if key in {"conversation", "facts", "episodes", "memory_candidates", "memory_stream"} else {}) for key, path in JSON_FILES.items()}
    context = assemble_context()
    return {
        "text": text,
        "json": data,
        "context": context,
        "stats": {
            "context_messages": len(context),
            "context_chars": sum(len(item.get("content", "")) for item in context),
            "short_term_messages": len(data["conversation"]),
            "facts": len(data["facts"]),
            "episodes": len(data["episodes"]),
            "memory_stream": len(mem.load_stream()),
            "candidates_pending": sum(1 for c in mem.load_candidates("pending")),
        },
        "memory_stats": mem.get_stats(),
    }


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小灵 Context Console</title>
  <style>
    :root { color-scheme: dark; --bg:#101116; --panel:#181a21; --line:#2a2d38; --text:#f2f3f7; --muted:#9ca3af; --accent:#61dafb; --ok:#56d364; --warn:#f2cc60; }
    * { box-sizing: border-box; }
    body { margin:0; font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }
    header { height:56px; display:flex; align-items:center; justify-content:space-between; padding:0 18px; border-bottom:1px solid var(--line); background:#12141b; }
    h1 { font-size:17px; margin:0; font-weight:650; }
    button { border:1px solid var(--line); background:#222630; color:var(--text); padding:7px 10px; border-radius:6px; cursor:pointer; }
    button:hover { border-color:var(--accent); }
    .wrap { display:grid; grid-template-columns: 220px 1fr 42%; height:calc(100vh - 56px); }
    nav { border-right:1px solid var(--line); padding:12px; overflow:auto; }
    nav button { width:100%; text-align:left; margin:0 0 8px; }
    nav button.active { border-color:var(--accent); color:var(--accent); }
    main, aside { padding:14px; overflow:auto; }
    aside { border-left:1px solid var(--line); background:#0d0f15; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px; margin-bottom:12px; }
    .row { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
    .title { font-size:15px; font-weight:650; }
    .muted { color:var(--muted); font-size:12px; }
    textarea { width:100%; min-height:calc(100vh - 190px); resize:vertical; border:1px solid var(--line); border-radius:8px; padding:12px; color:var(--text); background:#0f1117; font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }
    pre { white-space:pre-wrap; word-break:break-word; margin:0; font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; color:#d8dee9; }
    .msg { border:1px solid var(--line); border-radius:8px; padding:10px; margin-bottom:8px; background:#151821; }
    .msgHead { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:6px; }
    .mini { padding:2px 6px; font-size:11px; border-radius:5px; }
    .badge { display:inline-block; font-size:11px; color:#0b1020; background:var(--accent); padding:1px 6px; border-radius:999px; margin-right:6px; }
    .status { min-height:18px; color:var(--ok); font-weight:600; }
    .status.err { color:#ff7b72; }
    .grid { display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:8px; }
    .stat { background:#151821; border:1px solid var(--line); border-radius:7px; padding:8px; }
  </style>
</head>
<body>
  <header>
    <h1>小灵 Context Console</h1>
    <div>
      <button onclick="refreshMemory()" title="从 facts/episodes 生成 memory.md">刷新 memory.md</button>
      <button onclick="refreshMemoryStream()" title="从记忆流+反思+工作状态生成 memory.md">刷新记忆流</button>
      <button onclick="refreshReflection()" title="根据记忆流和最近对话重新生成反思">刷新反思</button>
      <button onclick="approveAll()" title="批准所有待审批候选">全部批准</button>
      <button onclick="loadAll()">重新读取</button>
    </div>
  </header>
  <div class="wrap">
    <nav id="nav"></nav>
    <main>
      <div class="panel">
        <div class="row">
          <div>
            <div class="title" id="editorTitle"></div>
            <div class="muted" id="editorHint"></div>
          </div>
          <button onclick="saveCurrent()">保存 Ctrl+S</button>
        </div>
        <textarea id="editor"></textarea>
        <div class="status" id="status"></div>
      </div>
    </main>
  <aside>
      <div class="panel">
        <div class="row"><div class="title">上下文统计</div></div>
        <div class="grid" id="stats"></div>
      </div>
      <div class="panel">
        <div class="row"><div class="title">记忆系统</div></div>
        <div class="grid" id="memStats"></div>
      </div>
      <div class="panel" id="candidatesPanel">
        <div class="row"><div class="title">待审批候选</div><button onclick="loadAll()">刷新</button></div>
        <div id="candidatesList"><span class="muted">加载中...</span></div>
      </div>
      <div class="panel">
        <div class="row"><div class="title">实际注入上下文</div><button onclick="copyContext()">复制</button></div>
        <div id="context"></div>
      </div>
    </aside>
  </div>
<script>
const tabs = [
  ["text:soul", "soul.txt", "人格、输出协议、说话风格"],
  ["text:user", "user.md", "用户画像和长期偏好"],
  ["text:memory", "memory.md", "自动生成的长期记忆摘要"],
  ["text:reflection", "reflection.md", "阶段性反思和建议"],
  ["json:working_memory", "working_memory.json", "当前工作状态"],
  ["json:state", "state.json", "关系状态和最近互动基调"],
  ["json:facts", "facts.json", "离散长期事实（兼容）"],
  ["json:episodes", "episodes.json", "重要互动片段（兼容）"],
  ["json:conversation", "conversation.json", "短期逐字对话"],
  ["json:memory_candidates", "memory_candidates.json", "待审批记忆候选"],
  ["json:settings", "settings.json", "模型和语音配置"]
];
let data = null;
let current = tabs[0][0];

function el(id){ return document.getElementById(id); }

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadAll() {
  data = await api('/api/context');
  renderNav();
  renderEditor();
  renderStats();
  renderMemStats();
  renderCandidates();
  renderContext();
  setStatus('已读取最新上下文');
}

function renderNav() {
  el('nav').innerHTML = tabs.map(([id, label, hint]) =>
    `<button class="${id===current?'active':''}" onclick="selectTab('${id}')">${label}<br><span class="muted">${hint}</span></button>`
  ).join('');
}

function selectTab(id) {
  current = id;
  renderNav();
  renderEditor();
}

function renderEditor() {
  const [kind, key] = current.split(':');
  const tab = tabs.find(t => t[0] === current);
  el('editorTitle').textContent = tab[1];
  el('editorHint').textContent = tab[2];
  const value = kind === 'text' ? data.text[key] : JSON.stringify(data.json[key], null, 2);
  el('editor').value = value || '';
}

async function saveCurrent() {
  try {
    const [kind, key] = current.split(':');
    const body = {kind, key};
    if (kind === 'text') body.content = el('editor').value;
    else {
      const raw = el('editor').value.trim();
      if (!raw) body.data = ['conversation', 'facts', 'episodes'].includes(key) ? [] : {};
      else body.data = JSON.parse(raw);
    }
    data = await api('/api/save', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    renderStats();
    renderMemStats();
    renderCandidates();
    renderContext();
    renderEditor();
    setStatus('已保存 ' + key);
  } catch (err) {
    setStatus('保存失败：' + err.message, true);
  }
}

async function refreshMemory() {
  data = await api('/api/refresh-memory', {method:'POST'});
  current = 'text:memory';
  renderNav();
  renderEditor();
  renderStats();
  renderMemStats();
  renderCandidates();
  renderContext();
  setStatus('已从 facts/episodes 重新生成 memory.md');
}

function renderStats() {
  el('stats').innerHTML = Object.entries(data.stats).map(([k,v]) => `<div class="stat"><div class="muted">${k}</div><div>${v}</div></div>`).join('');
}

function renderMemStats() {
  const ms = data.memory_stats || {};
  const items = [
    ['记忆流', ms.memory_stream_total || 0],
    ['待审批', ms.candidates_pending || 0],
    ['已批准', ms.candidates_approved || 0],
    ['已拒绝', ms.candidates_rejected || 0],
  ];
  el('memStats').innerHTML = items.map(([k,v]) =>
    `<div class="stat"><div class="muted">${k}</div><div>${v}</div></div>`
  ).join('');
}

function renderCandidates() {
  const candidates = (data.json.memory_candidates || {candidates:[]}).candidates;
  const pending = candidates.filter(c => c.status === 'pending');
  if (!pending.length) {
    el('candidatesList').innerHTML = '<span class="muted">暂无待审批候选</span>';
    return;
  }
  el('candidatesList').innerHTML = pending.map(c =>
    `<div class="msg" style="margin-bottom:6px">
      <div class="msgHead">
        <span><span class="badge">${c.type}</span> <span class="muted">重要性:${c.importance}</span></span>
        <span>
          <button class="mini" onclick="approveCandidate('${c.id}')" style="color:#56d364">✓ 批准</button>
          <button class="mini" onclick="rejectCandidate('${c.id}')" style="color:#ff7b72">✗ 拒绝</button>
        </span>
      </div>
      <pre>${escapeHtml(c.content)}</pre>
      <div class="muted" style="font-size:11px;margin-top:4px">${escapeHtml(c.reason)}</div>
    </div>`
  ).join('');
}

async function approveCandidate(id) {
  data = await api('/api/approve-candidate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({candidate_id:id})});
  renderStats(); renderMemStats(); renderCandidates(); renderContext();
  setStatus('已批准记忆');
}

async function rejectCandidate(id) {
  data = await api('/api/reject-candidate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({candidate_id:id})});
  renderMemStats(); renderCandidates();
  setStatus('已拒绝记忆');
}

async function approveAll() {
  data = await api('/api/approve-all', {method:'POST'});
  current = 'text:memory';
  renderNav(); renderEditor(); renderStats(); renderMemStats(); renderCandidates(); renderContext();
  setStatus('已全部批准');
}

async function refreshMemoryStream() {
  data = await api('/api/refresh-memory-stream', {method:'POST'});
  current = 'text:memory';
  renderNav(); renderEditor(); renderStats(); renderMemStats(); renderCandidates(); renderContext();
  setStatus('已从记忆流重新生成 memory.md');
}

async function refreshReflection() {
  data = await api('/api/refresh-reflection', {method:'POST'});
  current = 'text:reflection';
  renderNav(); renderEditor(); renderStats(); renderMemStats(); renderContext();
  setStatus('已重新生成反思');
}

function renderContext() {
  el('context').innerHTML = data.context.map((m, i) =>
    `<div class="msg">
      <div class="msgHead">
        <div><span class="badge">${i+1}</span><span class="muted">${m.role}${m.name ? ' · ' + m.name : ''}</span></div>
        ${sourceTabButton(m.name)}
      </div>
      <pre>${escapeHtml(m.content || '')}</pre>
    </div>`
  ).join('');
}

function sourceTabButton(name) {
  const map = {
    'soul.txt': 'text:soul',
    'user.md': 'text:user',
    'memory.md': 'text:memory',
    'reflection.md': 'text:reflection',
    'working_memory': 'json:working_memory',
    'state mood': 'json:state',
    'facts.json': 'json:facts',
    'episodes.json': 'json:episodes'
  };
  if (!map[name]) return '';
  return `<button class="mini" onclick="selectTab('${map[name]}')">编辑来源</button>`;
}

async function copyContext() {
  await navigator.clipboard.writeText(JSON.stringify(data.context, null, 2));
  setStatus('上下文已复制');
}

function setStatus(text, isError=false) {
  el('status').textContent = text;
  el('status').className = isError ? 'status err' : 'status';
  setTimeout(() => { if (el('status').textContent === text) el('status').textContent = ''; }, 2500);
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveCurrent();
  }
});

loadAll().catch(err => setStatus('错误：' + err.message, true));
</script>
</body>
</html>"""


class ContextHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self):
        payload = INDEX_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send_html()
        elif path == "/api/context":
            self._send_json(snapshot())
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/save":
                body = self._read_body()
                kind = body.get("kind")
                key = body.get("key")
                if kind == "text" and key in TEXT_FILES:
                    _write_text(TEXT_FILES[key], body.get("content", ""))
                elif kind == "json" and key in JSON_FILES:
                    _write_json(JSON_FILES[key], _normalize_json_for(key, body.get("data")))
                else:
                    self._send_json({"error": "invalid target"}, 400)
                    return
                self._send_json(snapshot())
            elif path == "/api/refresh-memory":
                refresh_memory_markdown()
                self._send_json(snapshot())
            elif path == "/api/refresh-memory-stream":
                mem.refresh_memory_md()
                self._send_json(snapshot())
            elif path == "/api/refresh-reflection":
                conversation = _read_json(JSON_FILES["conversation"], [])
                mem.refresh_reflection(conversation)
                self._send_json(snapshot())
            elif path == "/api/approve-candidate":
                body = self._read_body()
                cid = body.get("candidate_id", "")
                if not cid:
                    self._send_json({"error": "missing candidate_id"}, 400)
                    return
                mem.approve_candidate(cid)
                self._send_json(snapshot())
            elif path == "/api/reject-candidate":
                body = self._read_body()
                cid = body.get("candidate_id", "")
                if not cid:
                    self._send_json({"error": "missing candidate_id"}, 400)
                    return
                mem.reject_candidate(cid)
                self._send_json(snapshot())
            elif path == "/api/approve-all":
                for c in mem.load_candidates("pending"):
                    mem.approve_candidate(c["id"])
                self._send_json(snapshot())
            elif path == "/api/memory-stats":
                self._send_json(mem.get_stats())
            else:
                self._send_json({"error": "not found"}, 404)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        print(f"[context-ui] {self.address_string()} - {fmt % args}")


def main():
    parser = argparse.ArgumentParser(description="Run Xiaoling context web console.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ContextHandler)
    print(f"小灵 Context Console: http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
