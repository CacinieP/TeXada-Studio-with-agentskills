# TeXada Studio 桌面窗口:复用现有仓库检出与本机启动器,不自带模型、TeX 资源或云依赖。
"""薄桌面壳:有可用会话就复用,否则拉起 ``scripts/run-local-studio.py``,
在独立窗口(WKWebView)中打开私密入口;关闭窗口只回收自己启动的进程。

用法::

    .venv/bin/python desktop/app.py [--port 8888] [--state-dir DIR] [--timeout 120]

GUI 依赖 pywebview(``pip install -r desktop/requirements.txt``),仅在打开窗口时导入;
会话读取与进程管理逻辑保持无第三方依赖,便于离线测试。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from urllib.parse import quote
from pathlib import Path

def _default_venv_python(repo_root: Path = Path(__file__).resolve().parents[1], *, os_name: str | None = None) -> Path:
    effective_os = os_name if os_name is not None else os.name
    if effective_os == "nt":
        return repo_root / ".venv" / "Scripts" / "python.exe"
    return repo_root / ".venv" / "bin" / "python"


def _default_state_dir(
    *,
    platform_name: str | None = None,
    os_name: str | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    source_env = os.environ if env is None else env
    override = source_env.get("TEXADA_STUDIO_STATE_DIR")
    if override:
        return Path(override).expanduser()
    effective_platform = platform_name if platform_name is not None else sys.platform
    effective_os = os_name if os_name is not None else os.name
    user_home = home if home is not None else Path.home()
    if effective_platform == "darwin":
        return user_home / "Library" / "Application Support" / "TeXada Studio"
    if effective_os == "nt":
        local_appdata = source_env.get("LOCALAPPDATA") or str(user_home / "AppData" / "Local")
        return Path(local_appdata) / "TeXada Studio"
    xdg_data = source_env.get("XDG_DATA_HOME") or str(user_home / ".local" / "share")
    return Path(xdg_data) / "texada-studio"


def _default_tex_cache_target(
    *,
    platform_name: str | None = None,
    os_name: str | None = None,
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    source_env = os.environ if env is None else env
    effective_platform = platform_name if platform_name is not None else sys.platform
    effective_os = os_name if os_name is not None else os.name
    user_home = home if home is not None else Path.home()
    if effective_platform == "darwin":
        return user_home / "Library" / "Caches" / "TectonicProject.Tectonic"
    if effective_os == "nt":
        local_appdata = source_env.get("LOCALAPPDATA") or str(user_home / "AppData" / "Local")
        return Path(local_appdata) / "TectonicProject" / "Tectonic" / "Cache"
    xdg_cache = source_env.get("XDG_CACHE_HOME") or str(user_home / ".cache")
    return Path(xdg_cache) / "Tectonic"


REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = Path(os.environ["TEXADA_BUNDLE_DIR"]).resolve() if os.environ.get("TEXADA_BUNDLE_DIR") else None
LAUNCHER = (BUNDLE_DIR or REPO_ROOT) / "scripts" / "run-local-studio.py"
VENV_PYTHON = _default_venv_python(REPO_ROOT)
DEFAULT_STATE_DIR = _default_state_dir()
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
TEX_CACHE_SOURCE = BUNDLE_DIR / "tex-cache" if BUNDLE_DIR else None
TEX_CACHE_TARGET = _default_tex_cache_target()


def tool_bin_dirs():
    """PATH 前置目录:捆绑 bin(自包含包)与 ~/.texada/bin(含 Windows Library/bin)。"""
    dirs = [Path.home() / ".texada" / "bin"]
    if os.name == "nt":
        dirs.append(Path.home() / ".texada" / "Library" / "bin")
    if BUNDLE_DIR is not None:
        bundled = [BUNDLE_DIR / "bin"]
        if os.name == "nt":
            bundled.append(BUNDLE_DIR / "Library" / "bin")
        dirs = [*bundled, *dirs]
    return dirs


def prepend_dirs(path_value, dirs):
    """把目录按序前置到 PATH(幂等,纯函数便于测试)。"""
    entries = [entry for entry in (path_value or "").split(os.pathsep) if entry]
    additions = [str(item) for item in dirs if str(item) not in entries]
    return os.pathsep.join([*additions, *entries]) if entries or additions else ""


def backend_python():
    """启动器使用的解释器:捆绑模式用当前解释器,仓库模式优先 venv。"""
    if BUNDLE_DIR is not None:
        return sys.executable
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def read_entry(state_dir: Path):
    """读取工作区的 session.json;结构不合法或非回环入口时返回 None。"""
    try:
        record = json.loads((state_dir / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict):
        return None
    url = record.get("url")
    if not isinstance(url, str):
        return None
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in LOOPBACK_HOSTS:
        return None
    token = next((value for key, value in urllib.parse.parse_qsl(parts.query) if key == "token"), "")
    if not token or parts.username or parts.password or parts.fragment:
        return None
    pid = record.get("pid")
    return {"url": url, "pid": pid if type(pid) is int and pid >= 1 else None,
            "running": record.get("running") is True}


def _win32_pid_alive(pid: int) -> bool:
    if type(pid) is not int or pid <= 0 or pid > 0xFFFFFFFF:
        return False
    import ctypes

    windll = getattr(ctypes, "windll", None)
    if isinstance(windll, ctypes.LibraryLoader) and hasattr(ctypes, "WinDLL"):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
    elif windll is not None:
        kernel32 = windll.kernel32
    else:
        return False

    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5
    try:
        return kernel32.WaitForSingleObject(handle, 0) == 0x00000102
    finally:
        kernel32.CloseHandle(handle)


def entry_alive(entry) -> bool:
    """会话记录是否指向一个仍在运行的启动器进程。"""
    if not entry or not entry["running"]:
        return False
    pid = entry.get("pid")
    if type(pid) is not int or pid < 1:
        return False
    if os.name == "nt":
        return _win32_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _port_available(port: int, host: str = "127.0.0.1") -> bool:
    """检测回环端口是否可独占绑定,避免捆绑模式把私密 token 发给外部占口进程。"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def wait_for_entry(
    state_dir: Path,
    timeout: float,
    previous_pid=None,
    child=None,
    abort_if=None,
    expected_url=None,
):
    """轮询等待启动器写出新的可用会话;子进程退出、中止条件触发或超时返回 None。"""
    def _matches(entry):
        if not entry_alive(entry) or entry["pid"] == previous_pid:
            return False
        if expected_url is not None and entry["url"] != expected_url:
            return False
        return True

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = read_entry(state_dir)
        if _matches(entry):
            return entry
        if abort_if is not None and abort_if():
            entry = read_entry(state_dir)
            return entry if _matches(entry) else None
        if child is not None and child.poll() is not None:
            entry = read_entry(state_dir)
            return entry if _matches(entry) else None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))
    return None


