#!/bin/sh
cd -- "$(dirname -- "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 installer/launcher.py
else
  echo '请先安装 Python 3.9 或更高版本。'
  read answer
  exit 1
fi
