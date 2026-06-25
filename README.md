# 🤖 小灵 — AI Desktop Companion

桌面 AI 陪伴精灵，能听、能说、能看、有像素风表情。

**v0.4.0** | Python 3.11+ | macOS

---

## 快速开始

```bash
cd /Users/nolan/Desktop/agi/aibot
bash setup.sh     # 首次：搭建环境（创建 venv + 装依赖）
./run.sh          # 启动小灵
```

启动后**直接说话即可**，说完自动识别。小灵说话时直接开口就能打断她。

### 键盘交互

| 操作 | 方式 |
|------|------|
| 对话 | 直接说话，说完自动识别 |
| 打断小灵 | 她说话时直接开口 |
| 暂停/恢复监听 | **空格键** |
| 退出 | **ESC** |

说出「看看」「这是什么」「面前有什么」「拍」等关键词触发视觉模式（拍照 + 多模态理解）。

---

## Web 管理台（Context Console）

**小灵启动后自动运行**，浏览器打开即可使用：

[http://127.0.0.1:8765](http://127.0.0.1:8765)

左侧点 **「对话」** 可打字聊天（静默模式，无需语音），其他功能：

- **上下文检查** — 实时查看实际注入 LLM 的完整上下文（soul + mood 协议 + 长期记忆 + 对话轮次）
- **在线编辑** — 编辑 `soul.txt`（人格设定）、`user.md`（用户画像）、`settings.json`（模型/语音配置）
- **记忆审批** — 查看并批准/拒绝 DeepSeek 自动生成的记忆候选（facts、episodes）
- **记忆系统** — 查看记忆流统计，手动触发记忆流刷新和反思生成
- **数据巡检** — 查看 `conversation.json`、`facts.json`、`episodes.json`、`working_memory.json` 等原始数据

### 手动启动

```bash
source venv/bin/activate
python -m src.context_ui --host 127.0.0.1 --port 8765
```

---

## 个性化配置

编辑 `data/config/` 下的文件（可通过 Web 管理台在线编辑）：

| 文件 | 用途 |
|------|------|
| `settings.json` | DeepSeek 模型选择（`model`）、压缩模型（`compress_model`）、TTS 语音（`tts_voice`） |
| `soul.txt` | 人格设定 + mood 表情输出协议，决定小灵的性格和说话风格 |
| `user.md` | 用户画像和长期偏好 |

记忆文件在 `data/memory/`，删除后小灵就"失忆"了。

---

## 目录结构

```
aibot/
├── src/
│   ├── main.py           # 主循环 — VAD 监听 + 视觉路由 + 表情编排
│   ├── ear.py            # 音频 — RMS VAD + faster-whisper + Silero + OpenCC
│   ├── brain.py          # LLM — DeepSeek 流式对话 + MoodEngine + 记忆压缩
│   ├── mouth.py          # TTS — edge-tts 合成 + pygame 后台播放（可打断）
│   ├── eye.py            # 视觉 — OpenCV 拍照 + Agnes Vision API
│   ├── face.py           # GUI — tkinter 像素风动画表情（24×20 像素网格）
│   ├── moods.py          # 15 种表情像素定义 + 渲染引擎 + cross-fade
│   ├── memory_manager.py # 记忆系统（记忆流 + working memory + 候选审批）
│   ├── context_ui.py     # Web 管理台（本地 HTTP，实时查看/编辑配置和上下文）
│   └── config.py         # 配置中心（模型、文件路径、Key 管理）
├── data/
│   ├── config/           # 用户可编辑配置（soul.txt、user.md、settings.json）
│   ├── memory/           # 对话记忆持久化（gitignore）
│   └── photos/           # 视觉模式拍照（gitignore）
├── setup.sh              # macOS 环境搭建（venv + pip + SDL2 修复）
├── run.sh                # 一键启动小灵
├── run_context_ui.sh     # 一键启动 Web 管理台
├── requirements.txt      # Python 依赖
└── README.md
```

---

## 技术栈

| 模块 | 选型 |
|------|------|
| VAD | 纯 Python RMS 能量检测 (sounddevice InputStream) |
| STT | faster-whisper (base) + Silero VAD + OpenCC 繁转简 |
| LLM | DeepSeek API (OpenAI SDK)，流式输出 + 记忆压缩 |
| TTS | edge-tts (zh-CN 神经语音) |
| 音频播放 | pygame 后台线程，非阻塞，可打断 |
| 视觉 | OpenCV 拍照 + Agnes Vision API（多模态理解） |
| 表情 | PIL 逐像素渲染 → tkinter 动画，24×20 网格 ×6x 缩放，15 种表情，cross-fade 过渡 |
| GUI | tkinter 动画窗口，30fps，粒子背景 |