def wait_for_http(url, timeout: float = 30.0, sleeper=None, abort_if=None):
    """等私密入口真正可访问,避免窗口先于后端打开;只走本机、不代理。"""
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if abort_if is not None and abort_if():
            return False
        try:
            with opener.open(url, timeout=2):
                return True
        except Exception:
            if abort_if is not None and abort_if():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if sleeper is not None:
                sleeper(0.4)
            else:
                time.sleep(min(0.2, remaining))
    return False


def launcher_argv(state_dir: Path, port=None):
    """组装启动器命令行:始终不自动开浏览器,自定义数据目录时显式传递。"""
    argv = [backend_python(), str(LAUNCHER), "--no-browser"]
    if port:
        argv += ["--port", str(port)]
    if state_dir != DEFAULT_STATE_DIR:
        argv += ["--state-dir", str(state_dir)]
    return argv


def launcher_env(source=None):
    """子进程环境:标记「父进程消失即优雅退出」,防桌面窗口被强杀后后端残留。"""
    env = dict(source if source is not None else os.environ)
    env["TEXADA_EXIT_WHEN_ORPHANED"] = "1"
    env["PATH"] = prepend_dirs(env.get("PATH", ""), tool_bin_dirs())
    return env


def seed_tex_cache(source=None, target=None, copier=None):
    """Seed a fresh cache or add immutable bundle resources missing after an upgrade."""
    source = Path(source) if source is not None else TEX_CACHE_SOURCE
    target = Path(target) if target is not None else TEX_CACHE_TARGET
    if source is None or not source.is_dir():
        return False
    if not target.exists():
        (copier or shutil.copytree)(str(source), str(target))
        return True
    copied = False
    for entry in (source / "bundles" / "data").glob("*/*"):
        digest = entry.parent.name
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) or not entry.is_file():
            continue
        destination = target / entry.relative_to(source)
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.parent / f".{destination.name}.tmp-{os.getpid()}-{secrets.token_hex(6)}"
        try:
            shutil.copyfile(entry, staging)
            try:
                os.link(staging, destination)
            except FileExistsError:
                continue
            except OSError:
                if not destination.exists():
                    os.replace(staging, destination)
        finally:
            staging.unlink(missing_ok=True)
        copied = True
    return copied


