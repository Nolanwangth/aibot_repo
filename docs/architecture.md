# 架构设计

## 数据流

```
[持续 VAD 监听] → ear.listen_vad() → ear.transcribe() → brain.chat_stream()
       ↑                                                       ↓
  后台线程循环                                          流式输出 token
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
| 主线程 | tkinter GUI 动画循环 + 键盘事件 |
| VAD 线程 | 持续监听 → 转写 → 同步调用 LLM → 触发 TTS |
| TTS 线程 | 后台合成 + 播放，检查 `_stop_flag` 实现可打断 |

TTS 播放期间 VAD 检测到新语音 → `stop_playback()` 打断 → 立即开始新轮。

## 模块边界

| 模块 | 接口函数 | 输入 | 输出 |
|------|----------|------|------|
| ear | `listen_vad()` | 麦克风 | speech np.ndarray |
| ear | `transcribe(audio)` | np.ndarray | 简体中文文本 |
| brain | `chat_stream(text)` | 文本 | token 生成器 |
| brain | `generate_vision_query(text)` | 文本 | 视觉查询指令 |
| brain | `chat_with_vision(text, desc)` | 文本+描述 | 回复文本 |
| mouth | `say(text)` | 文本 | 非阻塞播放 |
| mouth | `stop_playback()` | — | 中断播放 |
| mouth | `is_playing()` | — | bool |
| eye | `capture()` | — | (base64, 文件路径) |
| eye | `describe(b64, query)` | 图片+查询 | 文字描述 |
| face | `set_state(state)` | str | GUI 表情切换 |

## 记忆系统

- **短期记忆**: JSON 文件，保留最近 5 轮对话（10 条消息），每次请求随上下文发往 LLM
- **长期记忆**: 纯文本文件，由 LLM 将溢出的旧对话压缩为 2-3 句摘要
- **压缩触发**: 短期记忆超过 5 轮时，最旧的 3 轮被送去压缩，合并进长期记忆

## 上下文构建

每次 LLM 请求的 messages 结构：

```
[system: SOUL 人格设定]
[system: 长期记忆摘要]      ← 仅当有内容时
[user: 第 N-4 轮]
[assistant: 第 N-4 轮]
...最多 5 轮...
[user: 当前输入]
```

视觉模式会额外插入一条 `[user: 画面描述 + 用户原话]`。
