"""Local document storage with optimistic concurrency and recoverable revisions."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import unicodedata
import uuid

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_LOCK = threading.RLock()
_WINDOWS_RESERVED_STEMS = frozenset({
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
})


class DocumentError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def document_name(value):
    if not isinstance(value, str):
        raise DocumentError("请使用不含路径的 .tex 文件名（最长 128 个字符）。")
    value = unicodedata.normalize("NFC", value)
    if (len(value) > 128
            or not re.fullmatch(r"[\w ()\-.]+\.tex", value)
            or value.startswith(".") or ".." in value):
        raise DocumentError("请使用不含路径的 .tex 文件名（最长 128 个字符）。")
    stem = value[:-4]
    if not stem or stem[-1] in {" ", "."}:
        raise DocumentError("文件名词干末尾不能是空格或点号。")
    device_stem = stem.split(".", 1)[0].rstrip(" .").upper()
    if device_stem in _WINDOWS_RESERVED_STEMS:
        raise DocumentError("文件名不能使用系统保留设备名。")
    return value


def document_text(value):
    if not isinstance(value, str):
        raise DocumentError("文档内容必须是文本。")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise DocumentError("文档必须是有效的 UTF-8 文本。") from None
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise DocumentError("单个文档不能超过 2 MiB。", 413)
    if "\x00" in value:
        raise DocumentError("文档中不能包含空字节。")
    return value


def text_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class DocumentStore:
    def __init__(self, documents, samples):
        self.documents = Path(documents)
        self.samples = Path(samples)

    def _path(self, directory, name, *, for_write=False):
        norm = document_name(name)
        if directory.is_symlink():
            raise DocumentError("不支持符号链接文档。")
        path = directory / norm
        if not for_write and not path.exists() and not path.is_symlink() and directory.is_dir():
            for entry in directory.iterdir():
                if unicodedata.normalize("NFC", entry.name) == norm:
                    path = entry
                    break
        if path.is_symlink():
            raise DocumentError("不支持符号链接文档。")
        return path

    def read(self, name):
        with _LOCK:
            name = document_name(name)
            user_path = self._path(self.documents, name)
            path = user_path if user_path.is_file() else self._path(self.samples, name)
            if not path.is_file():
                raise DocumentError("文档不存在。", 404)
            if path.stat().st_size > MAX_DOCUMENT_BYTES:
                raise DocumentError("文档超过 2 MiB。", 413)
            try:
                content = path.read_text(encoding="utf-8-sig")
            except UnicodeError:
                raise DocumentError("文档不是有效的 UTF-8 文本。") from None
            return {"name": name, "content": content, "sha256": text_hash(content),
                    "origin": "local" if path == user_path else "sample",
                    "saved_at": path.stat().st_mtime, "size": len(content.encode("utf-8"))}

    def listing(self):
        with _LOCK:
            seen_names = set()
            seen_casefold = set()
            seen_inodes = set()
            names = []
            if self.documents.is_dir() and not self.documents.is_symlink():
                for p in sorted(self.documents.iterdir(), key=lambda entry: unicodedata.normalize("NFC", entry.name)):
                    if p.is_symlink() or not p.is_file():
                        continue
                    try:
                        canonical_name = document_name(p.name)
                        st = p.stat()
                    except (DocumentError, OSError):
                        continue
                    inode = (st.st_dev, st.st_ino) if st.st_ino != 0 else None
                    if (inode is not None and inode in seen_inodes) or canonical_name in seen_names:
                        continue
                    if inode is not None:
                        seen_inodes.add(inode)
                    seen_names.add(canonical_name)
                    seen_casefold.add(canonical_name.casefold())
                    names.append(canonical_name)
            if self.samples.is_dir() and not self.samples.is_symlink():
                for p in sorted(self.samples.iterdir(), key=lambda entry: unicodedata.normalize("NFC", entry.name)):
                    if p.is_symlink() or not p.is_file():
                        continue
                    try:
                        name = document_name(p.name)
                    except DocumentError:
                        continue
                    folded = name.casefold()
                    if folded in seen_casefold:
                        continue
                    local_alias = self.documents / name
                    if not self.documents.is_symlink() and not local_alias.is_symlink() and local_alias.is_file():
                        try:
                            lst = local_alias.stat()
                        except OSError:
                            pass
                        else:
                            if lst.st_ino != 0 and (lst.st_dev, lst.st_ino) in seen_inodes:
                                continue
                    seen_casefold.add(folded)
                    names.append(name)
            documents = []
            for name in sorted(names):
                try:
                    documents.append({k: v for k, v in self.read(name).items() if k != "content"})
                except DocumentError:
                    continue
            return {"files": [d["name"] for d in documents], "documents": documents}

    def _write(self, path, content):
        self._safe_write_path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8", newline="") as stream:
                os.chmod(temporary, 0o600)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _safe_write_path(self, path):
        try:
            path.relative_to(self.documents)
        except ValueError:
            raise DocumentError("写入必须位于本地文档目录内。") from None
        for entry in (path, *path.parents):
            if entry.is_symlink():
                raise DocumentError("文档和恢复目录不能使用符号链接。")
            if entry == self.documents.parent:
                break

    def _archive(self, record):
        directory = self.documents / ".history" / hashlib.sha256(record["name"].encode()).hexdigest()[:20]
        self._write(directory / (record["sha256"] + ".tex"), record["content"])

    def save(self, name, content, expected_sha256=None, *, create=False, upload=False):
        name, content = document_name(name), document_text(content)
        with _LOCK:
            try:
                previous = self.read(name)
            except DocumentError as exc:
                if exc.status != 404:
                    raise
                previous = None
            if create and previous is not None:
                raise DocumentError("此名称已存在，请使用其他文件名。", 409)
            old_local = None
            if previous:
                # Uploading over a sample creates a local copy; an existing local
                # document always needs the version the editor actually opened.
                sample_upload = upload and previous["origin"] == "sample" and expected_sha256 is None
                if not sample_upload and expected_sha256 != previous["sha256"]:
                    raise DocumentError("文件已变化或同名文件已存在；请重新打开或另存为。", 409)
                if previous["origin"] == "local":
                    old_local = self._path(self.documents, name)
                    self._archive(previous)
            elif expected_sha256 is not None:
                raise DocumentError("文件已被移动或删除；请另存为。", 409)
            target = self._path(self.documents, name, for_write=True)
            self._write(target, content)
            if old_local is not None and old_local.exists() and not os.path.samefile(old_local, target):
                old_local.unlink()
            return {"ok": True, **self.read(name)}

    def create_many(self, documents):
        with _LOCK:
            normalized = [(document_name(name), document_text(content)) for name, content in documents]
            paths = []
            seen_folded = set()
            for name, _ in normalized:
                folded = name.casefold()
                existing = self._path(self.documents, name)
                target = self._path(self.documents, name, for_write=True)
                if existing.exists() or self._path(self.samples, name).exists() or folded in seen_folded:
                    raise DocumentError(f"「{name}」已存在或重复，请更换文件名。", 409)
                self._safe_write_path(target)
                seen_folded.add(folded)
                paths.append(target)

            published = []
            try:
                self.documents.mkdir(parents=True, exist_ok=True, mode=0o700)
                with tempfile.TemporaryDirectory(prefix=".split-", dir=self.documents) as temporary:
                    staged = []
                    for index, (_, content) in enumerate(normalized):
                        path = Path(temporary) / str(index)
                        self._write(path, content)
                        staged.append(path)
                    for source, target in zip(staged, paths):
                        try:
                            os.link(source, target)
                        except FileExistsError:
                            raise DocumentError(f"「{target.name}」已存在，请更换文件名。", 409) from None
                        published.append(target)
            except (OSError, DocumentError) as error:
                for path in published:
                    path.unlink(missing_ok=True)
                if isinstance(error, DocumentError):
                    raise
                raise DocumentError("无法按页保存文档，请检查本地存储后重试。", 500) from None
            return {"ok": True, "files": [path.name for path in paths]}

    def rename(self, name, new_name, expected_sha256):
        name, new_name = document_name(name), document_name(new_name)
        with _LOCK:
            old = self.read(name)
            if old["origin"] != "local":
                raise DocumentError("示例为只读，请先保存为本地文档。", 409)
            if old["sha256"] != expected_sha256:
                raise DocumentError("文档已变化，请重新打开。", 409)
            if name == new_name:
                return {"ok": True, **old}
            old_path = self._path(self.documents, name)
            new_path = self._path(self.documents, new_name, for_write=True)
            same_local_file = old_path.exists() and new_path.exists() and os.path.samefile(old_path, new_path)
            if not same_local_file:
                try:
                    self.read(new_name)
                except DocumentError as exc:
                    if exc.status != 404:
                        raise
                else:
                    raise DocumentError("目标文件名已存在。", 409)
            self._archive(old)
            if same_local_file:
                intermediate = old_path.with_name("." + uuid.uuid4().hex + ".rename")
                self._safe_write_path(intermediate)
                os.replace(old_path, intermediate)
                try:
                    os.replace(intermediate, new_path)
                except Exception:
                    if intermediate.exists() and not old_path.exists():
                        os.replace(intermediate, old_path)
                    raise
            else:
                os.replace(old_path, new_path)
            return {"ok": True, **self.read(new_name)}

    def delete(self, name, expected_sha256):
        name = document_name(name)
        with _LOCK:
            old = self.read(name)
            if old["origin"] != "local":
                raise DocumentError("示例文档为只读。", 409)
            if expected_sha256 != old["sha256"]:
                raise DocumentError("文档已变化，请重新打开。", 409)
            self._archive(old)
            trash = self.documents / ".trash"
            self._safe_write_path(trash)
            trash.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.replace(self._path(self.documents, name), trash / (str(time.time_ns()) + "-" + name))
            return {"ok": True, "name": name, "recoverable": True}
