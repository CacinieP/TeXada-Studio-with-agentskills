#!/usr/bin/env bash
# 生成提交包：dist/TeXada-WebUI-submission-<date>.zip
# 排除 .git / .venv / state / dist 自身；样本与文档全保留。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d)"
DIST="$REPO_DIR/dist"
mkdir -p "$DIST"
cd "$REPO_DIR"
zip -qr "$DIST/TeXada-WebUI-submission-$STAMP.zip" . \
  -x '.git/*' '.venv/*' 'state/*' 'dist/*' '*.DS_Store' '__pycache__/*' '*/__pycache__/*'
echo "提交包: $DIST/TeXada-WebUI-submission-$STAMP.zip"
unzip -l "$DIST/TeXada-WebUI-submission-$STAMP.zip" | tail -1
