#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -x "$ROOT/runtime/bin/python" ]; then
  echo "未找到便携运行环境：runtime/bin/python" >&2
  exit 2
fi
exec "$ROOT/runtime/bin/python" "$ROOT/app/portable_launcher.py"

