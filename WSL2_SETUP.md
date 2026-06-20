# 🤖 小灵 — WSL2 (Windows) 部署指南

本指南帮助你在 Windows 的 WSL2 (Ubuntu) 环境下从零部署「小灵」AI 桌面陪伴精灵。

---

## 📋 环境概览

| 组件 | 用途 | 运行位置 |
|------|------|----------|
| Python 3.10+ | 主程序运行 | WSL2 |
| DeepSeek API | LLM 大脑（云端） | 云端 |
| Ollama + qwen3.5:2b | 视觉理解（本地） | WSL2 |
| Edge TTS | 语音合成（云端） | 云端 |
| Windows 麦克风/摄像头 | 音频输入 & 拍照 | Windows → WSL2 |

> **⚠️ 重要提示：** 本项目最初为 macOS 开发，WSL2 下有几个地方需要调整，请务必阅读「平台适配」章节。

---

## 1. 安装 WSL2

以 **管理员身份** 打开 PowerShell 或 Windows Terminal，执行：

```powershell
# 安装 WSL2 + Ubuntu
wsl --install -d Ubuntu-24.04
```

安装完成后重启电脑。首次进入 Ubuntu 时会提示创建用户名和密码。

> 建议使用 Windows 11（自带 WSLg，支持 GUI 直接显示）。Windows 10 用户需额外配置 X Server。

---

## 2. 安装 Python 和系统依赖

进入 WSL2 Ubuntu 终端：

```bash
# 更新包管理器
sudo apt update && sudo apt upgrade -y

# 安装 Python 和基础工具
sudo apt install -y python3 python3-pip python3-venv python3-tk

# 安装音频依赖（sounddevice 需要 PortAudio）
sudo apt install -y portaudio19-dev

# 安装 OpenCV 系统依赖
sudo apt install -y libgl1-mesa-glx libglib2.0-0

# 安装 SDL2（pygame 音频播放需要）
sudo apt install -y libsdl2-2.0-0 libsdl2-mixer-2.0-0
```

---

## 3. 克隆项目

```bash
cd ~
git clone <你的仓库地址> aibot
cd aibot
```

---

## 4. 创建虚拟环境并安装 Python 依赖

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt

# 额外安装 OpenCC（繁简转换，requirements 里没有）
pip install opencc
```

> **说明：** 原项目的 `setup.sh` 是 macOS 专属脚本（包含 .dylib 库链接），在 Linux/WSL2 下不需要执行，直接按上述步骤操作即可。Linux 下 SDL2 通过 apt 安装为系统库，不会出现 macOS 那种 cv2 和 pygame 之间的 SDL2 冲突。

---

## 5. 配置 DeepSeek API Key 🔑

> **🔐 API Key 绝对不能提交到 Git！** 使用 `.env` 文件管理。

### 方法一：创建 `.env` 文件（推荐）

```bash
# 在项目根目录创建 .env 文件
echo 'DEEPSEEK_API_KEY=sk-your-actual-key-here' > .env
```

然后在运行前加载：

```bash
export $(cat .env | xargs)
```

`.env` 已被 `.gitignore` 忽略，不会提交到 Git。你也可以在 `~/.bashrc` 中添加自动加载：

```bash
echo 'export $(cat ~/aibot/.env | xargs) 2>/dev/null' >> ~/.bashrc
source ~/.bashrc
```

### 方法二：直接设置环境变量

```bash
export DEEPSEEK_API_KEY="sk-your-actual-key-here"
```

每次打开新终端都需要重新执行，建议添加到 `~/.bashrc`：

```bash
echo 'export DEEPSEEK_API_KEY="sk-your-actual-key-here"' >> ~/.bashrc
source ~/.bashrc
```

### 获取 API Key

1. 访问 [platform.deepseek.com](https://platform.deepseek.com)
2. 注册 / 登录
3. 进入 API Keys 页面，创建新 Key
4. 复制 Key（以 `sk-` 开头）

---

## 6. 安装和配置 Ollama（本地视觉模型）

```bash
# 安装 Ollama（Linux 一键脚本）
curl -fsSL https://ollama.ai/install.sh | sh