def start_backend_thread(state_dir: Path, port, server_box: dict):
    """捆绑模式:进程内线程跑 uvicorn;窗口进程退出即无残留。"""
    if not _port_available(port):
        server_box["error"] = f"端口 {port} 已被占用"
        return server_box

    seed_tex_cache()
    if os.name == "nt" and TEX_CACHE_TARGET.is_dir():
        os.environ.setdefault("TECTONIC_CACHE_DIR", str(TEX_CACHE_TARGET))
    state_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    os.environ.update({
        "TEXADA_LOCAL_MODE": "1", "SKILL_MODE": "on",
        "TEXADA_STUDIO_STATE_DIR": str(state_dir),
        "DEMO_TOKEN": token,
        "PATH": prepend_dirs(os.environ.get("PATH", ""), tool_bin_dirs()),
    })
    for entry in (BUNDLE_DIR / "webui", BUNDLE_DIR / "harness"):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    import uvicorn

    lock = threading.RLock()
    server_box["lock"] = lock
    server_box["stopped"] = False
    server_box["server"] = uvicorn.Server(uvicorn.Config(
        "app:app", host="127.0.0.1", port=port, workers=1, access_log=False, log_level="warning"))
    record = {"session_id": secrets.token_hex(12), "pid": os.getpid(),
              "url": f"http://127.0.0.1:{port}/studio?token={quote(token)}",
              "base_url": f"http://127.0.0.1:{port}", "model_base_url": os.environ.get("VLM_BASE_URL", ""),
              "model": "", "owned_model_pid": None, "created_at": time.time(), "running": True}
    server_box["record"] = record

    def worker():
        try:
            server_box["server"].run()
            if not getattr(server_box["server"], "started", False) and not server_box.get("stopped"):
                with lock:
                    server_box.setdefault("error", "后端未完成启动即退出")
                    if state_dir.exists():
                        _write_session(state_dir, {**record, "running": False, "url": None})
        except (Exception, SystemExit) as error:  # 后端线程崩溃或绑定失败(SystemExit)时标记会话,避免窗口悬死
            with lock:
                server_box["error"] = (
                    f"SystemExit({error.code})" if isinstance(error, SystemExit) else str(error)
                )
                if state_dir.exists():
                    _write_session(state_dir, {**record, "running": False, "url": None})

    thread = threading.Thread(target=worker, name="studio-backend", daemon=True)

    def publish_when_started():
        while thread.is_alive():
            with lock:
                if server_box.get("stopped") or server_box.get("error"):
                    return
                if getattr(server_box.get("server"), "started", False) is True:
                    if state_dir.exists():
                        _write_session(state_dir, record)
                    return
            time.sleep(0.02)

    thread.start()
    publisher = threading.Thread(target=publish_when_started, name="studio-session-pub", daemon=True)
    publisher.start()
    server_box["thread"] = thread
    server_box["publisher"] = publisher
    return server_box


def _write_session(state_dir: Path, record):
    if not state_dir.exists():
        return
    path = state_dir / "session.json"
    tmp = state_dir / f".session.json.tmp-{os.getpid()}-{secrets.token_hex(6)}"
    payload = json.dumps(record).encode("utf-8")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(str(tmp), str(path))
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def stop_backend_thread(server_box: dict, state_dir: Path):
    if server_box.get("stopped"):
        return
    lock = server_box.get("lock")
    if lock is not None:
        with lock:
            server_box["stopped"] = True
    else:
        server_box["stopped"] = True
    server = server_box.get("server")
    record = server_box.get("record")
    if server is not None:
        server.should_exit = True
    for key in ("thread", "publisher"):
        worker = server_box.get(key)
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=10)
    if record and state_dir.exists():
        if lock is not None:
            with lock:
                _write_session(state_dir, {**record, "running": False, "url": None})
        else:
            _write_session(state_dir, {**record, "running": False, "url": None})


def _scrub_child_session(state_dir: Path, child_pid: int) -> None:
    path = state_dir / "session.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(record, dict) or record.get("pid") != child_pid:
        return
    if record.get("running") is not False or record.get("url") is not None:
        _write_session(state_dir, {**record, "running": False, "url": None})


def _register_session_atexit(server_box: dict, state_dir: Path):
    """正常退出(Cmd+Q/关窗)时把会话标记为停止;强杀则由 pid 存活检查自愈。"""
    import atexit
    atexit.register(lambda: stop_backend_thread(server_box, state_dir))


def stop_launcher(child: subprocess.Popen) -> None:
    """只回收自己启动的启动器;模型等子进程由启动器自行回收。"""
    if child.poll() is not None:
        return
    child.send_signal(signal.SIGTERM)
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()


