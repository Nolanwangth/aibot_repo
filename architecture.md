# 架构设计

## 数据流

```
[持续 VAD 监听] → ear.listen_vad() → ear.transcribe() → brain.chat_stream()
       ↑                                                       ↓
  后台线程循环                                            流式输出 token
       ↑                                                       ↓
  [说话可打断 TTS]  ←  mouth.say()  ←  LLM reply  ←  face 状态切换
```

视觉路由（触发词如「看看」「这是什么」）：

```
ear.transcribe() → brain.generate_vision_query() → eye.capture()
                                                        ↓
        brain.chat_with_vision() ← eye.describe() ← Ollama VLM
               ↓
        mouth.say()
```

## 线程模型

| 线程 | 职责 |
|------|------|
| 主线程 | tkinter GUI 动画循环 + 键盘事件（空格暂停，ESC 退出） |
| VAD 线程 | 持续监听 → 转写 → LLM 流式对话 → 触发 TTS |
| TTS 线程 | 后台合成 + 播放，检查 `_stop_flag` 实现可打断 |

TTS 播放期间 VAD 检测到新语音 → `stop_playback()` 打断 → 立即开始新轮。

## 模块边界

| 模块 | 接口函数 | 输入 | 输出 |
|------|----------|------|------|
| ear | `listen_vad()` | 麦克风 | speech np.ndarray 或 None |
| ear | `transcribe(audio)` | np.ndarray | 简体中文文本 |
| brain | `chat_stream(text)` | 文本 | token 生成器 |
| brain | `generate_vision_query(text)` | 文本 | 视觉查询指令 |
| brain | `chat_with_vision(text, desc)` | 文本 + 图像描述 | 回复文本 |
| mouth | `say(text)` | 文本 | 非阻塞播放 |
| mouth | `stop_playback()` | — | 中断播放 |
| mouth | `is_playing()` | — | bool |
| eye | `capture()` | — | (base64 小图, 原图文件路径) |
| eye | `describe(b64, query)` | 图片 + 查询 | 文字描述 |
| face | `set_state(state)` | str | GUI 表情切换 |

## VAD 流程

`ear.listen_vad()` 使用固定阈值 RMS 能量检测，通过 sounddevice 的 `InputStream` 以 30ms 帧持续监听：

1. **waiting** — 等待 SPEECH_FRAMES(3) 个连续高能帧，触发前保留预缓冲
2. **speech** — 持续收集音频，每帧检测 silence
3. **done** — 连续 SILENCE_FRAMES(40) ≈ 1.2s 静音后结束，或 MAX_SPEECH_SECS(30) 硬截断

## STT 流程

`ear.transcribe()` 使用 faster-whisper (base 模型) + 内置 Silero VAD 过滤 + beam_size=3，然后 OpenCC 繁→简转换。Whisper 模型首次运行自动下载缓存。

## LLM 调用

- **DeepSeek API** — OpenAI 兼容 SDK (`https://api.deepseek.com`)
- **模型**: `deepseek-chat`（可通过 `data/config/settings.json` 切换）
- **V4 模型兼容**: `deepseek-v4-flash` / `deepseek-v4-pro` 默认开启 thinking mode，代码显式禁用以避免空内容
- **流式对话**: `chat_stream()` 逐 token yield，终端实时打印
- **视觉 query 生成**: `generate_vision_query()` 将用户口语转为简洁的图像分析指令

## 记忆系统

| 文件 | 内容 | 容量 |
|------|------|------|
| `data/memory/conversation.json` | 短期记忆 — 最近 N 轮原始对话 | 最多 5 轮（10 条消息） |
| `data/memory/facts.json` | 长期事实 — LLM 从对话中提取的离散信息 | 最多 20 条 |
| `data/memory/episodes.json` | 重要片段 — 值得记住的互动时刻 | 最多 15 条 |
| `data/memory/state.json` | 关系状态 — mood（情绪基调） | 单一键值 |

**压缩机制**: 短期记忆超过 5 轮时，最旧的 3 轮被送去 LLM 压缩，提取出事实/片段/情绪，合并进长期存储。日常寒暄会被忽略。事实去重，新事实在最前。

## 上下文构建

每次 LLM 请求的 messages 结构：

```
[system: SOUL 人格设定 — 来自 data/config/soul.txt]
[system: 【最近互动基调】当前情绪]              ← 仅当有 mood
[system: 【关于他你知道这些】事实列表]           ← 最多 10 条
[system: 【你们之间的事】重要片段]               ← 最多 5 条
[user: 第 N-4 轮]
[assistant: 第 N-4 轮]
...最多 5 轮...
[user: 当前输入]
```

视觉模式额外插入一条 `[user: 画面描述 + 用户原话]`。

## TTS

- **合成**: edge-tts（Microsoft 云端神经语音，`zh-CN-XiaoxiaoNeural`）
- **播放**: pygame.mixer.music，后台线程非阻塞
- **打断**: 全局 `_stop_flag`，VAD 检测到新语音时置位，TTS 线程检查后立即停止
- **文本清洗**: 去除括号内容（动作描述不给 TTS 念）

## 视觉

1. OpenCV 拍照 → 保存原图到 `data/photos/`，缩放到 448px 生成 base64
2. Ollama 发送 base64 + query 到本地 VLM (`qwen3.5:2b`)
3. 返回文字描述 → 拼接用户原话送给 LLM
4. macOS 用 AVFoundation 后端，其他平台用默认后端
