#!/bin/zsh
cd -- "${0:A:h}"
case "$(uname -m)" in
 arm64) PATCH_PY="./runtime/macos-arm64/python/bin/python3" ;;
 x86_64) PATCH_PY="./runtime/macos-x64/python/bin/python3" ;;
 *) echo "不支持的架构"; exit 1 ;;
esac
chmod +x "$PATCH_PY"
"$PATCH_PY" -E -s -B install.py "$@"
PATCH_EXIT=$?
read -r "?按回车关闭"
exit $PATCH_EXIT
