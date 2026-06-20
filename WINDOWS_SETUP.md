# 🪟 Windows 原生部署指南

本指南帮助你在 Windows 10/11 上从零部署「小灵」AI 桌面陪伴精灵。

**不需要 WSL2。** Python、音频、摄像头、Ollama 均为 Windows 原生。

---

## 环境概览

| 组件 | 说明 | 运行位置 |
|------|------|----------|
| Python 3.10+ | 主程序 | Windows 原生 |
| DeepSeek API | LLM 大脑 | 云端 |
| Ollama + qwen3.5:2b | 视觉理解 | Windows 原生 |
| Edge TTS | 语音合成 | 云端 |
| 麦克风 / 摄像头 | 音频 & 拍照 | Windows 原生 |

---

## 1. 安装 Python

从 [python.org](https://www.python.org/downloads/) 下载 Python 3.10+ 安装包。

> ⚠️ 安装时**务必勾选** "Add Python to PATH"。

验证：

```powershell
python --version
# 应输出 Python 3.10.x / 3.11.x / 3.12.x / 3.13.x
```

---

## 2. 克隆项目

```powershell
cd %USERPROFILE%
git clone https://github.com/Nolanwangth/aibot_repo.git
cd aibot
```

或者手动下载 ZIP 解压到 `C:\Users\<你的用户名>\aibot`。

---

## 3. 创建虚拟环境 & 安装依赖

```powershell
# 创建虚拟环境
python -m venv venv

# 激活
venv\Scripts\activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 安装 OpenCC（繁简转换，requirements 里没有，需要补装）
pip install opencc-python-reimplemented
```

---

## 4. 配置 DeepSeek API Key 🔑

```powershell
# 在项目根目录创建 .env 文件
echo DEEPSEEK_API_KEY=sk-你的key > .env
```

`.env` 已在 `.gitignore` 中，不会被提交到 Git。

> 没有 API Key？去 [platform.deepseek.com](https://platform.deepseek.com) 注册获取。

---

## 5. 安装 Ollama（视觉功能）

1. 从 [ollama.com](https://ollama.com/download/windows) 下载 Windows 安装包
2. 安装后 Ollama 会自动在后台运行（托盘图标）
3. 拉取视觉模型：

```powershell
ollama pull qwen3.5:2b
```

验证：

```powershell
ollama list
# 应显示 qwen3.5:2b
```

> 如果不需要视觉模式（拍照识别物体），可以跳过这步。语音聊天不受影响。

---

## 6. 启动！

```powershell
# 激活虚拟环境
venv\Scripts\activate

# 加载环境变量并启动
for /f "tokens=*" %i in (.env) do set %i
python -m src.main
```

或者写成一个批处理文件 `start.bat`：

```batch
@echo off
call venv\Scripts\activate
for /f "tokens=*" %%i in (.env) do set %%i
python -m src.main
```

放在项目根目录，双击即可运行。

---

## 快捷键 & 交互

| 操作 | 方式 |
|------|------|
| 对话 | 直接说话，说完自动识别 |
| 打断小灵 | 她说话时直接开口 |
| 暂停/恢复监听 | **空格** |
| 退出 | **ESC** |

说出「看看」「这是什么」「拍」等关键词触发视觉模式。

---

## 目录结构（部署后）

```
aibot/
├── venv/                  # Python 虚拟环境（gitignore）
├── src/
│   ├── main.py            # 主程序入口
│   ├── ear.py             # 语音识别（VAD + faster-whisper）
│   ├── brain.py           # LLM 大脑（DeepSeek API）
│   ├── mouth.py           # 语音合成（edge-tts + pygame）
│   ├── eye.py             # 计算机视觉（OpenCV + Ollama VLM）
│   ├── face.py            # 动画表情（tkinter）
│   └── config.py          # 配置加载
├── data/
│   ├── config/            # 用户可编辑配置
│   │   ├── settings.json  # 模型 & 语音设置
│   │   └── soul.txt       # 人设提示词
│   ├── memory/            # 运行时记忆（gitignore）
│   └── photos/            # 运行时拍照（gitignore）
├── requirements.txt       # Python 依赖
├── .env                   # API Key（手动创建，gitignore）
├── .gitignore
├── README.md
└── WINDOWS_SETUP.md       # 本指南
```

---

## 常见问题

### Q: `python` 命令找不到
安装 Python 时没勾选 "Add Python to PATH"。重新运行安装程序，选 "Modify" 然后勾上。

### Q: tkinter 相关报错
Windows 版 Python 安装包自带 tkinter，确认用的是 python.org 的安装包而不是 Microsoft Store 版。

### Q: 麦克风没反应
- 确认麦克风已在 Windows 设置中启用
- 检查隐私设置：设置 → 隐私 → 麦克风 → 允许桌面应用访问

### Q: 摄像头打不开
- 检查隐私设置：设置 → 隐私 → 摄像头 → 允许桌面应用访问
- 确认没有其他程序占用摄像头

### Q: Ollama 下载模型慢
模型约 2GB，耐心等待或挂代理。

### Q: 不需要视觉模式怎么禁用？
编辑 `src/main.py`，删除 `VISION_TRIGGERS` 列表里的所有中文关键词即可。

### Q: 如何确认 API Key 没被提交到 Git？
```powershell
git status   # .env 不应出现在列表中
```
