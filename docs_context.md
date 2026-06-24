# 小灵上下文与记忆设计

## 文件分层

- `data/config/soul.md`：小灵的灵魂层。定义人格、说话风格、输出协议、mood 列表和科研助手边界。人工编辑为主，程序只读取。
- `data/config/user.md`：用户画像层。记录用户长期目标、偏好、身份、研究方向和交互习惯。人工编辑为主，后续可以让记忆压缩器提出候选更新，但不自动覆盖。
- `data/memory/conversation.json`：短期记忆层。保存最近 `SHORT_TERM_TURNS` 轮逐字对话，保证当前交流的连续性。
- `data/memory/facts.json`：长期事实层。保存稳定、可复用、去重后的事实。
- `data/memory/episodes.json`：长期片段层。保存有情绪或关系价值的重要互动。
- `data/memory/state.json`：状态层。保存最近互动基调等轻状态。
- `data/memory/memory.md`：长期记忆摘要层。由 facts、episodes、state 自动生成，给人类和模型都更容易读。

## 合理性原则

- 短期记忆负责“刚刚发生了什么”，保留原话，数量少，重连续性。
- 长期记忆负责“以后还值得知道什么”，不保留完整原话，重稳定性和可复用性。
- `facts.json` 不应该存临时玩笑、角色扮演设定、一次性视觉描述，主要存用户目标、偏好、项目、研究方向、明确要求。
- `episodes.json` 可以存关系节点和科研节点，但要少而精。
- `state.json` 的 `mood` 必须是固定 mood 枚举之一，不能写“开心、兴奋”这类自由文本。
- `memory.md` 是由 JSON 源自动生成的人类可读摘要，不是唯一真源；真源仍然是 `facts.json`、`episodes.json`、`state.json`。

## Mood 与 Face

当前协议只有一个字段：`mood`。

LLM 第一行输出：

```json
{"mood":"focused"}
```

这里的 `focused` 同时也是表情 ID。程序链路是：

1. LLM 输出 `mood`
2. `MoodEngine` 校验 mood 是否在固定枚举里
3. `face.py` 用同一个 mood 名调用 `moods.py` 的渲染器
4. `moods.py` 返回对应像素表情帧

所以现在没有单独的 `face` 字段，也不需要让 LLM 输出 `face`。以后如果想让一个 mood 对应多个表情变体，比如 `focused` 显示“扫描脸”或“冷酷脸”，再在本地代码里加映射，不把复杂度交给 LLM。

## 每轮上下文顺序

1. `soul.md`
2. mood 输出协议
3. `state.json` 中的最近互动基调
4. `user.md`
5. `memory.md`
6. 最近短期对话 `conversation.json`
7. 当前用户输入

如果 `memory.md` 存在，就优先使用它；否则退回注入 `facts.json` 和 `episodes.json`，避免重复上下文。

## 更新机制

- 对话结束后，当前轮写入 `conversation.json`。
- 当短期对话超过上限，溢出的旧对话进入后台压缩任务。
- 后台压缩使用 `settings.json` 的 `compress_model`，默认 `deepseek-v4-flash`。
- 压缩结果合并进 `facts.json`、`episodes.json`、`state.json`。
- 合并完成后自动刷新 `memory.md`。
- 压缩失败不会阻塞当前对话，只打印错误并跳过本次压缩。

## Web UI

运行：

```bash
./run_context_ui.sh
```

默认地址：

```text
http://127.0.0.1:8765
```

管理台可以实时查看和编辑 `soul.md`、`user.md`、`memory.md`、`settings.json`、`state.json`、`facts.json`、`episodes.json`、`conversation.json`，右侧会显示实际注入模型的上下文顺序。
