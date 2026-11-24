# PyInstaller Windows 冻结入口:定位 Resources 捆绑目录并以别名加载 desktop/app.py(避免占用 "app" 模块名)。
"""同时承接冻结包内 `[sys.executable, <script.py>, ...]` / `-m` / `-c` 子进程调用,
使 `webui/app.py` 与 `harness` 在无系统 Python 的机器上仍能通过 `sys.executable` 运行确定性检查器。
"""
from __future__ import annotations

import importlib.util
import multiprocessing
import os
import runpy
import sys
from pathlib import Path


def resolve_bundle_dir(executable: Path | None = None, meipass: str | None = None) -> Path:
    exe = (Path(executable) if executable is not None else Path(sys.executable)).resolve()
    candidates: list[Path] = [exe.parent / "Resources"]
    raw_meipass = meipass if meipass is not None else getattr(sys, "_MEIPASS", None)
    if raw_meipass:
        candidates.append(Path(raw_meipass).resolve())
    candidates.extend((exe.parent / "_internal", exe.parent, Path(__file__).resolve().parents[1]))
    for candidate in candidates:
        if (candidate / "desktop" / "app.py").is_file():
            return candidate.resolve()
    return (exe.parent / "Resources").resolve()


def _exit_code_from_system_exit(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    if isinstance(exc.code, int):
        return exc.code
    print(exc.code, file=sys.stderr)
    return 1


def _ensure_bundle_sys_path(bundle_dir: Path) -> None:
    for subdir in ("harness", "webui"):
        entry = str(bundle_dir / subdir)
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _prepare_stdio_and_utf8() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    elif callable(getattr(sys.stdin, "reconfigure", None)):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            pass
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    elif callable(getattr(sys.stdout, "reconfigure", None)):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            pass
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    elif callable(getattr(sys.stderr, "reconfigure", None)):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            pass


def run_entry(argv: list[str] | None = None, *, executable: Path | None = None) -> int:
    multiprocessing.freeze_support()
    _prepare_stdio_and_utf8()
    effective_argv = list(sys.argv if argv is None else argv)
    bundle_dir = resolve_bundle_dir(executable=executable)
    os.environ.setdefault("TEXADA_BUNDLE_DIR", str(bundle_dir))

    if len(effective_argv) >= 3 and effective_argv[1] == "-c":
        _ensure_bundle_sys_path(bundle_dir)
        sys.argv = ["-c", *effective_argv[3:]]
        try:
            exec(compile(effective_argv[2], "<string>", "exec"), {"__name__": "__main__"})
        except SystemExit as exc:
            return _exit_code_from_system_exit(exc)
        return 0

    if len(effective_argv) >= 3 and effective_argv[1] == "-m":
        _ensure_bundle_sys_path(bundle_dir)
        mod_name = effective_argv[2]
        sys.argv = [mod_name, *effective_argv[3:]]
        try:
            runpy.run_module(mod_name, run_name="__main__", alter_sys=True)
        except SystemExit as exc:
            return _exit_code_from_system_exit(exc)
        return 0

    if (
        len(effective_argv) >= 2
        and not effective_argv[1].startswith("-")
        and effective_argv[1].lower().endswith(".py")
        and Path(effective_argv[1]).is_file()
    ):
        _ensure_bundle_sys_path(bundle_dir)
        script = str(Path(effective_argv[1]).resolve())
        script_dir = os.path.dirname(script)
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        sys.argv = [script, *effective_argv[2:]]
        try:
            runpy.run_path(script, run_name="__main__")
        except SystemExit as exc:
            return _exit_code_from_system_exit(exc)
        return 0

    desktop_script = bundle_dir / "desktop" / "app.py"
    spec = importlib.util.spec_from_file_location("texada_desktop_app", str(desktop_script))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载桌面入口:{desktop_script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["texada_desktop_app"] = module
    spec.loader.exec_module(module)
    return int(module.main(effective_argv[1:]))


if __name__ == "__main__":
    raise SystemExit(run_entry())