_ALLOWED_EXPORT_SUFFIXES = frozenset({".tex", ".pdf", ".md"})
_MAX_EXPORT_BYTES = 64 * 1024 * 1024
_DESKTOP_LOCALIZATION = {
    "global.quitConfirmation": "当前文档有未保存修改。确定放弃修改并关闭窗口？",
    "global.quit": "放弃并关闭",
    "global.cancel": "取消",
    "global.ok": "确定",
    "global.saveFile": "保存文件",
    "cocoa.menu.about": "关于",
    "cocoa.menu.services": "服务",
    "cocoa.menu.view": "视图",
    "cocoa.menu.edit": "编辑",
    "cocoa.menu.hide": "隐藏",
    "cocoa.menu.hideOthers": "隐藏其他",
    "cocoa.menu.showAll": "全部显示",
    "cocoa.menu.quit": "退出",
    "cocoa.menu.fullscreen": "进入全屏",
    "cocoa.menu.cut": "剪切",
    "cocoa.menu.copy": "拷贝",
    "cocoa.menu.paste": "粘贴",
    "cocoa.menu.selectAll": "全选",
    "windows.fileFilter.allFiles": "所有文件",
}


def _prepare_webview_storage(state_dir: Path) -> Path:
    """为桌面 WebView 准备持久化存储目录（保留本地偏好，避免每次启动清空并规避 Cookie 竞态）。"""
    state_dir.mkdir(parents=True, exist_ok=True)
    storage = state_dir / "webview-storage"
    if storage.is_symlink():
        raise RuntimeError(f"桌面存储目录不得为符号链接:{storage}")
    storage.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(storage, 0o700)
    return storage


def _sanitize_export_filename(filename: str) -> str:
    if not isinstance(filename, str):
        raise ValueError("导出文件名必须是字符串。")
    name = filename.strip()
    if (
        not name
        or len(name) > 200
        or "/" in name
        or "\\" in name
        or "\x00" in name
        or any(ord(ch) < 32 for ch in name)
        or name in {".", ".."}
        or Path(name).name != name
    ):
        raise ValueError("导出文件名包含非法字符。")
    if Path(name).suffix.lower() not in _ALLOWED_EXPORT_SUFFIXES:
        raise ValueError("仅支持导出 .tex、.pdf 或 .md 文件。")
    return name


def _is_trusted_loopback_url(url) -> bool:
    if not isinstance(url, str) or not url:
        return False
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "http" and parts.hostname in LOOPBACK_HOSTS


