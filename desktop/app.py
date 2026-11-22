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

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = Path(os.environ["TEXADA_BUNDLE_DIR"]).resolve() if os.environ.get("TEXADA_BUNDLE_DIR") else None
LAUNCHER = (BUNDLE_DIR or REPO_ROOT) / "scripts" / "run-local-studio.py"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "TeXada Studio"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
TEX_CACHE_SOURCE = BUNDLE_DIR / "tex-cache" if BUNDLE_DIR else None
TEX_CACHE_TARGET = Path.home() / "Library" / "Caches" / "TectonicProject.Tectonic"


def tool_bin_dirs():
    """PATH 前置目录:捆绑 bin(自包含包)与 ~/.texada/bin(一键安装位置)。"""
    dirs = [Path.home() / ".texada" / "bin"]
    if BUNDLE_DIR is not None:
        dirs.insert(0, BUNDLE_DIR / "bin")
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
    return {"url": url, "pid": pid if isinstance(pid, int) else None,
            "running": record.get("running") is True}


def entry_alive(entry) -> bool:
    """会话记录是否指向一个仍在运行的启动器进程。"""
    if not entry or not entry["running"] or not isinstance(entry.get("pid"), int):
        return False
    try:
        os.kill(entry["pid"], 0)
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
        with tempfile.NamedTemporaryFile(dir=destination.parent) as staging:
            shutil.copyfile(entry, staging.name)
            try:
                os.link(staging.name, destination)
            except FileExistsError:
                continue
        copied = True
    return copied


def start_backend_thread(state_dir: Path, port, server_box: dict):
    """捆绑模式:进程内线程跑 uvicorn;窗口进程退出即无残留。"""
    if not _port_available(port):
        server_box["error"] = f"端口 {port} 已被占用"
        return server_box

    seed_tex_cache()
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


_terminate_state = {"window_closer": None, "shutdown": None, "signal_pump": None}
_watchdog_deadline = 5.0


def _on_terminate(signum, _frame):
    """SIGTERM/SIGINT 先尝试关窗(走正常清理);窗口未建立时执行清理,SIGTERM 仍契约式 0 退出。

    注意:Python 级信号处理器只会在主线程执行字节码时运行,而 webview.start()
    会把主线程阻塞在 Cocoa 事件循环里,本处理器可能永远得不到执行机会(#50)。
    因此另有信号泵(_install_signal_pump)与看门狗(_install_terminate_watchdog)双保险。
    """
    _terminate_action(signum, _terminate_state)


def _terminate_action(signum, state, exiter=None):
    """终止动作核心(可注入 exiter 供测试)。

    契约(#50 / E2E-5 发行验收):SIGTERM 无论落在「窗口建立前的启动窗口」还是
    窗口建立后,都必须执行已注册清理并有界地以退出码 0 结束;SIGINT(开发者 Ctrl-C)
    在清理后保持默认信号退出语义不变。
    """
    exiter = os._exit if exiter is None else exiter
    closer = state.get("window_closer")
    if closer:
        try:
            closer()
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


def _install_signal_pump(interval=0.2):
    """macOS:让主 run loop 周期执行 Python 回调,待决信号处理器才能及时运行。

    信号到达后 CPython 只置待决标志;主线程必须执行到字节码才会调用 Python 级处理器。
    每 interval 秒执行一次回调把执行权带回解释器,_on_terminate 就能走 window_closer
    正常清理。仅注册 NSTimer;失败时返回 False,不影响其它路径。
    """
    try:
        from Foundation import NSObject, NSTimer, NSRunLoop, NSRunLoopCommonModes
    except Exception:
        return False

    class _SignalPump(NSObject):
        def tick_(self, _timer):
            return None  # 执行 Python 字节码即可触发待决信号处理器

    try:
        pump = _SignalPump.alloc().init()
        timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            interval, pump, "tick:", None, True)
        NSRunLoop.currentRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
        _terminate_state["signal_pump"] = timer  # 保持引用,防止被回收
        return True
    except Exception:
        return False


def _terminate_watchdog(read_fd, state, deadline=_watchdog_deadline, exiter=None):
    """看门狗线程体:收到唤醒字节后有界等待,随后自行清理并强制退出。

    信号到达时 CPython 会把信号编号写进 set_wakeup_fd 的管道,读到字节即知收到了
    信号。第一个字节后至多再等 deadline 秒让主线程走正常退出;期间再来第二个信号
    则立即强制。随后执行清理钩子(标记会话停止、停止后端)并退出,保证有界退出。
    """
    exiter = os._exit if exiter is None else exiter
    try:
        select.select([read_fd], [], [])  # 阻塞等待第一个唤醒字节
        os.read(read_fd, 64)
        readable, _, _ = select.select([read_fd], [], [], deadline)
        if readable:
            os.read(read_fd, 64)
        shutdown = state.get("shutdown")
        if callable(shutdown):
            try:
                shutdown()
            except Exception:
                pass  # 清理失败也必须退出,保证有界
        exiter(0)
    except Exception:
        exiter(0)


def _install_terminate_watchdog(state, deadline=_watchdog_deadline):
    """安装 set_wakeup_fd 管道与看门狗线程;失败时返回 False。"""
    try:
        read_fd, write_fd = os.pipe()
        os.set_blocking(write_fd, False)
        signal.set_wakeup_fd(write_fd)
    except (OSError, ValueError):
        return False
    threading.Thread(
        target=_terminate_watchdog, args=(read_fd, state),
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

        webview.create_window("TeXada Studio", entry["url"], width=1440, height=900, min_size=(1024, 640))
        _terminate_state["window_closer"] = lambda: [window.destroy() for window in webview.windows]
        _terminate_state["shutdown"] = _cleanup
        _install_signal_pump()
        _install_terminate_watchdog(_terminate_state)
        webview.start()
        _cleanup()
        return 0
    finally:
        _terminate_state["window_closer"] = None
        _terminate_state["shutdown"] = None


if __name__ == "__main__":
    raise SystemExit(main())
