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

# Load .env for brain module (DeepSeek key etc.)
_env_path = ROOT / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Embedded mode toggle — set True by main.py when it starts the web server.
# When False (standalone), chat won't trigger TTS/face.
EMBEDDED_MODE = False
EMBEDDED_CHAT_HANDLER = None

TEXT_FILES = {
    "soul": CONFIG_DIR / "soul.md",
    "user": CONFIG_DIR / "user.md",
    "memory": MEMORY_DIR / "memory.md",
    "reflection": MEMORY_DIR / "reflection.md",
}

JSON_FILES = {
    "settings": CONFIG_DIR / "settings.json",
    "conversation": MEMORY_DIR / "conversation.json",
    "state": MEMORY_DIR / "state.json",
    "memory_candidates": MEMORY_DIR / "memory_candidates.json",
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
mood 就是小灵此刻该有的表情，是她的内心状态和用户刚才那句话共同折射出来的脸。结合用户这句话、private_state 和上一轮表情，觉得该是什么就选什么。
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
    return _read_text(TEXT_FILES["soul"]).strip() or _read_text(CONFIG_DIR / "soul.md").strip()


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _json_default_for(key: str):
    return [] if key == "conversation" else {}


def _normalize_json_for(key: str, data):
    default = _json_default_for(key)
    if isinstance(default, list):
        return data if isinstance(data, list) else default
    return data if isinstance(data, dict) else default


def assemble_context() -> list[dict[str, str]]:
    soul = _runtime_soul()

    messages = [
        {"role": "system", "name": "soul.md", "content": soul},
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

    messages.extend(_read_json(JSON_FILES["conversation"], []))
    return messages


def snapshot() -> dict:
    text = {key: _read_text(path) for key, path in TEXT_FILES.items()}
    data = {key: _read_json(path, [] if key == "conversation" else {}) for key, path in JSON_FILES.items()}
    context = assemble_context()
    return {
        "text": text,
        "json": data,
        "context": context,
        "stats": {
            "context_messages": len(context),
            "context_chars": sum(len(item.get("content", "")) for item in context),
            "short_term_messages": len(data["conversation"]),
            "memory_stream": len(mem.load_stream()),
        },
        "memory_stats": mem.get_stats(),
        "settings_summary": {
            "speech_output_enabled": bool(data["settings"].get("speech_output_enabled", True)),
            "proactive_enabled": bool(data["settings"].get("proactive_enabled", True)),
            "proactive_idle_seconds": data["settings"].get("proactive_idle_seconds", 60),
        },
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
      <button onclick="refreshMemoryStream()" title="从记忆流+反思+工作状态生成 memory.md">刷新记忆流</button>
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
        <div id="chatPanel" style="display:none;flex-direction:column;height:calc(100vh - 280px);">
          <div id="chatMessages" style="flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:8px;padding:4px 0;"></div>
          <div style="display:flex;gap:6px;padding-top:8px;border-top:1px solid var(--line);margin-top:4px;">
            <input id="chatInput" type="text" style="flex:1;background:#0f1117;border:1px solid var(--line);border-radius:6px;padding:8px 12px;color:var(--text);font-size:14px;outline:none;" placeholder="输入消息，按 Enter 发送..." autofocus>
            <button id="chatSendBtn" style="padding:8px 16px;background:var(--accent);color:#000;border:none;border-radius:6px;cursor:pointer;font-weight:600;">发送</button>
          </div>
          <div id="chatStatus" class="muted" style="padding:4px 0;font-size:11px;min-height:18px;"></div>
        </div>
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
      <div class="panel">
        <div class="row"><div class="title">实际注入上下文</div><button onclick="copyContext()">复制</button></div>
        <div id="context"></div>
      </div>
    </aside>
  </div>
<script>
const tabs = [
  ["text:soul", "soul.md", "人格、输出协议、说话风格"],
  ["chat", "对话", "静默打字聊天"],
  ["text:user", "user.md", "用户画像和长期偏好"],
  ["text:memory", "memory.md", "自动长期记忆"],
  ["json:conversation", "conversation.json", "短期逐字对话"],
  ["json:settings", "settings.json", "模型、语音、主动观察"]
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
  const chatPanel = document.getElementById('chatPanel');
  const editor = document.getElementById('editor');
  if (current === 'chat') {
    chatPanel.style.display = 'flex';
    editor.style.display = 'none';
    el('editorTitle').textContent = '对话';
    el('editorHint').textContent = '静默模式 - 无需语音，直接打字聊天';
    document.getElementById('chatInput').focus();
    return;
  }
  chatPanel.style.display = 'none';
  editor.style.display = '';
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
      if (!raw) body.data = key === 'conversation' ? [] : {};
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

function renderStats() {
  const proactive = data.settings_summary || {};
  const entries = Object.entries(data.stats).concat([
    ['语音输出', proactive.speech_output_enabled ? '开启' : '关闭'],
    ['主动观察', proactive.proactive_enabled ? '开启' : '关闭'],
    ['空闲秒数', proactive.proactive_idle_seconds || 60],
  ]);
  el('stats').innerHTML = entries.map(([k,v]) => `<div class="stat"><div class="muted">${k}</div><div>${v}</div></div>`).join('');
}

function renderMemStats() {
  const ms = data.memory_stats || {};
  const items = [
    ['记忆流', ms.memory_stream_total || 0],
    ['自动记忆', ms.memory_stream_total || 0],
    ['反思', ms.has_reflection ? '有' : '无'],
  ];
  el('memStats').innerHTML = items.map(([k,v]) =>
    `<div class="stat"><div class="muted">${k}</div><div>${v}</div></div>`
  ).join('');
}

function renderCandidates() {
  if (!el('candidatesList')) return;
  const raw = data.json.memory_candidates || [];
  const candidates = Array.isArray(raw) ? raw : (raw.candidates || []);
  const pending = candidates.filter(c => c && c.status === 'pending');
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
    'soul.md': 'text:soul',
    'user.md': 'text:user',
    'memory.md': 'text:memory',
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

// ── Chat ──
let _chatBusy = false;

function addChatBubble(role, content, id) {
  const msgs = document.getElementById('chatMessages');
  const div = document.createElement('div');
  const base = 'padding:10px 14px;border-radius:10px;max-width:88%;line-height:1.6;white-space:pre-wrap;word-break:break-word;font-size:14px;';
  div.style.cssText = role === 'user'
    ? base + 'align-self:flex-end;background:var(--accent);color:#000;'
    : base + 'align-self:flex-start;background:var(--panel);border:1px solid var(--line);';
  div.textContent = content || '';
  if (id) div.id = id;
  msgs.appendChild(div);
  div.scrollIntoView({block:'end',behavior:'smooth'});
}

function updateStreamingMsg(content) {
  const el = document.getElementById('streamingMsg');
  if (el) el.textContent = content || ' ';
}

function setChatStatus(text) {
  document.getElementById('chatStatus').textContent = text;
}

async function sendChat() {
  if (_chatBusy) return;
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';
  _chatBusy = true;
  document.getElementById('chatSendBtn').disabled = true;
  setChatStatus('发送中…');
  addChatBubble('user', msg);
  addChatBubble('assistant', '', 'streamingMsg');
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    if (!res.ok) { setChatStatus('❌ ' + res.status); return; }
    const ct = res.headers.get('Content-Type') || '';
    if (ct.includes('json')) {
      // Embedded mode — JSON response (main.py handles terminal/face/memory/TTS setting)
      const data = await res.json();
      if (data.error) {
        setChatStatus('❌ ' + data.error);
      } else {
        const el = document.getElementById('streamingMsg');
        if (el) { el.textContent = data.reply || ''; el.removeAttribute('id'); }
        setChatStatus('✓');
      }
      return;
    }
    // Standalone mode — SSE streaming
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buf += dec.decode(value, {stream: true});
      const lines = buf.split('\n');
      buf = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const p = line.slice(6).trim();
        if (p === '[DONE]') continue;
        try {
          const d = JSON.parse(p);
          if (d.token) {
            const el = document.getElementById('streamingMsg');
            if (el) el.textContent += d.token;
          }
          else if (d.done) {
            const el = document.getElementById('streamingMsg');
            if (el) { el.textContent = d.clean || ''; el.removeAttribute('id'); }
            setChatStatus('✓');
          }
          else if (d.error) { setChatStatus('❌ ' + d.error); }
        } catch(_) {}
      }
    }
  } catch(err) {
    setChatStatus('❌ 连接失败');
  } finally {
    _chatBusy = false;
    document.getElementById('chatSendBtn').disabled = false;
  }
}

document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveCurrent();
  }
});
document.getElementById('chatSendBtn').addEventListener('click', sendChat);
document.getElementById('chatInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !_chatBusy) {
    e.preventDefault();
    sendChat();
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

    def _handle_chat(self):
        """Chat endpoint. Embedded uses main.py's face/memory handler.
        Standalone calls DeepSeek directly with SSE streaming."""
        body = self._read_body()
        message = body.get("message", "")
        if not message:
            self._send_json({"error": "empty message"}, 400)
            return

        if EMBEDDED_MODE:
            # ── Embedded: main.py injects the real face/mood-aware handler. ──
            try:
                if EMBEDDED_CHAT_HANDLER is None:
                    raise RuntimeError("embedded chat handler is not registered")
                reply = EMBEDDED_CHAT_HANDLER(message)
                self._send_json({"reply": reply})
            except Exception as exc:
                import traceback as _tb
                _tb.print_exc()
                self._send_json({"error": str(exc)}, 500)
        else:
            # ── Standalone: direct DeepSeek + SSE streaming ──
            self._chat_stream_sse(message)

        self.close_connection = True  # avoid thread pile-up on keep-alive

    def _chat_stream_sse(self, message: str):
        """Standalone: call DeepSeek, strip mood JSON, stream tokens via SSE."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        import re as _re
        from .brain import chat_stream, MoodState, _save_turn as _save_chat

        _json_re = _re.compile(r'^\s*\{.*?\}\s*', _re.S)
        _mood = MoodState()
        full_reply = ""
        header_buf = ""
        header_done = False

        try:
            for token in chat_stream(message):
                full_reply += token
                if not header_done:
                    header_buf += token
                    parsed = False
                    if "\n" in header_buf:
                        first_line, rest = header_buf.split("\n", 1)
                        try:
                            _mood.apply_mood(json.loads(first_line.strip()).get("mood", ""))
                            rest = rest.lstrip()
                            parsed = True
                        except json.JSONDecodeError:
                            pass
                    if not parsed and '}' in header_buf:
                        idx = header_buf.index('}')
                        try:
                            _mood.apply_mood(json.loads(header_buf[:idx + 1]).get("mood", ""))
                            rest = header_buf[idx + 1:].lstrip()
                            parsed = True
                        except json.JSONDecodeError:
                            pass
                    if parsed:
                        header_done = True
                        if rest:
                            self.wfile.write(f"data: {json.dumps({'token': rest})}\n\n".encode())
                            self.wfile.flush()
                        continue
                    elif len(header_buf) > 200:
                        header_done = True
                    if not header_done:
                        continue
                self.wfile.write(f"data: {json.dumps({'token': token})}\n\n".encode())
                self.wfile.flush()

            clean = _mood.parse_llm_output(full_reply)
            _jh = _json_re.match(clean)
            if _jh:
                clean = clean[_jh.end():].strip()
            _save_chat(message, clean)
            self.wfile.write(f"data: {json.dumps({'done': True, 'clean': clean})}\n\n".encode())
        except Exception as exc:
            import traceback as _tb
            _tb.print_exc()
            self.wfile.write(f"data: {json.dumps({'error': str(exc)})}\n\n".encode())
        finally:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True

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
                mem.refresh_memory_md()
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
                mem.refresh_memory_md()
                self._send_json(snapshot())
            elif path == "/api/memory-stats":
                self._send_json(mem.get_stats())
            elif path == "/api/chat":
                self._handle_chat()
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
