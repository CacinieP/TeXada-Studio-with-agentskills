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
import signal
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "run-local-studio.py"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
DEFAULT_STATE_DIR = Path.home() / "Library" / "Application Support" / "TeXada Studio"
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def backend_python():
    """启动器使用的解释器:优先仓库 venv(窗口进程被 py2app 打包时仍指回仓库)。"""
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


def wait_for_entry(state_dir: Path, timeout: float, previous_pid=None):
    """轮询等待启动器写出新的可用会话;超时返回 None。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = read_entry(state_dir)
        if entry_alive(entry) and entry["pid"] != previous_pid:
            return entry
        time.sleep(0.5)
    return None


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
    return env


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


_terminate_state = {"window_closer": None}


def _on_terminate(signum, _frame):
    """SIGTERM/SIGINT 先尝试关窗(走正常清理);窗口未建立时恢复默认行为。"""
    closer = _terminate_state.get("window_closer")
    if closer:
        try:
            closer()
            return
        except Exception:
            pass
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TeXada Studio 桌面窗口")
    parser.add_argument("--port", type=int, help="Studio 端口(默认沿用启动器 8888)")
    parser.add_argument("--state-dir", type=Path, help="用户数据目录(默认系统应用数据目录)")
    parser.add_argument("--timeout", type=float, default=120.0, help="等待启动器就绪的秒数")
    args = parser.parse_args(argv)

    state_dir = args.state_dir or DEFAULT_STATE_DIR
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, _on_terminate)
    previous = read_entry(state_dir)
    child = None
    if entry_alive(previous):
        entry = previous
    else:
        try:
            child = subprocess.Popen(launcher_argv(state_dir, args.port), cwd=str(REPO_ROOT),
                                      env=launcher_env())
        except OSError as error:
            print(f"无法启动本地启动器:{error}", file=sys.stderr)
            return 1
        entry = wait_for_entry(state_dir, args.timeout, previous_pid=previous and previous.get("pid"))
        if entry is None:
            stop_launcher(child)
            print("等待本地服务就绪超时;请先用 run-local-studio.py --check 核对依赖。", file=sys.stderr)
            return 1

    try:
        import webview
    except ImportError:
        if child is not None:
            stop_launcher(child)
        print("缺少桌面窗口依赖:请先 .venv/bin/pip install -r desktop/requirements.txt", file=sys.stderr)
        return 1

    webview.create_window("TeXada Studio", entry["url"], width=1440, height=900, min_size=(1024, 640))
    _terminate_state["window_closer"] = lambda: [window.destroy() for window in webview.windows]
    webview.start()
    if child is not None:
        stop_launcher(child)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
