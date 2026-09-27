#!/usr/bin/env bash
# git bundle 本地备份：全量打包到仓库同级 ../_backups/<repo>/ 时间戳文件。
# 用法: scripts/backup.sh   （恢复: git clone <bundle> <dir>）
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="$(dirname "$REPO_DIR")/_backups/$(basename "$REPO_DIR")"
STAMP="$(date +%Y%m%d-%H%M%S)"
BUNDLE="${BACKUP_DIR}/${STAMP}.bundle"

mkdir -p "$BACKUP_DIR"
git -C "$REPO_DIR" bundle create "$BUNDLE" --all
git -C "$REPO_DIR" bundle verify "$BUNDLE"
echo "备份完成: $BUNDLE"

# 只保留最近 10 份
ls -1t "$BACKUP_DIR"/*.bundle 2>/dev/null | tail -n +11 | xargs -r rm -- 
echo "（保留最近 10 份备份）"
