"""Explicit downloads of pinned OpenBMB model files and a Studio-owned llama-server."""
from __future__ import annotations

import hashlib
from http.client import HTTPException
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple

from local_runtime import LocalRuntimeError, local_json_request

_STDLIB_URLOPEN = urllib.request.urlopen
_BLOCKED_MODEL_ENV = {
    "DEMO_TOKEN",
    "VLM_BASE_URL",
    "VLM_MODEL",
    "TEXADA_OPENAI_BASE_URL",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
}


class ModelFile(NamedTuple):
    name: str
    size: int
    sha256: str


class ModelProfile(NamedTuple):
    name: str
    model: str
    repo: str
    revision: str
    files: tuple[ModelFile, ...]


PROFILES = {
    "1b": ModelProfile(
        "MiniCPM-V 4.7 1B · Q4_K_M", "minicpm-v4.7-1b-q4_k_m",
        "openbmb/MiniCPM-V-4.7-1B-gguf", "59cd286146b6ce70f818508ccf512e11438d8957",
        (
            ModelFile("MiniCPM-V-4_7-1B-Q4_K_M.gguf", 672003680,
                      "588c6c94c82f756b86dba35c42ed9ba9ec187d65824eb52f039c347df563e63d"),
            ModelFile("mmproj-model-f16.gguf", 1110117984,
                      "fb9cc047a3cdad5317fd8433a4aeda2d22f00f02ca4bd93b34ad84165b25a900"),
        ),
    ),
    "35b": ModelProfile(
        "MiniCPM-V 4.7 35B-A3B · Q4_K_M", "minicpm-v4.7-35b-a3b-q4",
        "openbmb/MiniCPM-V-4.7-35B-A3B-gguf", "adc779c0f3c4936016d7124395ccf260ec696567",
        (
            ModelFile("MiniCPM-V-4_7-35B-A3B-Q4_K_M.gguf", 21166255008,
                      "9ecf91e814d7e9adc64325b1b65f8628a9b1bb8da4f61a92869ca7489bfd888e"),
            ModelFile("mmproj-model-f16.gguf", 1119575840,
                      "bff3b688e14c300eca273092c37c50a0ddfcc2054e079af1a0480edeed5d20f1"),
        ),
    ),
}


def _clean_model_environment(source):
    """Strip cloud API credentials, UI tokens, llama.cpp arg overrides, and proxies."""
    return {
        key: value
        for key, value in source.items()
        if "API_KEY" not in key.upper()
        and not key.upper().endswith(("_TOKEN", "_SECRET"))
        and not key.upper().startswith("LLAMA_ARG_")
        and key.upper() not in _BLOCKED_MODEL_ENV
    }


def find_llama_server(*, os_name=None):
    effective_os = os_name if os_name is not None else os.name
    names = ("llama-server.exe", "llama-server") if effective_os == "nt" else ("llama-server", "llama-server.exe")
    bundle_dir = os.environ.get("TEXADA_BUNDLE_DIR", "").strip()
    if bundle_dir:
        bundle_bin = Path(bundle_dir).resolve() / "bin"
        for name in names:
            bundled = bundle_bin / name
            if bundled.is_file() and os.access(bundled, os.X_OK):
                return str(bundled)
    home = Path.home()
    candidates = (
        *(home / ".texada" / "bin" / name for name in names),
        *(home / ".texada" / "runtime" / name for name in names),
        Path("/opt/homebrew/bin/llama-server"),
        Path("/usr/local/bin/llama-server"),
    )
    found_in_path = next((shutil.which(name) for name in names if shutil.which(name)), None)
    return found_in_path or next(
        (str(path) for path in candidates if path.is_file() and os.access(path, os.X_OK)), None
    )


def _size(path):
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _matches(path, file):
    if _size(path) != file.size:
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == file.sha256


_SERVER_ERROR_HINTS = re.compile(
    r"(GGML_ASSERT[^\n]*|no backends are loaded[^\n]*|failed to load model[^\n]*"
    r"|error loading model[^\n]*|unknown model architecture[^\n]*"
    r"|llama_model_load[^\n]*|error: [^\n]*)",
    re.IGNORECASE,
)