# 启动 Ollama 服务（后台运行）
ollama serve &

# 拉取视觉模型（约 2GB，需要一段时间）
ollama pull qwen3.5:2b
```

验证 Ollama 是否正常运行：

```bash
curl http://localhost:11434/api/tags
```

应该返回包含 `qwen3.5:2b` 的 JSON。

> **注意：** 每次重启 WSL2 后需要重新执行 `ollama serve &`。可以加到 `~/.bashrc` 中自动启动：
> ```bash
> echo 'ollama serve &>/dev/null &' >> ~/.bashrc
> ```

---

## 7. WSL2 平台适配（重要！）

原代码有两个 macOS 专属的地方需要修改。

### 7.1 修改摄像头后端

编辑 `src/eye.py`，找到第 15 行：

```python
backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
```

这行已经处理了非 macOS 的情况（fallback 到 `cv2.CAP_ANY`），所以在 Linux 下会自动使用 V4L2 后端，**无需修改**。

### 7.2 修改图片查看命令

编辑 `src/eye.py`，找到第 80 行：

```python
subprocess.Popen(["open", path])
```

改为：

```python
subprocess.Popen(["xdg-open", path])
```

或者跨平台写法（替换那一个函数）：

```python
def show_photo(path: str) -> None:
    """Open photo with system viewer so user can see what was captured."""
    import platform
    if platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    elif platform.system() == "Windows":
        # 如果在 WSL 中，用 PowerShell 打开
        # WSL 中 Windows 可执行文件在 PATH 中
        subprocess.Popen(["powershell.exe", "Start-Process", path])
    else:
        subprocess.Popen(["xdg-open", path])
```

### 7.3 配置项目设置

检查 `data/config/settings.json`，根据你的需求调整：

```json
{
  "model": "deepseek-chat",
  "tts_voice": "zh-CN-XiaoxiaoNeural"
}
```

> `deepseek-chat` 是标准模型，如需使用其他模型可改为 `deepseek-v4-pro` 等。

`data/config/soul.txt` 是人设文件，可按喜好修改，不需要动。

---

## 8. 配置 WSL2 音频（麦克风 + 扬声器）

WSL2 默认没有音频支持，需要配置 PulseAudio。

### 8.1 Windows 端安装 PulseAudio 服务

1. 下载 PulseAudio for Windows：https://www.freedesktop.org/wiki/Software/PulseAudio/Ports/Windows/Support/
   - 或者下载预编译版：https://github.com/GeorgeMDX/PulseAudio-for-Windows/releases

2. 解压到 `C:\pulseaudio\`

3. 编辑 `C:\pulseaudio\etc\pulse\default.pa`，找到并取消注释 / 添加：

   ```
   load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1;172.16.0.0/12
   load-module module-esound-protocol-tcp auth-ip-acl=127.0.0.1;172.16.0.0/12
   ```

4. 编辑 `C:\pulseaudio\etc\pulse\daemon.conf`，设置：

   ```
   exit-idle-time = -1
   ```

5. 以管理员身份运行 `C:\pulseaudio\bin\pulseaudio.exe`

### 8.2 WSL2 端配置

```bash
# 安装 PulseAudio 客户端
sudo apt install -y pulseaudio-utils

# 配置 PulseAudio 连接到 Windows 服务端
echo 'export PULSE_SERVER=tcp:$(grep nameserver /etc/resolv.conf | awk "{print \$2}")' >> ~/.bashrc
echo 'export PULSE_SERVER=tcp:$(ip route show default | awk "{print \$3}")' >> ~/.bashrc
source ~/.bashrc
```

### 8.3 测试音频

```bash
# 测试麦克风
parecord --channels=1 --rate=16000 --format=s16le test.wav

