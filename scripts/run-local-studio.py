#!/usr/bin/env python3
"""Start the local Studio with private access and optional owned model runtime."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import webbrowser


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "webui"))
from local_runtime import DEFAULT_BASE, DEFAULT_MODEL, LocalRuntime, LocalRuntimeError, _model_name, validate_base_url


def default_state_dir():
    override = os.environ.get("TEXADA_STUDIO_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TeXada Studio"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "TeXada Studio"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "texada-studio"


def parser():
    result = argparse.ArgumentParser(description="启动 TeXada Studio 本地版。不会下载模型或自动安装依赖。")
    result.add_argument("--no-browser", action="store_true", help="不自动打开浏览器；私密入口保存在数据目录 session.json")
    result.add_argument("--no-auto-model", action="store_true", help="仅复用已有模型服务，不启动模型")
    result.add_argument("--port", type=int, default=8888, help="本机 Studio 端口（默认 8888）")
    result.add_argument("--model-port", type=int, default=18081, help="自有模型服务端口（默认 18081）")
    result.add_argument("--state-dir", type=Path, help="用户数据目录，默认系统应用数据目录")
    result.add_argument("--base-url", help="本机 OpenAI 兼容模型地址")
    result.add_argument("--model", help=f"模型名称（默认 {DEFAULT_MODEL}，或保留已保存设置）")
    result.add_argument("--gguf", type=Path, help="本机 GGUF 权重路径")
    result.add_argument("--mmproj", type=Path, help="本机视觉 projector 路径")
    result.add_argument("--check", action="store_true", help="只检查本机依赖与配置，不联网、不启动服务、不写会话")
    return result


def clean_environment(source):
    """The local app and any owned model process receive no cloud credentials."""
    return {key: value for key, value in source.items()
            if "API_KEY" not in key.upper() and not key.upper().endswith(("_TOKEN", "_SECRET"))
            and key.upper() not in {"DEMO_TOKEN", "VLM_BASE_URL", "VLM_MODEL", "TEXADA_OPENAI_BASE_URL"}}


def dependency_status():
    modules = {name: importlib.util.find_spec(name) is not None
               for name in ("fastapi", "uvicorn", "sympy", "antlr4")}
    compiler = os.path.expanduser(os.environ.get("TECTONIC", "tectonic"))
    tools = {"tectonic": bool(shutil.which(compiler)),
             "pdftoppm": bool(shutil.which("pdftoppm")), "pdfinfo": bool(shutil.which("pdfinfo"))}
    return {"python": sys.version_info >= (3, 11), "modules": modules, "tools": tools}


def report_dependencies(status):
    missing = [name for name, ready in status["modules"].items() if not ready]
    if not status["python"]:
        print("需要 Python 3.11 或更新版本。", flush=True)
    if missing:
        print("缺少 Python 依赖：" + "、".join(missing), flush=True)
        print("请在项目虚拟环境安装：python -m pip install -r webui/requirements.txt", flush=True)
    else:
        print("编辑与文档检查依赖已就绪。", flush=True)
    absent_tools = [name for name, ready in status["tools"].items() if not ready]
    if absent_tools:
        print("可选工具尚未就绪：" + "、".join(absent_tools) + "；相应 PDF 编译/导入功能将提示安装。", flush=True)
        if "tectonic" in absent_tools:
            print("提示:可在 Studio 设置中点「下载 Tectonic」,或运行 scripts/install_local_tools.py。", flush=True)
    else:
        print("本地 PDF 编译与页面转换工具已就绪。", flush=True)
    return status["python"] and not missing


def _listen_available(port):
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(8))
    try:
        with open(temporary, "x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _alive(pid):
    if type(pid) is not int or pid < 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def acquire_lock(state):
    path = state / "launcher.lock"
    for _ in range(2):
        try:
            with open(path, "x", encoding="utf-8") as stream:
                os.chmod(path, 0o600)
                stream.write(str(os.getpid()))
            return path
        except FileExistsError:
            try:
                pid = int(path.read_text().strip())
            except (OSError, ValueError):
                raise RuntimeError("启动锁无法读取，请检查数据目录中的 launcher.lock。") from None
            if _alive(pid):
                raise RuntimeError("这个数据目录已有 Studio 在运行；请继续使用已打开的窗口。")
            path.unlink()
    raise RuntimeError("无法取得本地启动锁。")


def find_model_files(args):
    models = Path.home() / ".texada" / "models"
    gguf = args.gguf.expanduser() if args.gguf else models / "MiniCPM-V-4_7-1B-Q4_K_M.gguf"
    mmproj = args.mmproj.expanduser() if args.mmproj else models / "mmproj-model-f16.gguf"
    executable = shutil.which("llama-server")
    if not executable:
        for candidate in (Path.home() / ".texada" / "bin" / "llama-server",
                          Path.home() / ".texada" / "runtime" / "llama-server"):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                executable = str(candidate)
                break
    return executable, gguf, mmproj


def _probe_service(base, model):
    # Temporary object uses no persisted settings, so each candidate really is probed.
    from local_runtime import local_json_request
    try:
        data = local_json_request(base + "/models", timeout=2)
        models = [entry["id"] for entry in data.get("data", [])
                  if isinstance(entry, dict) and isinstance(entry.get("id"), str)]
        return {"reachable": isinstance(data.get("data"), list), "available": model in models}
    except (LocalRuntimeError, TypeError):
        return {"reachable": False, "available": False}


def select_service(config, args):
    candidates = [config["base_url"]]
    if not args.base_url:
        candidates.extend((f"http://127.0.0.1:{args.model_port}/v1", "http://127.0.0.1:8080/v1", DEFAULT_BASE))
    reachable = None
    for base in dict.fromkeys(candidates):
        status = _probe_service(base, config["model"])
        if status["available"]:
            return base
        if status["reachable"] and reachable is None:
            reachable = base
    # A running Ollama service does not imply the requested MiniCPM is loaded.
    # Automatic mode must still be allowed to start the actual local checkpoint.
    return reachable if args.no_auto_model else None


def launch_owned_model(args, config, state, environment):
    if args.gguf is None and config["model"] != DEFAULT_MODEL:
        print("当前模型名称与默认 MiniCPM 权重不同；未自动加载或重命名权重。请连接对应模型服务，或用 --gguf 明确指定权重。", flush=True)
        return None
    executable, gguf, mmproj = find_model_files(args)
    if not executable or not gguf.is_file() or not mmproj.is_file():
        print("本机模型尚未连接，且未找到完整的 llama-server/1B GGUF/projector。可先使用编辑与检查，之后在连接设置中配置。", flush=True)
        return None
    if not _listen_available(args.model_port):
        print("模型端口已被其他进程占用；没有停止或替换它。可在连接设置中选择已有服务。", flush=True)
        return None
    logfile = state / "model-server.log"
    stream = open(logfile, "ab")
    os.chmod(logfile, 0o600)
    command = [executable, "-m", str(gguf), "--mmproj", str(mmproj), "--alias", config["model"],
               "--host", "127.0.0.1", "--port", str(args.model_port), "--ctx-size", "8192",
               "--parallel", "1", "-ngl", "99", "--jinja", "--reasoning", "off"]
    try:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                   env=environment, start_new_session=True)
    except OSError:
        stream.close()
        print("本机模型进程无法启动；请检查 llama-server 与权重文件。", flush=True)
        return None
    stream.close()
    print("正在加载本机 1B 视觉模型…", flush=True)
    return process


def stop_owned_model(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def existing_session_url(state, port):
    """Recover only this profile's live, exact loopback Studio entry point."""
    path = state / "session.json"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("running") is not True or not _alive(record.get("pid")):
            return None
        url = record.get("url")
        if not isinstance(url, str) or any(ord(char) < 32 for char in url):
            return None
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, max_num_fields=1)
        if (parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.port != port
                or parts.username is not None or parts.password is not None or parts.fragment
                or parts.path != "/studio" or len(query) != 1 or query[0][0] != "token"
                or not 0 < len(query[0][1]) <= 256):
            return None
        return url
    except (OSError, ValueError, UnicodeError):
        return None


