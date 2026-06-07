#!/bin/bash
# AI Desktop Companion — 一键环境搭建 (macOS MVP)
# 绝不修改任何全局 shell 配置文件

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo "📦 创建 Python 虚拟环境..."
python3 -m venv "$VENV_DIR"

echo "🔧 激活虚拟环境并安装依赖..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements.txt" -q

echo "🔗 修复 SDL2 库冲突 (cv2 ↔ pygame)..."
CV2_DYLIBS=$(python3 -c "import cv2, os; print(os.path.join(os.path.dirname(cv2.__file__), '.dylibs'))")
PY_SDL=$(python3 -c "import pygame; print(pygame.__file__.replace('__init__.py','.dylibs/libSDL2-2.0.0.dylib'))")
AV_DYLIBS=$(python3 -c "import av, os; print(os.path.join(os.path.dirname(av.__file__), '.dylibs'))")

# SDL2: cv2 → pygame
CV2_SDL="$CV2_DYLIBS/libSDL2-2.0.0.dylib"
if [ -f "$CV2_SDL" ] && [ ! -L "$CV2_SDL" ]; then
  rm "$CV2_SDL"
  ln -s "$PY_SDL" "$CV2_SDL"
  echo "   ✓ SDL2 已链接 → pygame"
fi

# avdevice: cv2 → av (faster-whisper dependency)
CV2_AVD=$(ls "$CV2_DYLIBS"/libavdevice.*.dylib 2>/dev/null | head -1)
AV_AVD=$(ls "$AV_DYLIBS"/libavdevice.*.dylib 2>/dev/null | head -1)
if [ -n "$CV2_AVD" ] && [ -n "$AV_AVD" ] && [ ! -L "$CV2_AVD" ]; then
  rm "$CV2_AVD"
  ln -s "$AV_AVD" "$CV2_AVD"
  echo "   ✓ avdevice 已链接 → av"
fi

echo ""
echo "✅ 环境搭建完成！"
echo ""
echo "激活环境: source venv/bin/activate"
echo "启动程序: python -m src.main"