def _atomic_write_bytes(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.tmp-{os.getpid()}-{secrets.token_hex(6)}"
    try:
        with staging.open("wb") as handle:
            handle.write(payload)
        os.replace(str(staging), str(target))
    except Exception:
        staging.unlink(missing_ok=True)
        raise


class _DesktopBridge:
    """最小桌面 JS 桥接：仅暴露原生文件保存与编辑状态同步，内部属性全部以 _ 隐藏。"""

    def __init__(self, webview_module=None):
        self._webview = webview_module
        self._window = None
        self._lock = threading.RLock()
        self._dirty = False
        self._can_undo = False
        self._can_redo = False
        self._native_editable = False
        self._terminating = False

    def _attach(self, window) -> None:
        with self._lock:
            self._window = window
            if window is not None and hasattr(window, "confirm_close"):
                window.confirm_close = bool(self._dirty) and not self._terminating

    def _mark_terminating(self) -> None:
        with self._lock:
            self._terminating = True
            if self._window is not None and hasattr(self._window, "confirm_close"):
                self._window.confirm_close = False

    def _history_enabled(self, direction: str) -> bool:
        with self._lock:
            if self._native_editable:
                return True
            if direction == "undo":
                return self._can_undo
            if direction == "redo":
                return self._can_redo
            return False

    def set_edit_state(self, dirty=False, can_undo=False, can_redo=False, native_editable=False):
        with self._lock:
            self._dirty = bool(dirty)
            self._can_undo = bool(can_undo)
            self._can_redo = bool(can_redo)
            self._native_editable = bool(native_editable)
            if self._window is not None and hasattr(self._window, "confirm_close"):
                self._window.confirm_close = self._dirty and not self._terminating
        return {"ok": True}

    def save_file(self, filename, data_base64):
        window = self._window
        if window is None:
            raise RuntimeError("桌面窗口尚未就绪。")
        current_url = window.get_current_url() if callable(getattr(window, "get_current_url", None)) else None
        if not _is_trusted_loopback_url(current_url):
            raise RuntimeError("仅允许本地 TeXada Studio 工作台触发文件导出。")
        safe_name = _sanitize_export_filename(filename)
        if not isinstance(data_base64, str):
            raise ValueError("导出数据格式无效。")
        if len(data_base64) > (_MAX_EXPORT_BYTES * 4 // 3) + 16:
            raise ValueError("导出文件过大。")
        try:
            payload = base64.b64decode(data_base64.encode("ascii"), validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("导出数据编码无效。") from exc
        if len(payload) > _MAX_EXPORT_BYTES:
            raise ValueError("导出文件过大。")
        file_dialog = getattr(self._webview, "FileDialog", None)
        save_dialog = getattr(file_dialog, "SAVE", 30)
        selection = window.create_file_dialog(save_dialog, save_filename=safe_name)
        target_raw = selection[0] if isinstance(selection, (list, tuple)) and selection else selection
        if not isinstance(target_raw, str) or not target_raw.strip():
            return {"saved": False, "cancelled": True}
        target = Path(target_raw)
        _atomic_write_bytes(target, payload)
        return {"saved": True, "cancelled": False, "name": target.name}


def _dispatch_macos_history_js(window, direction: str) -> bool:
    """在 Cocoa 主线程异步派发撤销/重做 JS，绝不阻塞等待信号量避免死锁。"""
    if direction not in {"undo", "redo"} or window is None:
        return False
    script = f"window.TeXadaStudioHistory && window.TeXadaStudioHistory({json.dumps(direction)});"
    try:
        from webview.platforms.cocoa import BrowserView

        uid = getattr(window, "uid", None)
        instance = BrowserView.instances.get(uid) if uid is not None else None
        native_webview = getattr(instance, "webview", None)
        if native_webview is not None:
            native_webview.evaluateJavaScript_completionHandler_(script, None)
            return True
    except Exception:
        pass
    evaluate = getattr(window, "evaluate_js", None)
    if callable(evaluate):
        threading.Thread(
            target=lambda: evaluate(script), daemon=True, name=f"history-{direction}"
        ).start()
        return True
    return False


def _find_edit_submenu(main_menu):
    if main_menu is None:
        return None
    items = list(main_menu.itemArray() or [])
    for item in items:
        submenu = item.submenu()
        if submenu is None:
            continue
        for sub_item in list(submenu.itemArray() or []):
            action = str(sub_item.action() or "")
            if action in {"cut:", "copy:", "paste:", "selectAll:"}:
                return submenu
    for item in items:
        submenu = item.submenu()
        if submenu is not None and str(submenu.title() or "") in {"Edit", "编辑"}:
            return submenu
    return None


_EDIT_MENU_TARGET_CLASSES: dict[type, type] = {}


def _edit_menu_target_class(base_cls: type) -> type:
    cls = _EDIT_MENU_TARGET_CLASSES.get(base_cls)
    if cls is not None:
        return cls

    class _TexadaEditHistoryMenuTarget(base_cls):
        def texadaUndo_(self, _sender):
            self._dispatch(self._window, "undo")

        def texadaRedo_(self, _sender):
            self._dispatch(self._window, "redo")

        def validateMenuItem_(self, item):
            action = str(item.action() or "")
            if action == "texadaUndo:":
                return self._bridge._history_enabled("undo")
            if action == "texadaRedo:":
                return self._bridge._history_enabled("redo")
            return True

    _EDIT_MENU_TARGET_CLASSES[base_cls] = _TexadaEditHistoryMenuTarget
    return _TexadaEditHistoryMenuTarget


def _install_macos_edit_history_menu(window, bridge: _DesktopBridge, *, app=None, appkit=None, dispatcher=None) -> bool:
    """macOS: 向系统菜单栏 Edit 菜单顶部注入「撤销 ⌘Z」「重做 ⇧⌘Z」（#54）。"""
    if appkit is None:
        if sys.platform != "darwin":
            return False
        try:
            import AppKit as appkit
        except Exception:
            return False
    try:
        ns_app = app if app is not None else appkit.NSApplication.sharedApplication()
        edit_menu = _find_edit_submenu(ns_app.mainMenu())
        if edit_menu is None:
            return False
        for existing in list(edit_menu.itemArray() or []):
            if str(existing.action() or "") == "texadaUndo:":
                return True

        dispatch = dispatcher if dispatcher is not None else _dispatch_macos_history_js
        base_cls = getattr(appkit, "NSObject", object)
        target_cls = _edit_menu_target_class(base_cls)
        target = target_cls.alloc().init() if hasattr(target_cls, "alloc") else target_cls()
        target._window = window
        target._bridge = bridge
        target._dispatch = dispatch
        cmd_mask = getattr(appkit, "NSEventModifierFlagCommand", getattr(appkit, "NSCommandKeyMask", 1 << 20))
        shift_mask = getattr(appkit, "NSEventModifierFlagShift", getattr(appkit, "NSShiftKeyMask", 1 << 17))

        undo_item = appkit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("撤销", "texadaUndo:", "z")
        undo_item.setTarget_(target)
        undo_item.setKeyEquivalentModifierMask_(cmd_mask)

        redo_item = appkit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("重做", "texadaRedo:", "Z")
        redo_item.setTarget_(target)
        redo_item.setKeyEquivalentModifierMask_(cmd_mask | shift_mask)

        separator = appkit.NSMenuItem.separatorItem()
        edit_menu.insertItem_atIndex_(separator, 0)
        edit_menu.insertItem_atIndex_(redo_item, 0)
        edit_menu.insertItem_atIndex_(undo_item, 0)
        _terminate_state["edit_menu_target"] = target
        return True
    except Exception:
        return False


def _schedule_macos_edit_history_menu(window, bridge: _DesktopBridge) -> None:
    if sys.platform != "darwin":
        return
    try:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(_install_macos_edit_history_menu, window, bridge)
    except Exception:
        pass


_terminate_state = {"window_closer": None, "shutdown": None, "signal_pump": None, "edit_menu_target": None, "terminating": False}
_watchdog_deadline = 5.0


def _on_terminate(signum, _frame):
    """SIGTERM/SIGINT 先尝试关窗(走正常清理);窗口未建立时执行清理,SIGTERM 仍契约式 0 退出。

    注意:Python 级信号处理器只会在主线程执行字节码时运行,而 webview.start()
    会把主线程阻塞在 Cocoa 事件循环里,本处理器可能永远得不到执行机会(#50)。
    因此另有信号泵(_install_signal_pump)与看门狗(_install_terminate_watchdog)双保险。
    """
    _terminate_action(signum, _terminate_state)


def _nudge_cocoa_event_loop() -> None:
    """macOS: NSApplication.stop_() 仅设置标志,无头 CI 无后续 NSEvent 时 run() 会阻塞;
    排入一条空 AppDefined NSEvent 确保事件循环立即唤醒检查停止标志并从 webview.start() 返回。
    """
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSEvent
        from PyObjCTools import AppHelper

        def _post():
            app = NSApplication.sharedApplication()
            event = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
                15, (0.0, 0.0), 0, 0.0, 0, None, 0, 0, 0
            )
            if event is not None:
                app.postEvent_atStart_(event, True)

        AppHelper.callAfter(_post)
    except Exception:
        pass


def _close_shown_windows(windows) -> bool:
    """仅对已完成原生 shown 的窗口调用 destroy();未就绪窗口直接回退 shutdown 避免主线程死锁。"""
    ready = [
        window for window in windows
        if getattr(getattr(window, "events", None), "shown", None) is None
        or window.events.shown.is_set()
    ]
    if not ready:
        return False
    for window in ready:
        if hasattr(window, "confirm_close"):
            window.confirm_close = False
        window.destroy()
    _nudge_cocoa_event_loop()
    return True


def _terminate_action(signum, state, exiter=None):
    """终止动作核心(可注入 exiter 供测试)。

    契约(#50 / E2E-5 发行验收):SIGTERM 无论落在「窗口建立前的启动窗口」还是
    窗口建立后,都必须执行已注册清理并有界地以退出码 0 结束;SIGINT(开发者 Ctrl-C)
    在清理后保持默认信号退出语义不变。
    """
    exiter = os._exit if exiter is None else exiter
    state["terminating"] = True
    bridge = state.get("bridge")
    if bridge is not None:
        bridge._mark_terminating()
    closer = state.get("window_closer")
    if closer:
        try:
            if closer() is not False:
                return
        except Exception:
            pass
    shutdown = state.get("shutdown")
    if callable(shutdown):
        state["shutdown"] = None
        try:
            shutdown()
        except Exception:
            pass  # 清理失败也必须退出,保证有界
    if signum == signal.SIGTERM:
        exiter(0)
        return
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


_SIGNAL_PUMP_CLASS = None


def _install_signal_pump(interval=0.2):
    """macOS:让主 run loop 周期执行 Python 回调,待决信号处理器才能及时运行。

    信号到达后 CPython 只置待决标志;主线程必须执行到字节码才会调用 Python 级处理器。
    每 interval 秒执行一次回调把执行权带回解释器,_on_terminate 就能走 window_closer
    正常清理。仅注册 NSTimer;失败时返回 False,不影响其它路径。
    """
    global _SIGNAL_PUMP_CLASS
    try:
        from Foundation import NSObject, NSTimer, NSRunLoop, NSRunLoopCommonModes
    except Exception:
        return False

    try:
        if _SIGNAL_PUMP_CLASS is None:
            class _SignalPump(NSObject):
                def tick_(self, _timer):
                    return None  # 执行 Python 字节码即可触发待决信号处理器

            _SIGNAL_PUMP_CLASS = _SignalPump
        pump = _SIGNAL_PUMP_CLASS.alloc().init()
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            interval, pump, "tick:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
        _terminate_state["signal_pump"] = timer  # 保持引用,防止被回收
        return True
    except Exception:
        return False


def _read_wakeup_bytes(channel) -> bytes:
    if hasattr(channel, "recv"):
        return channel.recv(64)
    return os.read(channel, 64)


def _terminate_watchdog(read_channel, state, deadline=_watchdog_deadline, exiter=None):
    """看门狗线程体:收到唤醒字节后有界等待,随后自行清理并强制退出。

    信号到达时 CPython 会把信号编号写进 set_wakeup_fd 通道,读到非空字节即知收到了信号。
    未收到真实唤醒字节前的任何 OSError/EOF 直接返回,绝不误杀进程;收到首个信号后保持
    deadline 秒兜底武装(防止主线程返回后解释器/WebKit 析构阶段卡死),除非 force 关闭。
    """
    exiter = os._exit if exiter is None else exiter
    woken = False
    try:
        readable, _, _ = select.select([read_channel], [], [])
        if not readable or state.get("closing"):
            return
        first = _read_wakeup_bytes(read_channel)
        if not first or state.get("closing"):
            return
        woken = True
        state["woken"] = True
        readable2, _, _ = select.select([read_channel], [], [], deadline)
        if state.get("closing"):
            return
        if readable2:
            try:
                second = _read_wakeup_bytes(read_channel)
            except OSError:
                if state.get("closing"):
                    return
                second = b"\x01"
            if not second or state.get("closing"):
                return
        shutdown = state.get("shutdown")
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass  # 清理失败也必须退出,保证有界
        exiter(0)
    except Exception:
        if not woken or state.get("closing"):
            return
        shutdown = state.get("shutdown")
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass
        exiter(0)


def _close_terminate_watchdog(state, *, force: bool = False) -> None:
    """空闲退出时关闭唤醒通道(socketpair / pipe);若已收到终止信号且非 force,保持看门狗武装兜底析构卡死。"""
    if state.get("woken") and not force:
        return
    state["closing"] = True
    state["woken"] = False
    sockets = state.pop("wakeup_sockets", None)
    pipe_fds = state.pop("wakeup_pipe", None)
    if not sockets and not pipe_fds:
        return
    try:
        signal.set_wakeup_fd(-1)
    except (OSError, ValueError):
        pass
    for sock in reversed(sockets or ()):
        try:
            sock.close()
        except OSError:
            pass
    for fd in reversed(pipe_fds or ()):
        try:
            os.close(fd)
        except OSError:
            pass


def _install_terminate_watchdog(state, deadline=_watchdog_deadline, *, os_name=None):
    """安装唤醒通道与看门狗线程:POSIX 用原生 os.pipe,Windows 用 Winsock socketpair。"""
    effective_os = os_name if os_name is not None else os.name
    _close_terminate_watchdog(state, force=True)
    state["closing"] = False
    state["woken"] = False
    if effective_os != "nt":
        read_fd = write_fd = None
        try:
            read_fd, write_fd = os.pipe()
            os.set_blocking(write_fd, False)
            signal.set_wakeup_fd(write_fd, warn_on_full_buffer=False)
        except (OSError, ValueError):
            for fd in (write_fd, read_fd):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            return False
        state["wakeup_pipe"] = (read_fd, write_fd)
        threading.Thread(
            target=_terminate_watchdog, args=(read_fd, state),
            kwargs={"deadline": deadline}, daemon=True, name="terminate-watchdog",
        ).start()
        return True

    read_sock = write_sock = None
    try:
        read_sock, write_sock = socket.socketpair()
        read_sock.setblocking(False)
        write_sock.setblocking(False)
        signal.set_wakeup_fd(write_sock.fileno(), warn_on_full_buffer=False)
    except (OSError, ValueError):
        for sock in (write_sock, read_sock):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        return False
    state["wakeup_sockets"] = (read_sock, write_sock)
    threading.Thread(
        target=_terminate_watchdog, args=(read_sock, state),
        kwargs={"deadline": deadline}, daemon=True, name="terminate-watchdog",
    ).start()
    return True


def _reusable_entry(previous, requested_port) -> bool:
    if not entry_alive(previous):
        return False
    if requested_port is not None and urllib.parse.urlsplit(previous["url"]).port != requested_port:
        return False
    return wait_for_http(previous["url"], timeout=3.0)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TeXada Studio 桌面窗口")
    parser.add_argument("--port", type=int, help="Studio 端口(默认沿用启动器 8888)")
    parser.add_argument("--state-dir", type=Path, help="用户数据目录(默认系统应用数据目录)")
    parser.add_argument("--timeout", type=float, default=120.0, help="等待启动器就绪的秒数")
    args = parser.parse_args(argv)

    state_dir = args.state_dir or DEFAULT_STATE_DIR
    port = args.port or 8888
    _terminate_state["window_closer"] = None
    _terminate_state["shutdown"] = None
    _terminate_state["bridge"] = None
    _terminate_state["edit_menu_target"] = None
    _terminate_state["terminating"] = False
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, _on_terminate)
    previous = read_entry(state_dir)
    runtime = {"child": None}
    server_box = {}

    def _cleanup():
        child = runtime["child"]
        if child is not None:
            stop_launcher(child)
            _scrub_child_session(state_dir, child.pid)
        if server_box:
            stop_backend_thread(server_box, state_dir)

    try:
        if _reusable_entry(previous, args.port):
            entry = previous
        elif BUNDLE_DIR is not None:
            _terminate_state["shutdown"] = _cleanup
            start_backend_thread(state_dir, port, server_box)
            if server_box.get("error"):
                stop_backend_thread(server_box, state_dir)
                print(f"捆绑后端未就绪:{server_box['error']}", file=sys.stderr)
                return 1
            _register_session_atexit(server_box, state_dir)
            backend_dead = lambda: bool(server_box.get("error")) or (
                server_box.get("thread") is not None and not server_box["thread"].is_alive()
            )
            entry = wait_for_entry(
                state_dir,
                args.timeout,
                abort_if=backend_dead,
                expected_url=server_box["record"]["url"],
            )
            if entry is None or not wait_for_http(
                entry["url"], timeout=min(args.timeout, 30.0), abort_if=backend_dead
            ):
                stop_backend_thread(server_box, state_dir)
                print(f"捆绑后端未就绪:{server_box.get('error', '等待超时')}", file=sys.stderr)
                return 1
        else:
            _terminate_state["shutdown"] = _cleanup
            try:
                runtime["child"] = subprocess.Popen(
                    launcher_argv(state_dir, args.port), cwd=str(REPO_ROOT), env=launcher_env()
                )
            except OSError as error:
                print(f"无法启动本地启动器:{error}", file=sys.stderr)
                return 1
            entry = wait_for_entry(
                state_dir,
                args.timeout,
                previous_pid=previous and previous.get("pid"),
                child=runtime["child"],
            )
            if entry is None:
                _cleanup()
                print("等待本地服务就绪超时;请先用 run-local-studio.py --check 核对依赖。", file=sys.stderr)
                return 1

        try:
            import webview
        except ImportError:
            _cleanup()
            print("缺少桌面窗口依赖:捆绑包不应出现此错误;仓库模式请先 .venv/bin/pip install -r desktop/requirements.txt", file=sys.stderr)
            return 1

        try:
            storage_dir = _prepare_webview_storage(state_dir)
        except (OSError, RuntimeError) as error:
            _cleanup()
            print(f"无法初始化桌面存储目录:{error}", file=sys.stderr)
            return 1

        settings = getattr(webview, "settings", None)
        if settings is not None and hasattr(settings, "__setitem__"):
            settings["ALLOW_DOWNLOADS"] = True

        bridge = _DesktopBridge(webview)
        window = webview.create_window(
            "TeXada Studio",
            entry["url"],
            width=1440,
            height=900,
            min_size=(1024, 640),
            js_api=bridge,
        )
        bridge._attach(window)
        shown_event = getattr(getattr(window, "events", None), "shown", None)
        if shown_event is not None and sys.platform == "darwin":
            try:
                shown_event += lambda: _schedule_macos_edit_history_menu(window, bridge)
            except Exception:
                pass
        _terminate_state["bridge"] = bridge
        _terminate_state["window_closer"] = lambda: _close_shown_windows(webview.windows)
        _terminate_state["shutdown"] = _cleanup
        _install_signal_pump()
        _install_terminate_watchdog(_terminate_state)
        webview.start(
            private_mode=False,
            storage_path=str(storage_dir),
            localization=_DESKTOP_LOCALIZATION,
        )
        _cleanup()
        return 0
    finally:
        _close_terminate_watchdog(_terminate_state)
        _terminate_state["window_closer"] = None
        _terminate_state["shutdown"] = None
        _terminate_state["bridge"] = None
        _terminate_state["edit_menu_target"] = None
        _terminate_state["terminating"] = False


if __name__ == "__main__":
    raise SystemExit(main())