LOCAL_TOOL_BIN = Path.home() / ".texada" / "bin"


def prepend_local_bin(path_value):
    """把 ~/.texada/bin(install_local_tools.py 的安装位置)放到 PATH 最前。"""
    entries = [entry for entry in (path_value or "").split(os.pathsep) if entry]
    local = str(LOCAL_TOOL_BIN)
    if local in entries:
        return path_value
    return os.pathsep.join([local, *entries])


def watch_parent_exit(server):
    """TEXADA_EXIT_WHEN_ORPHANED=1 时,父进程消失(桌面窗口被强杀)就优雅退出。"""
    if os.environ.get("TEXADA_EXIT_WHEN_ORPHANED") != "1":
        return None
    parent = os.getppid()
    def watch():
        while True:
            time.sleep(2)
            try:
                if os.getppid() != parent:
                    server.should_exit = True
                    return
            except OSError:
                return
    import threading
    thread = threading.Thread(target=watch, daemon=True, name="parent-watch")
    thread.start()
    return thread


def run(args):
    if not 1 <= args.port <= 65535 or not 1 <= args.model_port <= 65535 or args.port == args.model_port:
        raise RuntimeError("Studio 与模型端口必须是 1–65535 内不同的端口。")
    os.environ["PATH"] = prepend_local_bin(os.environ.get("PATH", ""))
    status = dependency_status()
    ready = report_dependencies(status)
    state = (args.state_dir or default_state_dir()).expanduser().resolve()
    runtime = LocalRuntime(state)
    config = runtime.get_config()
    values = None
    if args.base_url or args.model:
        values = {"base_url": validate_base_url(args.base_url) if args.base_url else config["base_url"],
                  "model": _model_name(args.model) if args.model else config["model"]}
        config = {**config, **values}
    if args.check:
        print("离线检查完成；没有连接模型、启动服务或写入会话。", flush=True)
        return 0 if ready else 2
    if not ready:
        return 2
    existing_url = existing_session_url(state, args.port)
    if existing_url:
        if args.no_browser:
            print("此数据目录的 TeXada Studio 已在运行；没有启动新进程。私密入口仍保存在 session.json。", flush=True)
        else:
            webbrowser.open(existing_url)
            print("已重新打开正在运行的 TeXada Studio。", flush=True)
        return 0
    if not _listen_available(args.port):
        raise RuntimeError("Studio 端口已被占用，请用 --port 选择其他端口。")
    state.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(state)
    owned_model, server, session_id = None, None, secrets.token_hex(12)
    old_terminate_handler = signal.getsignal(signal.SIGTERM)
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    session_path = state / "session.json"
    environment = clean_environment(dict(os.environ))
    environment["PATH"] = prepend_local_bin(environment.get("PATH"))
    environment.update(TEXADA_LOCAL_MODE="1", TEXADA_STUDIO_STATE_DIR=str(state),
                       VLM_MODEL=config["model"], VLM_BASE_URL=config["base_url"],
                       SKILL_MODE="on", DEMO_TOKEN=secrets.token_urlsafe(32))
    try:
        if values is not None:
            config = runtime.update_settings(values)
        base = select_service(config, args)
        if base is None and not args.no_auto_model:
            if args.base_url:
                print("指定的本机地址未提供目标模型；已保留该地址，没有切换路由或自动启动其他服务。请在 Studio 中检查连接。", flush=True)
            else:
                owned_model = launch_owned_model(args, config, state, environment)
                if owned_model is not None:
                    base = f"http://127.0.0.1:{args.model_port}/v1"
        if base is not None:
            config = runtime.update_settings({"base_url": base, "model": config["model"]})
            environment["VLM_BASE_URL"] = base
            print("已选择本机模型服务；连接状态可在 Studio 中检查。", flush=True)
        elif args.no_auto_model:
            print("未连接到已有模型；编辑与规则检查仍可使用。", flush=True)
        # Imported only after dependency checks and environment setup.
        os.environ.clear()
        os.environ.update(environment)
        import uvicorn
        studio_base = f"http://127.0.0.1:{args.port}"
        private_url = studio_base + "/studio?token=" + environment["DEMO_TOKEN"]
        record = {"session_id": session_id, "pid": os.getpid(), "url": private_url,
                  "base_url": studio_base, "model_base_url": environment["VLM_BASE_URL"],
                  "model": config["model"], "owned_model_pid": owned_model.pid if owned_model else None,
                  "created_at": time.time(), "running": True}
        private_json(session_path, record)
        print("TeXada Studio 本地版正在启动：" + studio_base, flush=True)
        print("私密入口已保存在用户数据目录的 session.json。按 Ctrl+C 退出。", flush=True)
        server = uvicorn.Server(uvicorn.Config("app:app", host="127.0.0.1", port=args.port,
                                               workers=1, access_log=False, log_level="warning"))
        watch_parent_exit(server)
        # Delay browser launch until the listener is ready, without blocking startup.
        if not args.no_browser:
            import threading
            def open_when_ready():
                for _ in range(100):
                    if server.started:
                        webbrowser.open(private_url)
                        return
                    if server.should_exit:
                        return
                    time.sleep(0.1)
            threading.Thread(target=open_when_ready, daemon=True).start()
        server.run()
        return 0
    finally:
        stop_owned_model(owned_model)
        signal.signal(signal.SIGTERM, old_terminate_handler)
        try:
            if session_path.exists():
                record = json.loads(session_path.read_text(encoding="utf-8"))
                if record.get("session_id") == session_id:
                    record.update(running=False, stopped_at=time.time(), url=None)
                    private_json(session_path, record)
        except (OSError, ValueError):
            pass
        try:
            if lock.read_text().strip() == str(os.getpid()):
                lock.unlink()
        except OSError:
            pass


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return run(args)
    except (LocalRuntimeError, RuntimeError) as exc:
        print("无法启动：" + str(exc), file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
