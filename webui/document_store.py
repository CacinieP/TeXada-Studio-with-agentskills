"""Local document storage with optimistic concurrency and recoverable revisions."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import threading
import time
import uuid

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
_LOCK = threading.RLock()


class DocumentError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def document_name(value):
    if (not isinstance(value, str) or len(value) > 128
            or not re.fullmatch(r"[\w ()\-.]+\.tex", value)
            or value.startswith(".") or ".." in value):
        raise DocumentError("请使用不含路径的 .tex 文件名（最长 128 个字符）。")
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

    def _path(self, directory, name):
        path = directory / document_name(name)
        if directory.is_symlink() or path.is_symlink():
            raise DocumentError("不支持符号链接文档。")
        return path

    def read(self, name):
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
        names = {p.name for directory in (self.samples, self.documents) if directory.is_dir()
                 for p in directory.glob("*.tex") if p.is_file() and not p.is_symlink()}
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
            if previous:
                # Uploading over a sample creates a local copy; an existing local
                # document always needs the version the editor actually opened.
                sample_upload = upload and previous["origin"] == "sample" and expected_sha256 is None
                if not sample_upload and expected_sha256 != previous["sha256"]:
                    raise DocumentError("文件已变化或同名文件已存在；请重新打开或另存为。", 409)
                if previous["origin"] == "local":
                    self._archive(previous)
            elif expected_sha256 is not None:
                raise DocumentError("文件已被移动或删除；请另存为。", 409)
            self._write(self._path(self.documents, name), content)
            return {"ok": True, **self.read(name)}

    def rename(self, name, new_name, expected_sha256):
        document_name(new_name)
        with _LOCK:
            old = self.read(name)
            if old["origin"] != "local":
                raise DocumentError("示例为只读，请先保存为本地文档。", 409)
            if old["sha256"] != expected_sha256:
                raise DocumentError("文档已变化，请重新打开。", 409)
            if name == new_name:
                return {"ok": True, **old}
            try:
                self.read(new_name)
            except DocumentError as exc:
                if exc.status != 404:
                    raise
            else:
                raise DocumentError("目标文件名已存在。", 409)
            self._archive(old)
            os.replace(self._path(self.documents, name), self._path(self.documents, new_name))
            return {"ok": True, **self.read(new_name)}

    def delete(self, name, expected_sha256):
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