# 测试扬声器
paplay /usr/share/sounds/alsa/Front_Center.wav
```

---

## 9. 配置 WSL2 摄像头

WSL2 默认不直接支持 USB 摄像头。有以下几种方案：

### 方案 A：使用 usbipd-win（USB 摄像头直通）

```powershell
# 在 Windows PowerShell（管理员）中安装
winget install dorssel.usbipd-win
```

```bash
# 在 WSL2 中安装
sudo apt install -y linux-tools-generic hwdata
sudo update-alternatives --install /usr/local/bin/usbip usbip /usr/lib/linux-tools/*-generic/usbip 20
```

使用步骤：
1. 在 Windows PowerShell（管理员）中列出 USB 设备：`usbipd list`
2. 找到摄像头的 BUSID，绑定：`usbipd bind --busid <BUSID>`
3. 附加到 WSL：`usbipd attach --wsl --busid <BUSID>`
4. 在 WSL 中验证：`ls /dev/video*`

每次重启 WSL 后需要重新 `usbipd attach`。

### 方案 B：不使用摄像头

如果你暂时不需要视觉功能（拍照识别），可以跳过摄像头配置。语音对话功能依然可用。

程序在检测不到摄像头时会报错，但可以在代码中跳过视觉模式，只使用语音聊天。

### 方案 C：使用 Windows 端摄像头 + 桥接

通过 OpenCV 直接使用 Windows 摄像头比较复杂，建议先用方案 A 或 B。

---

## 10. 运行「小灵」

```bash
cd ~/aibot
source venv/bin/activate

# 确保 Ollama 在运行
ollama serve &

# 确保环境变量已加载
export $(cat .env | xargs)

# 启动！
python -m src.main
```

### 快捷键

| 按键 | 功能 |
|------|------|
| **空格** | 暂停 / 恢复麦克风监听 |
| **ESC** | 退出程序 |

### 交互方式

- 直接说话，说完停顿 1-2 秒，自动识别转文字
- 小灵说话时直接开口能打断她
- 说出「看看」「这是什么」「拍」等关键词触发视觉模式

---

## 11. 自启动脚本（可选）

创建 `~/aibot/start.sh`：

```bash
#!/bin/bash
cd ~/aibot
source venv/bin/activate
export $(cat .env | xargs)
ollama serve &>/dev/null &
sleep 2
python -m src.main
```

```bash
chmod +x ~/aibot/start.sh
```

---

## 12. 常见问题

### Q: `sounddevice` 报 PortAudio 错误
```bash
sudo apt install -y portaudio19-dev
pip install --force-reinstall sounddevice
```

### Q: tkinter 找不到 / GUI 无法显示
- Windows 11：确保 WSLg 已启用（`wsl --update`）
- Windows 10：需要安装 X Server（如 VcXsrv），并设置 `export DISPLAY=:0`

### Q: Ollama 模型下载慢
- 可以挂代理或者耐心等待，模型约 2GB
- 也可以尝试更小的模型：`ollama pull qwen3:2b`（无视觉能力）

### Q: `faster-whisper` 首次运行慢
- 首次运行会下载 Whisper base 模型（~140MB），之后会缓存

### Q: 麦克风没声音
- 检查 PulseAudio 是否在 Windows 端运行
- 在 WSL2 中执行 `pactl info` 查看是否连接到 PulseAudio Server

### Q: 可以不用摄像头吗？
- 可以。纯语音聊天不需要摄像头。说出视觉触发词时报错是正常的，此时重启程序并只说非视觉相关的话即可。
- 或者在 `src/main.py` 的 `VISION_TRIGGERS` 列表中删除所有视觉触发词，这样就不会进入视觉模式。

### Q: 如何确认 API Key 没被提交到 Git？
```bash
git status          # 确认 .env 不在暂存区
cat .gitignore      # 确认 .env 在忽略列表中
```
`.env` 已在项目的 `.gitignore` 中，不会被提交。

---

## 📁 项目目录结构（部署后）

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
│   ├── config/
│   │   ├── settings.json  # 模型 & 语音设置
│   │   └── soul.txt       # 人设提示词
│   ├── memory/            # 运行时记忆（gitignore）
│   └── photos/            # 运行时拍照（gitignore）
├── requirements.txt       # Python 依赖
├── .env                   # API Key（手动创建，gitignore）
├── .gitignore
├── CLAUDE.md
└── WSL2_SETUP.md          # 本指南
```

---

有任何问题随时问我，祝朋友部署顺利！🎉
