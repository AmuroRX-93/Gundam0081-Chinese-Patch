#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 launcher.py
else
  echo '请从 python.org 安装 Python 3.9 或以上，再重试。'
  read -r answer
fi
