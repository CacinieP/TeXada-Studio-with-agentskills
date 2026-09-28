#!/usr/bin/env bash
# 从已提交的 HEAD 生成源码包；不收集工作目录中的上传文档、密钥或缓存。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$REPO_DIR/dist"
mkdir -p "$DIST"
cd "$REPO_DIR"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "请先审阅并提交代码；打包只包含 HEAD，不能包含未提交的修改。" >&2
  exit 1
fi
REV="$(git rev-parse --short HEAD)"
ARCHIVE="$DIST/TeXada-WebUI-$REV.zip"
git archive --format=zip --prefix="TeXada-WebUI-$REV/" --output="$ARCHIVE" HEAD
echo "源码包: $ARCHIVE"
