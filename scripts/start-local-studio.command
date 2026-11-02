#!/bin/sh
# Portable double-click entry. Install dependencies explicitly, never silently.
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd -- "$REPO_DIR" || exit 1
if [ -n "${TEXADA_STUDIO_PYTHON:-}" ] && [ -x "$TEXADA_STUDIO_PYTHON" ]; then
  STUDIO_PYTHON=$TEXADA_STUDIO_PYTHON
elif [ -x "$REPO_DIR/.venv/bin/python" ]; then
  STUDIO_PYTHON=$REPO_DIR/.venv/bin/python
else
  printf '%s\n' '未找到项目虚拟环境。请先在此项目目录执行：' \
    'python3.13 -m venv .venv' \
    '.venv/bin/python -m pip install -r webui/requirements.txt' \
    '完成后重新双击此文件。'
  printf '%s' '按回车关闭…'
  read -r STUDIO_REPLY
  exit 2
fi
exec "$STUDIO_PYTHON" "$REPO_DIR/scripts/run-local-studio.py" "$@"
