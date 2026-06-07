# 变更日志

## [0.3.0] — 2026-06-01

### Added
- always-on VAD 语音监听 — 纯 Python RMS 能量检测，无需按键触发
- 语音打断 — TTS 播放时说话自动中断并开始新轮
- 长短期记忆系统 — 5 轮短期记忆 + LLM 自动压缩为长期摘要
- 模型切换 — `data/config/settings.json` 可选模型，支持 deepseek-v4-pro
- OpenCC 繁转简 — faster-whisper 输出自动转简体中文

### Changed
- 交互模型改为持续监听，空格改为暂停/恢复
- TTS 播放改为后台线程非阻塞模式
- 上下文构建改为 [soul + 长期记忆 + 短期记忆 + 当前输入]
- whisper 转写加入 Silero VAD 过滤，beam_size 降为 3 提速
- 删除 pynput 依赖，键盘事件改用 tkinter 原生绑定

### Fixed
- deepseek-v4-pro 返回空内容 (thinking mode 默认开启，需显式禁用)
- macOS Core Audio -50 错误 (int16 替代 float32 录音)
- edge-tts SSML 导致乱码 (改用纯文本)

## [0.2.0] — 2026-06-01

### Added
- `src/eye.py` — OpenCV 摄像头拍照 + Ollama qwen3.5:2b 本地 VLM 图像理解
- `src/face.py` — tkinter 全屏动态卡通眼睛（idle/listening/thinking/happy/speaking）
- `src/brain.py` — `generate_vision_query()` + `chat_with_vision()` 视觉管线
- `src/main.py` — 视觉触发关键词检测 + 视觉/对话双路由

### Changed
- `src/ear.py` — int16 替代 float32 录音，修复 macOS Core Audio -50 错误
- `src/main.py` — tkinter 主线程架构

## [0.1.0] — 2026-06-01

### Added
- 项目初始化，git 仓库创建
- venv 虚拟环境搭建脚本 `setup.sh`
- `src/config.py` — 集中配置管理
- `src/ear.py` — 麦克风录音 + faster-whisper 转写
- `src/brain.py` — DeepSeek API 对话 + 记忆管理
- `src/mouth.py` — edge-tts 合成 + pygame 播放
- `src/main.py` — 主循环编排
- `docs/` — 项目文档目录