def _server_log_hint(path, limit=200):
    """Return the most recent actionable line from model-server.log, if any."""
    try:
        data = path.read_bytes()[-65536:]
    except OSError:
        return ""
    matches = _SERVER_ERROR_HINTS.findall(data.decode("utf-8", "replace"))
    if not matches:
        return ""
    return " ".join(matches[-1].split())[:limit]


def _reuse_weight(key, file, path):
    root = Path.home() / ".texada" / "models"
    ollama = Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama/models").expanduser()
    known = (root / key / file.name, root / file.name, ollama / "blobs" / ("sha256-" + file.sha256))
    for candidate in known:
        if not _matches(candidate, file):
            continue
        part = path.with_suffix(".gguf.reuse")
        part.unlink(missing_ok=True)
        try:
            os.link(candidate, part)
        except OSError:
            shutil.copyfile(candidate, part)
        part.replace(path)
        return True
    return False


class _HttpsOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or not parsed.hostname:
            if fp is not None:
                fp.close()
            raise ValueError("下载重定向必须保持 HTTPS。")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_https_only(req, timeout=30):
    parsed_req = urllib.parse.urlsplit(req.full_url)
    if parsed_req.scheme != "https" or not parsed_req.hostname:
        raise ValueError("下载重定向必须保持 HTTPS。")
    if urllib.request.urlopen is not _STDLIB_URLOPEN:
        response = urllib.request.urlopen(req, timeout=timeout)
        final_url = getattr(response, "url", None)
        if isinstance(final_url, str):
            parsed = urllib.parse.urlsplit(final_url)
            if parsed.scheme != "https" or not parsed.hostname:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                raise ValueError("下载重定向必须保持 HTTPS。")
        return response
    return urllib.request.build_opener(_HttpsOnlyRedirectHandler()).open(req, timeout=timeout)


def _download(profile, file, path, progress, closed):
    part = path.with_suffix(f".gguf.{file.sha256}.part")
    offset = _size(part)
    if offset > file.size or (offset == file.size and not _matches(part, file)):
        part.unlink(missing_ok=True)
        offset = 0
    if offset < file.size:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        url = f"https://huggingface.co/{profile.repo}/resolve/{profile.revision}/{file.name}"
        with _open_https_only(urllib.request.Request(url, headers=headers), timeout=30) as response:
            if response.status == 206:
                if response.headers.get("Content-Range") != f"bytes {offset}-{file.size - 1}/{file.size}":
                    raise ValueError("下载服务返回了不匹配的文件范围。")
            elif response.status == 200:
                offset = 0
            else:
                raise ValueError("下载服务未返回权重文件。")
            with part.open("ab" if offset else "wb") as stream:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    if closed.is_set():
                        return
                    offset += len(block)
                    if offset > file.size:
                        raise ValueError("下载文件超出官方大小。")
                    stream.write(block)
                    progress(offset)
    progress(file.size)
    if not _matches(part, file):
        if _size(part) >= file.size:
            part.unlink(missing_ok=True)
        raise ValueError("模型文件未完整下载或 SHA-256 不匹配，请重试。")
    part.replace(path)


