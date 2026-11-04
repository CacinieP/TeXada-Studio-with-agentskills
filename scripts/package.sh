#!/usr/bin/env bash
# 从已提交的 HEAD 生成可复核源码包；不收集工作目录或本机运行依赖。
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$REPO_DIR/dist"
cd "$REPO_DIR"
COMMIT="$(git rev-parse --verify 'HEAD^{commit}')"
if ! git diff --quiet "$COMMIT" -- || ! git diff --cached --quiet "$COMMIT" --; then
  echo "请先审阅并提交代码；打包只包含 HEAD，不能包含未提交的修改。" >&2
  exit 1
fi
REV="$(git rev-parse --short=12 "$COMMIT")"
TREE="$(git rev-parse "$COMMIT^{tree}")"
STEM="TeXada-Studio-with-agentskills-$REV"
PACKAGE_PYTHON="${TEXADA_PACKAGE_PYTHON:-python3}"
mkdir -p "$DIST"
BUILD_DIR="$(mktemp -d "$DIST/.source-package.XXXXXX")"
trap 'rm -rf "$BUILD_DIR"' EXIT
git archive --format=zip --prefix="$STEM/" --output="$BUILD_DIR/$STEM.zip" "$COMMIT"

# Python 标准库负责 ZIP 完整性、包内路径和摘要检查，不解压、不加载源码。
"$PACKAGE_PYTHON" - "$BUILD_DIR" "$STEM" "$COMMIT" "$TREE" <<'PY'
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

directory, stem, commit, tree = Path(sys.argv[1]), *sys.argv[2:]
archive = directory / (stem + ".zip")
prefix = stem + "/"
required = {"LICENSE", "README.md", "README.en.md", "THIRD_PARTY_NOTICES.md",
            "scripts/package.sh", "scripts/run-local-studio.py", "webui/app.py",
            "webui/requirements.txt", "harness/requirements.txt"}
runtime_directories = {".git", ".github", "state", "work", "dist", "models", ".venv",
                       "venv", "node_modules", "__pycache__", ".repo_memory", ".ssh", ".aws"}
private_names = {"secrets.env", "session.json", "credentials.json", "id_rsa", "id_ed25519",
                 ".netrc", ".DS_Store"}
runtime_suffixes = {".gguf", ".safetensors", ".pyc", ".pyo", ".log", ".pem", ".key",
                    ".p12", ".pfx", ".dylib", ".so", ".dll", ".exe"}
native_magic = {b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
                b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
files, seen = [], set()
try:
    with zipfile.ZipFile(archive) as source:
        if source.comment.decode("ascii") != commit:
            raise ValueError("ZIP commit marker does not match the selected HEAD")
        for entry in source.infolist():
            name = entry.filename
            if not name.startswith(prefix) or "\\" in name:
                raise ValueError("unexpected archive root or path separator")
            relative = name[len(prefix):].rstrip("/")
            if not relative:
                continue  # The one top-level directory entry.
            path = PurePosixPath(relative)
            if (path.is_absolute() or any(part in {".", ".."} for part in path.parts)
                    or relative in seen):
                raise ValueError("unsafe or duplicate archive path")
            seen.add(relative)
            filename = path.name
            if (any(part in runtime_directories for part in path.parts)
                    or filename in private_names or filename.endswith("-headers.txt")
                    or (filename.startswith(".env") and filename != ".env.example")
                    or path.suffix.lower() in runtime_suffixes):
                raise ValueError("runtime, model or private path found in archive: " + relative)
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("source package must not contain symbolic links: " + relative)
            if not entry.is_dir():
                payload = source.read(entry)  # Also verifies this member's ZIP CRC.
                pe_offset = int.from_bytes(payload[60:64], "little") if len(payload) >= 64 else 0
                is_pe = payload[:2] == b"MZ" and pe_offset >= 64 and payload[pe_offset:pe_offset + 4] == b"PE\0\0"
                if payload[:4] in native_magic or is_pe:
                    raise ValueError("native runtime binary found in source archive: " + relative)
                files.append({"path": relative, "bytes": len(payload),
                              "sha256": hashlib.sha256(payload).hexdigest()})
        missing = required - {item["path"] for item in files}
        if missing:
            raise ValueError("source package lacks required files: " + ", ".join(sorted(missing)))
    archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {"schema_version": 1, "kind": "git-archive-source-package",
                "commit": commit, "tree": tree, "archive": archive.name,
                "archive_sha256": archive_sha256, "root_prefix": prefix,
                "file_count": len(files), "files": sorted(files, key=lambda item: item["path"])}
    manifest_path = directory / (stem + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (directory / (stem + ".SHA256SUMS")).write_text(
        f"{archive_sha256}  {archive.name}\n{manifest_sha256}  {manifest_path.name}\n", encoding="utf-8")
except (OSError, ValueError, zipfile.BadZipFile) as error:
    print("源码包验证失败：" + str(error), file=sys.stderr)
    sys.exit(1)
PY

# 只有所有检查通过后才将这组文件放到 dist；失败时只清理本次临时目录。
for suffix in zip manifest.json SHA256SUMS; do
  mv "$BUILD_DIR/$STEM.$suffix" "$DIST/$STEM.$suffix"
done
echo "源码包: $DIST/$STEM.zip"
echo "文件清单: $DIST/$STEM.manifest.json"
echo "SHA256 校验: $DIST/$STEM.SHA256SUMS"
