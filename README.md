# 🤖 小灵 — AI Desktop Companion

桌面 AI 陪伴精灵，能听、能说、能看、有像素风表情。

**v0.4.0** | Python 3.11+ | macOS

---

## 快速开始

```bash
# 1. 一键搭建环境（仅首次）
bash setup.sh

# 2. 配置 API Key
export DEEPSEEK_API_KEY=sk-xxx
# 或写入项目根目录 .env 文件

# 3. 启动
./run.sh
```

启动后**直接说话即可**，说完自动识别。小灵说话时直接开口就能打断她。

---

## 调试管理台

对话上下文实时查看和编辑（运行在小灵之外的可选工具）：

```bash
./run_context_ui.sh
```

默认地址：**http://127.0.0.1:8765**

管理台功能：
- 实时查看实际注入 LLM 的完整上下文（soul + mood 协议 + 记忆 + 对话轮次）
- 编辑 soul.txt、user.md、settings.json
- 查看和审批记忆候选条目（memory candidates）
- 查看记忆统计（fact / episode / stream 数量）
- 实时查看 conversation.json、facts.json、episodes.json

---

## 键盘 & 交互

| 操作 | 方式 |
|------|------|
| 对话 | 直接说话，说完自动识别 |
| 打断小灵 | 她说话时直接开口 |
| 暂停/恢复监听 | **空格** |
| 退出 | **ESC** |

说出「看看」「这是什么」「面前有什么」「拍」等关键词触发视觉模式。

---

## 个性化配置

编辑 `data/config/` 下的文件，重启生效：

| 文件 | 用途 |
|------|------|
| `data/config/settings.json` | DeepSeek 模型选择、TTS 语音 |
| `data/config/soul.txt` | 人格设定 + mood 表情输出协议 |

记忆文件在 `data/memory/`，删除后小灵就"失忆"了。

---

## 目录结构

```
aibot/
├── src/
│   ├── main.py           # 主循环 — VAD 监听 + 视觉路由 + 表情编排
│   ├── ear.py            # 音频 — RMS VAD + faster-whisper + Silero + OpenCC
│   ├── brain.py          # LLM — DeepSeek 流式对话 + MoodEngine + 分层记忆
│   ├── mouth.py          # TTS — edge-tts 合成 + pygame 后台播放（可打断）
│   ├── eye.py            # 视觉 — OpenCV 拍照 + Agnes Vision API
│   ├── face.py           # GUI — tkinter 像素风动画表情（24×20 像素网格）
│   ├── moods.py          # 15 种表情像素定义 + 渲染引擎 + cross-fade
│   ├── memory_manager.py # 新版记忆系统（记忆流 + working memory）
│   ├── context_ui.py     # Web 管理台（本地 HTTP，实时查看/编辑配置和上下文）
│   └── config.py         # 配置中心
├── data/
│   ├── config/           # 用户可编辑配置
│   ├── memory/           # 对话记忆持久化（gitignore）
│   └── photos/           # 视觉模式拍照（gitignore）
├── setup.sh              # macOS 环境搭建
├── requirements.txt      # Python 依赖
└── README.md
```

---

## 技术栈

| 模块 | 选型 |
|------|------|
| VAD | 纯 Python RMS 能量检测 (sounddevice InputStream) |
| STT | faster-whisper (base) + Silero VAD + OpenCC 繁转简 |
| LLM | DeepSeek API (OpenAI SDK)，流式输出 |
| TTS | edge-tts (zh-CN 神经语音) |
| 音频播放 | pygame 后台线程，非阻塞，可打断 |
| 视觉 | OpenCV 拍照 + Agnes Vision API（多模态理解） |
| 表情 | PIL 逐像素渲染 → tkinter 动画，24×20 网格 ×6x 缩放，15 种表情，cross-fade 过渡 |
| GUI | tkinter 动画窗口，30fps，粒子背景 |