class ManagedModels:
    def __init__(self, state):
        self.state = Path(state)
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.process = None
        self.active = None
        self.job = None

    def _paths(self, key):
        return tuple(self.state / "models" / key / file.name for file in PROFILES[key].files)

    def status(self):
        with self.lock:
            return {
                "runtime_available": bool(find_llama_server()),
                "active": self.connection(),
                "job": self.job.copy() if self.job else None,
                "profiles": [
                    {"id": key, "name": profile.name, "model": profile.model,
                     "size": sum(file.size for file in profile.files),
                     "downloaded": all(_size(path) == file.size
                                       for path, file in zip(self._paths(key), profile.files))}
                    for key, profile in PROFILES.items()
                ],
            }

    def connection(self):
        with self.lock:
            if self.active and self.process is not None and self.process.poll() is None:
                return self.active.copy()
            self.active = None
            if self.process is not None and self.process.poll() is not None:
                self.process = None
            return None

    def _job(self, **fields):
        with self.lock:
            self.job.update(fields)

    def submit(self, action, key):
        if not isinstance(key, str) or key not in PROFILES or action not in {"download", "start"}:
            raise LocalRuntimeError("unknown_model", "请选择支持的 MiniCPM 版本。")
        with self.lock:
            if self.closed.is_set() or (self.job and self.job["state"] == "running"):
                raise LocalRuntimeError("model_busy", "已有模型操作正在执行。", 409)
            if action == "start" and not find_llama_server():
                raise LocalRuntimeError("runtime_missing",
                                        "未找到 llama-server。请使用含运行时的 Studio 安装包，或安装 llama.cpp。", 503)
            self.job = {"profile": key, "action": action, "state": "running", "bytes": 0,
                        "total": sum(file.size for file in PROFILES[key].files)}
            threading.Thread(target=self._run, args=(action, key), daemon=True).start()
            return self.status()

    def _run(self, action, key):
        profile = PROFILES[key]
        paths = self._paths(key)
        try:
            if action == "download":
                paths[0].parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                done = 0
                for file, path in zip(profile.files, paths):
                    if not _matches(path, file) and not _reuse_weight(key, file, path):
                        _download(profile, file, path,
                                  lambda count: self._job(bytes=done + count), self.closed)
                    if self.closed.is_set():
                        return
                    done += file.size
                    self._job(bytes=done)
            else:
                if not all(_matches(path, file) for path, file in zip(paths, profile.files)):
                    raise ValueError("模型权重缺失或校验失败，请先下载。")
                self._start(profile, paths)
            self._job(state="done")
        except (OSError, ValueError, HTTPException, subprocess.SubprocessError) as error:
            # urllib errors can include a temporary signed download URL.
            message = str(error) if type(error) is ValueError else "操作失败，请检查网络、磁盘或 model-server.log 后重试。"
            self._job(state="failed", message=message)

    def _start(self, profile, paths):
        active = self.connection()
        if active and active["model"] == profile.model:
            return
        executable = find_llama_server()
        clean_env = _clean_model_environment(os.environ)
        win_kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
        version = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
            env=clean_env,
            **win_kwargs,
        )
        output = version.stdout + version.stderr
        build = re.search(r"build (\d+)", output) or re.search(r"version: (\d+)(?:\s|$)", output)
        if build and int(build.group(1)) < 11609:
            raise ValueError("llama-server 版本过旧，MiniCPM-V 4.7 需要 build 11609 或更新版本。")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        with self.lock:
            if self.closed.is_set():
                return
            self._terminate()
            self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
            log_path = self.state / "model-server.log"
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(log_path, flags, 0o600)
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(fd, 0o600)
                elif os.name == "posix":
                    os.chmod(log_path, 0o600)
                log_stream = os.fdopen(fd, "ab")
            except Exception:
                os.close(fd)
                raise
            with log_stream as log:
                self.process = process = subprocess.Popen([
                    executable, "-m", str(paths[0]), "--mmproj", str(paths[1]),
                    "--alias", profile.model, "--host", "127.0.0.1", "--port", str(port),
                    "--ctx-size", "8192", "--parallel", "1", "-ngl", "99",
                    "--jinja", "--reasoning", "off", "--no-webui",
                ], stdout=log, stderr=subprocess.STDOUT, env=clean_env, **win_kwargs)
        base = f"http://127.0.0.1:{port}/v1"
        deadline = time.monotonic() + 180
        try:
            while process.poll() is None and time.monotonic() < deadline and not self.closed.is_set():
                try:
                    models = local_json_request(base + "/models", timeout=2).get("data", [])
                    if any(isinstance(item, dict) and item.get("id") == profile.model for item in models):
                        with self.lock:
                            if self.process is process and process.poll() is None and not self.closed.is_set():
                                self.active = {"base_url": base, "model": profile.model}
                                return
                except LocalRuntimeError:
                    pass
                self.closed.wait(0.5)
            detail = _server_log_hint(self.state / "model-server.log")
            suffix = f"：{detail}" if detail else "，请检查可用内存和 model-server.log。"
            raise ValueError("模型未能启动" + suffix)
        finally:
            with self.lock:
                if self.process is process and self.active is None:
                    self._terminate()

    def _terminate(self):
        process, self.process, self.active = self.process, None, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def stop(self):
        with self.lock:
            if self.job and self.job["action"] == "start" and self.job["state"] == "running":
                raise LocalRuntimeError("model_busy", "请等当前模型启动结束。", 409)
            self._terminate()

    def close(self):
        self.closed.set()
        with self.lock:
            self._terminate()
