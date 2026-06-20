# 🤖 小灵 — AI Desktop Companion

桌面 AI 陪伴精灵，能听、能说、能看、有表情。

**v0.3.0** | Python 3.10+ | macOS / Windows WSL2

---

## 快速开始

```bash
# 1. 一键搭建环境（仅首次）
bash setup.sh

# 2. 配置 API Key（.env 不会被提交到 Git，仅首次）
echo "DEEPSEEK_API_KEY=sk-你的key" > .env

# 3. 启动
source venv/bin/activate && export $(cat .env | xargs) && python -m src.main
```

启动后**直接说话即可**，无需按键触发。小灵说话时直接开口就能打断她。

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

编辑 `data/config/` 下的文件即可，重启生效：

| 文件 | 用途 |
|------|------|
| `data/config/settings.json` | 模型选择、TTS 语音 |
| `data/config/soul.txt` | 人格设定 |

记忆文件在 `data/memory/`，删除后小灵就"失忆"了。

---

## 目录结构

```
aibot/
├── src/
│   ├── main.py       # 主循环 — VAD 监听 + 视觉路由 + 快捷键
│   ├── ear.py        # 音频 — RMS VAD + faster-whisper STT + OpenCC 繁转简
│   ├── brain.py      # LLM — DeepSeek + 长短期记忆
│   ├── mouth.py      # TTS — edge-tts 合成 + pygame 播放（可打断）
│   ├── eye.py        # 视觉 — OpenCV 拍照 + Ollama qwen3.5:2b VLM
│   ├── face.py       # GUI — tkinter 全屏动画眼睛
│   └── config.py     # 配置中心
├── data/
│   ├── config/       # 用户可编辑配置
│   ├── memory/       # 对话记忆持久化
│   └── photos/       # 视觉模式拍照
├── docs/             # 设计文档 & 变更日志
├── setup.sh          # 环境搭建脚本
└── requirements.txt  # Python 依赖
```

---

## 技术栈

| 模块 | 选型 |
|------|------|
| VAD | 纯 Python RMS 能量检测 (sounddevice InputStream) |
| STT | faster-whisper (base) + Silero VAD + OpenCC 繁转简 |
| LLM | DeepSeek API (OpenAI SDK)，支持多模型切换 |
| TTS | edge-tts (zh-CN 神经语音) |
| 音频播放 | pygame 后台线程，非阻塞，可打断 |
| 视觉 | opencv-python + Ollama qwen3.5:2b |
| GUI | tkinter 全屏动画眼睛 |

---

## Windows 用户

参考 [WSL2_SETUP.md](./WSL2_SETUP.md)。
