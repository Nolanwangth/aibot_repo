# AI Desktop Companion (aibot)

桌面 AI 陪伴精灵 — 能听、能说、能看、有表情的互动程序。

## 当前阶段

**Phase 2**: always-on VAD 语音交互 + 视觉 + 动画 GUI + 语音打断。

## 快速开始

```bash
# 1. 一键搭建环境
bash setup.sh

# 2. 激活虚拟环境
source venv/bin/activate

# 3. 启动
python -m src.main
```

启动后**直接说话即可**，无需按键触发。小灵说话时直接开口就能打断她。

| 操作 | 按键 |
|------|------|
| 暂停/恢复监听 | 空格 |
| 退出 | ESC |

说出「看看」「这是什么」「面前有什么」等触发视觉模式。

## 个性化配置

编辑 `data/config/` 下的文件即可，重启生效：

| 文件 | 用途 |
|------|------|
| `data/config/settings.json` | 模型选择、TTS 语音 |
| `data/config/soul.txt` | 人格设定（女友角色） |

记忆文件在 `data/memory/`，删除后小灵就"失忆"了。

## 目录结构

```
aibot/
├── src/
│   ├── main.py       # 主循环 — VAD 监听 + 视觉路由
│   ├── ear.py        # 音频输入 — VAD + faster-whisper STT
│   ├── brain.py      # LLM 中枢 — DeepSeek + 长短期记忆
│   ├── mouth.py      # TTS — edge-tts 合成 + pygame 播放
│   ├── eye.py        # 视觉 — 摄像头拍照 + Ollama VLM
│   ├── face.py       # GUI — tkinter 全屏动画眼睛
│   └── config.py     # 配置中心 — 加载外部配置
├── data/
│   ├── config/       # 用户可编辑的配置
│   ├── memory/       # 对话记忆持久化
│   └── photos/       # 视觉模式拍照留存
├── docs/             # 设计文档
├── setup.sh          # 环境搭建脚本
└── requirements.txt  # Python 依赖
```

## 技术栈

| 模块 | 选型 |
|------|------|
| VAD | 纯 Python RMS 能量检测 (sounddevice InputStream) |
| STT | faster-whisper (base) + Silero VAD + OpenCC 繁转简 |
| LLM | DeepSeek (OpenAI SDK), 支持 v4-pro 等多模型切换 |
| TTS | edge-tts (zh-CN 神经语音) |
| 音频播放 | pygame (后台线程非阻塞) |
| 视觉 | opencv-python + Ollama qwen3.5:2b |
| GUI | tkinter 全屏动画眼睛 |
