"""TeXada Studio 本地编辑器后端（FastAPI）。

启动（仓库根目录，先设置 DEMO_TOKEN）:
  python -m uvicorn app:app --host 127.0.0.1 --port 8888 --app-dir webui
配置与依赖见 README.md；仅用于可信用户的单进程部署。
"""

import hashlib
import hmac
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlsplit
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from document_store import DocumentStore, DocumentError, document_name, document_text, text_hash
from local_runtime import (
    DEFAULT_BASE,
    DEFAULT_MODEL,
    MAX_FILE_BYTES,
    MAX_IMAGE_PIXELS,
    MAX_PDF_PAGES,
    LocalRuntime,
    LocalRuntimeError,
    _model_name,
    make_local_provider,
    validate_base_url,
)
from managed_models import ManagedModels, PROFILES
import tool_fetch

TOKEN = os.environ.get("DEMO_TOKEN", "")
if not TOKEN.strip():
    raise RuntimeError("DEMO_TOKEN must be set to a non-empty secret before starting the server")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(REPO, "state", "demo")
VLM_MODEL = os.environ.get("VLM_MODEL", DEFAULT_MODEL)
VLM_BASE_URL = os.environ.get("VLM_BASE_URL") or os.environ.get("VLM_BASE") or DEFAULT_BASE
_INITIAL_LOCAL_MODE = os.environ.get("TEXADA_LOCAL_MODE", "1") == "1"
LOCAL_MODE = _INITIAL_LOCAL_MODE


def _is_local_mode() -> bool:
    if LOCAL_MODE != _INITIAL_LOCAL_MODE:
        return bool(LOCAL_MODE)
    if "TEXADA_LOCAL_MODE" in os.environ:
        return os.environ["TEXADA_LOCAL_MODE"] == "1"
    return bool(LOCAL_MODE)


def _effective_port(scheme: str, port: int | None) -> int:
    if port is not None:
        return port
    return 443 if scheme == "https" else 80


def _tectonic_command():
    """编译器命令;每次读取环境,使会话内安装的 Tectonic 立即生效。"""
    return os.path.expanduser(os.environ.get("TECTONIC", "tectonic"))


def _subprocess_window_kwargs() -> dict:
    """Suppress transient console flashes when running CLI tools from a windowed Windows bundle."""
    if os.name == "nt" or sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return {"creationflags": flags} if flags else {}
    return {}

@asynccontextmanager
async def lifespan(_app):
    global _DEFAULT_MANAGED_MODELS, managed_models
    if managed_models is _DEFAULT_MANAGED_MODELS and _DEFAULT_MANAGED_MODELS.closed.is_set():
        _DEFAULT_MANAGED_MODELS = managed_models = ManagedModels(_DEFAULT_STUDIO_STATE)
    try:
        yield
    finally:
        managed_models.close()
        if _DEFAULT_MANAGED_MODELS is not managed_models:
            _DEFAULT_MANAGED_MODELS.close()
        with _scoped_models_lock:
            scoped = list(_scoped_managed_models.values())
            _scoped_managed_models.clear()
        for manager in scoped:
            manager.close()


app = FastAPI(title="TeXada Studio Local", lifespan=lifespan)
_run = {"proc": None, "log": [], "done": True, "code": None, "started": None}
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@app.middleware("http")
async def _loopback_csrf_guard(request: Request, call_next):
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        sec_fetch_site = (request.headers.get("sec-fetch-site") or "").strip().lower()
        if sec_fetch_site == "cross-site":
            return JSONResponse({"detail": "cross-site request blocked"}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None:
            try:
                parts = urlsplit(origin.strip())
                valid_syntax = (parts.scheme in {"http", "https"}
                                and bool(parts.hostname)
                                and parts.username is None and parts.password is None
                                and parts.path in {"", "/"} and not parts.query and not parts.fragment
                                and (parts.port is None or 1 <= parts.port <= 65535))
            except ValueError:
                valid_syntax = False
            allowed_origin = False
            if valid_syntax:
                if parts.hostname in _LOOPBACK_HOSTS:
                    allowed_origin = True
                elif not _is_local_mode():
                    req_scheme = (request.url.scheme or "").lower()
                    req_host = (request.url.hostname or "").lower()
                    allowed_origin = (
                        parts.scheme == req_scheme
                        and parts.hostname == req_host
                        and _effective_port(parts.scheme, parts.port) == _effective_port(req_scheme, request.url.port)
                    )
            if not allowed_origin:
                return JSONResponse({"detail": "cross-origin request blocked"}, status_code=403)
    return await call_next(request)


def _guard(token: str):
    if not hmac.compare_digest(token.encode(), TOKEN.encode()):
        raise HTTPException(status_code=401, detail="bad token")


MONACO_PREFIX = "/static/monaco/0.52.2"
MONACO_COOKIE = "texada_monaco"
MONACO_SESSION_TTL = 12 * 60 * 60


def _monaco_signature(expires: int) -> str:
    payload = f"{MONACO_PREFIX}:{expires}".encode()
    return hmac.new(TOKEN.encode(), payload, hashlib.sha256).hexdigest()


def _valid_monaco_cookie(value: str) -> bool:
    if len(value) > 96:
        return False
    try:
        timestamp, signature = value.split(".", 1)
        expires = int(timestamp)
    except (ValueError, TypeError):
        return False
    if len(signature) != 64 or any(c not in "0123456789abcdef" for c in signature):
        return False
    now = int(time.time())
    return (now < expires <= now + MONACO_SESSION_TTL
            and hmac.compare_digest(signature, _monaco_signature(expires)))


class MonacoStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        if not _valid_monaco_cookie(Request(scope).cookies.get(MONACO_COOKIE, "")):
            return PlainTextResponse("Unauthorized", status_code=401,
                                     headers={"Cache-Control": "no-store"})
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "private, max-age=3600"
        response.headers["Vary"] = "Cookie"
        return response


app.mount(MONACO_PREFIX, MonacoStaticFiles(
    directory=os.path.join(os.path.dirname(__file__), "static", "monaco", "0.52.2")
), name="monaco")

# Public assets contain only application code and branding, never user documents.
for _asset_name in ("brand", "editor"):
    app.mount(f"/static/{_asset_name}", StaticFiles(
        directory=os.path.join(os.path.dirname(__file__), "static", _asset_name)
    ), name=_asset_name)


def _run_pipeline(fresh: bool):
    _run.update(log=[], done=False, code=None, started=time.time())
    if fresh and os.path.exists(STATE):
        shutil.rmtree(STATE)
    command = [sys.executable, "-m", "docforensics", "run", "samples", "--state", STATE,
               "--vlm", VLM_BASE_URL, "--vlm-model", REPAIR_MODEL]
    env = {**os.environ, "PYTHONPATH": os.path.join(REPO, "harness")}
    try:
        p = subprocess.Popen(command, cwd=REPO, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    except OSError:
        _run.update(done=True, code=1)
        raise
    _run["proc"] = p

    def reader():
        for line in p.stdout:
            _run["log"].append(line.rstrip())
            _run["log"] = _run["log"][-400:]
        p.wait()
        _run["done"] = True
        _run["code"] = p.returncode

    threading.Thread(target=reader, daemon=True).start()


def _events():
    path = os.path.join(STATE, "state.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


RENDER = os.path.join(STATE, "render")


def _compile_latex(latex: str, node_id: str, tag: str):
    """公式片段 → standalone PDF → PNG。成功返回 PNG 路径，编译失败返回 None。"""
    os.makedirs(RENDER, exist_ok=True)
    h = hashlib.sha1((node_id + tag + latex).encode()).hexdigest()[:12]
    png = os.path.join(RENDER, f"{node_id}-{tag}-{h}.png")
    if os.path.exists(png):
        return png
    d = tempfile.mkdtemp(prefix=f"tmp-{h}-", dir=RENDER)
    try:
        tex = ("\\documentclass[border=6pt]{standalone}\n\\usepackage{amsmath,amssymb}\n"
               "\\begin{document}\n$\\displaystyle " + latex + "$\n\\end{document}\n")
        texf = os.path.join(d, "f.tex")
        with open(texf, "w", encoding="utf-8") as f:
            f.write(tex)
        try:
            r = subprocess.run([_tectonic_command(), "--untrusted", "--only-cached", "-o", d, texf],
                               capture_output=True, text=True, timeout=120, **_subprocess_window_kwargs())
        except (OSError, subprocess.SubprocessError):
            return None
        pdf = os.path.join(d, "f.pdf")
        if r.returncode != 0 or not os.path.exists(pdf):
            return None
        try:
            subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile", pdf, png[:-4]],
                           check=True, capture_output=True, timeout=30, **_subprocess_window_kwargs())
        except (OSError, subprocess.SubprocessError):
            return None
        return png if os.path.exists(png) else None
    finally:
        shutil.rmtree(d, ignore_errors=True)


@app.get("/api/render/{node_id}")
def render(node_id: str, token: str = Query("")):
    _guard(token)
    ev = None
    for e in _events():
        if e.get("node_id") == node_id and e.get("status") == "OK":
            ev = e
    if not ev:
        raise HTTPException(status_code=404, detail="node not repaired")
    orig = ev.get("original")
    rep = ev.get("latex")
    orig_png = _compile_latex(orig, node_id, "orig") if orig else None
    rep_png = _compile_latex(rep, node_id, "rep") if rep else None
    return {
        "orig_ok": orig_png is not None,
        "rep_ok": rep_png is not None,
        "original": orig, "latex": rep,
        "img": f"/api/render-img/{os.path.basename(rep_png)}" if rep_png else None,
    }


@app.get("/api/render-img/{name}")
def render_img(name: str, token: str = Query("")):
    _guard(token)
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="bad name")
    path = os.path.join(RENDER, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="no render")
    return FileResponse(path)


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.get("/api/nodeinfo")
def nodeinfo(token: str = Query("")):
    _guard(token)
    managed = _managed_models().connection()
    runtime_platform = " ".join(part for part in (
        platform.system(), platform.release(), platform.machine()) if part)
    configured_model = managed["model"] if managed else REPAIR_MODEL
    if not managed and _is_local_mode():
        try:
            configured_model = _local_runtime().get_config()["model"]
        except LocalRuntimeError:
            pass
    return {"host": platform.node(), "platform": runtime_platform,
            "python": platform.python_version(), "configured_model": configured_model,
            "model": configured_model,
            # 按任务模型契约(#23):状态接口暴露修复线与 OCR 线的实际模型。
            "repair_model": managed["model"] if managed else REPAIR_MODEL,
            "ocr_model": managed["model"] if managed else OCR_MODEL,
            # Empty legacy fields keep older clients compatible without probing hardware.
            "gpu": "", "mem": "", "models": ""}


@app.post("/api/run")
def run(token: str = Query(""), resume: bool = False):
    _guard(token)
    if not _run["done"]:
        raise HTTPException(status_code=409, detail="pipeline already running")
    _run_pipeline(fresh=not resume)
    return {"ok": True, "fresh": not resume}


@app.get("/api/status")
def status(token: str = Query("")):
    _guard(token)
    events = _events()
    terminal = {}
    for e in events:
        if e.get("node_id") and e.get("status") in ("OK", "NEEDS_HUMAN"):
            terminal[e["node_id"]] = e
    docs = {}
    for e in events:
        doc = e.get("doc")
        if not doc:
            continue
        d = docs.setdefault(doc, {"nodes": {}})
        if e.get("node_id"):
            d["nodes"][e["node_id"]] = e
    return JSONResponse({
        "running": not _run["done"],
        "exit_code": _run["code"],
        "elapsed": round(time.time() - _run["started"], 1) if _run["started"] else 0,
        "log_tail": _run["log"][-12:],
        "docs": docs,
        "report_ready": os.path.exists(os.path.join(STATE, "report.md")),
    })


@app.get("/api/report", response_class=PlainTextResponse)
def report(token: str = Query("")):
    _guard(token)
    path = os.path.join(STATE, "report.md")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="report not ready")
    with open(path) as f:
        return f.read()


@app.get("/api/crops/{name}")
def crops(name: str, token: str = Query("")):
    _guard(token)
    if "/" in name or ".." in name:
        raise HTTPException(status_code=400, detail="bad name")
    path = os.path.join(STATE, "crops", name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="no crop")
    return FileResponse(path)


# ============ Studio：VS Code 风格编辑器 + Skill 一键修复 ============

import re as _re
import sys as _sys
import uuid as _uuid
from decimal import Decimal, localcontext

_sys.path.insert(0, os.path.join(REPO, "harness"))
from docforensics import anchor_guard  # noqa: E402
from docforensics.vlm import OpenAICompatibleProvider  # noqa: E402
from docforensics.planner import ConstrainedPlanner  # noqa: E402
from docforensics.skill_selection import load_catalog  # noqa: E402
from docforensics.handoff import FormulaHandoffClient, HandoffError, CHECKPOINT  # noqa: E402
from docforensics.tex_context import analyze_math, check_math_grids, extract_math, mask_opaque  # noqa: E402
from docforensics.formula_repair import (  # noqa: E402
    assess_candidate,
    can_attempt_structural_repair,
    deterministic_candidate,
    repair_blocker,
)
from docforensics.table_repair import assess_table_candidate  # noqa: E402
from docforensics.tex_cleanup import (  # noqa: E402
    assess_cleanup_candidate,
    cleanup_edits,
    deterministic_cleanup_candidate,
    inspect_tex_cleanup,
)
from docforensics.__main__ import repair_model_default  # noqa: E402

# 按任务模型契约(issue #23):修复线 REPAIR_MODEL > VLM_MODEL > 内置默认,与 harness CLI 同源。
REPAIR_MODEL = repair_model_default()
# OCR 线契约同 skills/doc-ocr-extract:OCR_MODEL > minicpm-ocr:latest。
OCR_MODEL = os.environ.get("OCR_MODEL", "minicpm-ocr:latest")

SAMPLE_DOCS = os.path.join(REPO, "samples", "docs")
STUDIO_STATE = os.environ.get("TEXADA_STUDIO_STATE_DIR", os.path.join(REPO, "state", "studio"))
_DEFAULT_STUDIO_STATE = Path(STUDIO_STATE)
_DEFAULT_MANAGED_MODELS = managed_models = ManagedModels(STUDIO_STATE)
_scoped_managed_models: dict[Path, ManagedModels] = {}
_scoped_models_lock = threading.Lock()
STUDIO_DOCS = os.path.join(STUDIO_STATE, "documents")
VERIFY = os.path.join(REPO, "skills", "doc-formula-verify", "scripts", "verify.py")
AUDIT_TABLE = os.path.join(REPO, "skills", "doc-table-audit", "scripts", "audit_table.py")
SKILL_MODE = os.environ.get("SKILL_MODE", "on")


def _managed_models() -> ManagedModels:
    if managed_models is not _DEFAULT_MANAGED_MODELS:
        return managed_models
    state_path = Path(STUDIO_STATE)
    if state_path == _DEFAULT_STUDIO_STATE:
        return _DEFAULT_MANAGED_MODELS
    with _scoped_models_lock:
        manager = _scoped_managed_models.get(state_path)
        if manager is None or manager.closed.is_set():
            manager = ManagedModels(state_path)
            _scoped_managed_models[state_path] = manager
        return manager


def _new_provider(*, skill_selection=False):
    # Selection must see metadata first; do not eagerly load the fixed formula body.
    if _is_local_mode():
        runtime = _local_runtime()
        config = runtime.get_config()
        active = _managed_models().connection()
        managed_1b = (active is not None and active["model"] == config["model"] == PROFILES["1b"].model
                      and active["base_url"] == config["base_url"])
        return make_local_provider(config["base_url"], config["model"],
                                   skill_mode="off" if skill_selection else SKILL_MODE,
                                   constrain_planner=managed_1b)
    return OpenAICompatibleProvider(VLM_BASE_URL, REPAIR_MODEL, skill_mode="off" if skill_selection else SKILL_MODE)


def _local_runtime(*, managed=True):
    return LocalRuntime(STUDIO_STATE, base_url=os.environ.get("VLM_BASE_URL") or os.environ.get("VLM_BASE"),
                        model=REPAIR_MODEL, active_model=_managed_models().connection() if managed else None)


try:
    PROVIDER = _new_provider()
except LocalRuntimeError:
    # A corrupt saved connection must not prevent opening Settings to repair it.
    PROVIDER = None
_TABLE_LABELS = ("合计", "总计", "total")
_TABLE_NUMBER = r"[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)"
_jobs = {}
_compile_lock = threading.Lock()
_job_lock = threading.RLock()


def _documents():
    return DocumentStore(STUDIO_DOCS, SAMPLE_DOCS)


def _document_call(operation):
    try:
        return operation()
    except DocumentError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from None


def _document_body(body):
    body = body or {}
    name = _document_call(lambda: document_name(body.get("name")))
    content = _document_call(lambda: document_text(body.get("content")))
    return name, content


def _artifact_directory(name, tag):
    norm_name = _document_call(lambda: document_name(name))
    if not isinstance(tag, str) or not _re.fullmatch(r"[\w-]{1,80}", tag):
        raise HTTPException(status_code=400, detail="bad artifact tag")
    return Path(STUDIO_STATE) / "builds" / norm_name.removesuffix(".tex") / tag


def _subprocess_text(value) -> str:
    """编译器输出按 UTF-8 解码；非法字节替换，避免整次编译变成未处理异常。"""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _normalize_compile_path(value: str) -> str:
    text = value.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    if os.name == "nt" or _re.match(r"^[A-Za-z]:/", text):
        text = text.lower()
    return text


def _source_compile_error(output: str, source: Path, line_count: int):
    """Return a location only when Tectonic names the compiled source file."""
    raw_source = _normalize_compile_path(str(source))
    basename = raw_source.rsplit("/", 1)[-1]
    source_paths = {
        _normalize_compile_path(source.name),
        basename,
        raw_source,
        _normalize_compile_path(source.as_posix()),
    }
    for match in _re.finditer(r"^error:[ \t]*((?:[A-Za-z]:)?[^:\r\n]+):(\d{1,8}):[ \t]*([^\r\n]+)", output, _re.M):
        filename, line, message = match.groups()
        if _normalize_compile_path(filename) not in source_paths:
            continue
        number = int(line)
        if 1 <= number <= line_count:
            return {"line": number, "message": message.strip()[:240]}
    return None


def _append_compiler_log(log, outcome) -> None:
    """失败时把编译器原文写进任务日志，成功时不重复成功输出。"""
    if outcome.get("ok"):
        return
    for line in (outcome.get("log") or "").splitlines():
        text = line.strip()
        if text:
            log.append(text)


def _studio_compile(content: str, name: str, tag: str):
    """Compile in an isolated build directory; page images are generated lazily."""
    document_text(content)
    directory = _artifact_directory(name, tag)
    directory.mkdir(parents=True, exist_ok=True)
    digest = text_hash(content)
    result = {"ok": False, "compile_ok": False, "preview_ok": False,
              "png": None, "pages": [], "pdf": None, "tag": tag,
              "content_sha256": digest, "log": ""}
    with _compile_lock:
        texf = directory / "main.tex"
        texf.write_text(content, encoding="utf-8")
        # A local Studio never downloads TeX packages during an edit/preview.
        command = [_tectonic_command(), "--untrusted", "--only-cached", "--keep-logs",
                   "-o", str(directory), str(texf)]
        try:
            run = subprocess.run(command, cwd=directory, capture_output=True, timeout=120,
                                 **_subprocess_window_kwargs())
        except subprocess.TimeoutExpired as exc:
            log = "编译超过 120 秒，已停止。请检查文档或本机 TeX 缓存。"
            for stream in (exc.stdout, exc.stderr):
                if stream:
                    log += "\n" + _subprocess_text(stream)[-1200:]
            return {**result, "log": log}
        except OSError:
            return {**result, "log": "Tectonic not found; install it or set TECTONIC（本机缺少编译器）。"}
        stderr_text = _subprocess_text(run.stderr)
        stdout_text = _subprocess_text(run.stdout)
        output = "\n".join(part for part in (stderr_text, stdout_text) if part.strip()) or stderr_text or stdout_text
        log = output[-2400:]
        if run.returncode != 0 or not (directory / "main.pdf").is_file():
            diagnostic = _source_compile_error(output, texf, content.count("\n") + 1)
            return {**result, "log": log or "未生成 PDF；请检查本机 TeX 缓存和文档语法。",
                    "diagnostic": diagnostic}
        base = f"/api/studio/preview/{quote(name)}/{tag}"
        result.update(compile_ok=True, pdf=f"/api/studio/pdf/{quote(name)}/{tag}", log=log)
        page_count = 1
        try:
            info = subprocess.run(["pdfinfo", str(directory / "main.pdf")],
                                  capture_output=True, timeout=10, **_subprocess_window_kwargs())
            match = _re.search(r"^Pages:\s+(\d+)", _subprocess_text(info.stdout), _re.MULTILINE)
            if match:
                page_count = int(match.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
        result["page_count"] = page_count
        result["pages"] = [f"{base}?page={page}" for page in range(1, min(page_count, 60) + 1)]
        try:
            _render_preview_page(directory, 1)
        except HTTPException:
            result.update(log="PDF 已生成；预览转换失败，请检查本机 pdftoppm。", pages=[])
        else:
            result.update(ok=True, preview_ok=True, png=result["pages"][0])
        (directory / "manifest.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        return result


def _render_preview_page(directory, page):
    png = directory / f"preview-{page}.png"
    if not png.is_file():
        try:
            subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-png", "-r", "100",
                            "-singlefile", str(directory / "main.pdf"), str(png.with_suffix(""))],
                           check=True, capture_output=True, timeout=45, **_subprocess_window_kwargs())
        except (OSError, subprocess.SubprocessError):
            raise HTTPException(status_code=503, detail="PDF 已生成，但本机页面预览转换失败。") from None
    if not png.is_file():
        raise HTTPException(status_code=404, detail="页面不存在。")
    return png


@app.post("/api/studio/preview")
def studio_preview_live(token: str = Query(""), body: dict = None):
    """编译当前编辑器内容并返回整页渲染（预览窗口用）。"""
    _guard(token)
    name, content = _document_body(body)
    # Identical source can produce different output (for example, \\today).
    # Each build owns immutable PDF/page URLs, including lazily rendered pages.
    tag = "live-" + _uuid.uuid4().hex
    res = _studio_compile(content, name, tag)
    return res


@app.post("/api/studio/upload")
def studio_upload(token: str = Query(""), body: dict = None):
    """导入 .tex 文档到被 Git 忽略的 state/studio/documents。"""
    _guard(token)
    name, content = _document_body(body)
    return _document_call(lambda: _documents().save(name, content, (body or {}).get("expected_sha256"), upload=True))


@app.get("/api/studio/pdf/{name}/{tag}")
def studio_pdf(name: str, tag: str, token: str = Query("")):
    _guard(token)
    p = str(_artifact_directory(name, tag) / "main.pdf")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="no pdf")
    return FileResponse(p, media_type="application/pdf", filename=name.removesuffix(".tex") + f"-{tag}.pdf")


@app.get("/api/studio/preview/{name}/{tag}")
def studio_preview(name: str, tag: str, token: str = Query(""), page: int = Query(1, ge=1, le=60)):
    _guard(token)
    directory = _artifact_directory(name, tag)
    if not (directory / "main.pdf").is_file():
        raise HTTPException(status_code=404, detail="no preview")
    manifest = directory / "manifest.json"
    if manifest.is_file():
        count = json.loads(manifest.read_text(encoding="utf-8")).get("page_count", 1)
        if page > count:
            raise HTTPException(status_code=404, detail="no page")
    return FileResponse(_render_preview_page(directory, page), headers={"Cache-Control": "private, max-age=3600"})


def _verify_formula(latex: str):
    """Verifier failures are environment problems, never a successful check."""
    try:
        result = subprocess.run([_sys.executable, VERIFY, latex],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=30, **_subprocess_window_kwargs())
        data = json.loads(result.stdout.strip().splitlines()[-1])
        expected_codes = {"OK": 0, "RETRY": 0, "NEEDS_HUMAN": 1, "NEEDS_ENV": 2}
        status = data.get("status")
        if not isinstance(status, str) or result.returncode != expected_codes.get(status):
            raise ValueError("verifier did not complete")
        return data
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, AttributeError):
        return {"status": "NEEDS_ENV", "reason": "公式检查器不可用，请检查 SymPy / antlr 依赖与服务日志"}


def _math_boundary_problems(diagnostics):
    return [{**diagnostic, "id": f"math-boundary-{index}", "type": "formula",
             "status": "NEEDS_HUMAN", "latex": "",
             "reason": "数学边界未闭合或无法可靠抽取，请先检查原文：" + diagnostic.get("reason", diagnostic.get("code", "unknown"))}
            for index, diagnostic in enumerate(diagnostics)]


def _formula_problems(content: str, emit=None, *, deterministic_only=False, skip_ordinals=()):
    skipped = set(skip_ordinals)
    problems = []
    parsed = analyze_math(content)
    for ordinal, node in enumerate(parsed["nodes"], 1):
        if ordinal in skipped:
            continue
        if deterministic_only and (not node["checkable"] or deterministic_candidate(node["latex"]) is None):
            continue
        if node["checkable"]:
            vj = _verify_formula(node["latex"])
        else:
            grid = check_math_grids(node["latex"]) if node["reason"] == "structured_math" else None
            vj = grid or {"status": "NEEDS_HUMAN", "reason": "复杂数学结构保留原文供人工核对：" + node["reason"]}
        if emit:
            emit("CHECK", node_id=node["id"], line=node["line"], original=node["latex"],
                 checker="doc-formula-verify", check=vj)
        if vj.get("status") != "OK":
            blocker = repair_blocker(node["latex"]) if vj.get("status") == "RETRY" else None
            hard_blocked = bool(blocker and not can_attempt_structural_repair(node["latex"]))
            problems.append({**node, "type": "formula", "status": "NEEDS_HUMAN" if hard_blocked else vj["status"],
                             "reason": ("无法确定语法修复，保留原文供人工核对：" + blocker) if hard_blocked else vj.get("reason", ""),
                             **({"repair_blocker": blocker} if hard_blocked else {})})
    problems.extend(_math_boundary_problems(parsed["diagnostics"]))
    return problems


def _is_escaped_tex(text: str, index: int) -> bool:
    slashes = 0
    while index > 0 and text[index - 1] == "\\":
        slashes += 1
        index -= 1
    return slashes % 2 == 1


def _table_row_spans(vis_line: str):
    row_end = len(vis_line.rstrip())
    has_row_break = (row_end >= 2 and vis_line[row_end - 2:row_end] == r"\\"
                     and not _is_escaped_tex(vis_line, row_end - 2))
    body_end = row_end - 2 if has_row_break else row_end
    spans = []
    start = 0
    for idx in range(body_end):
        if vis_line[idx] == "&" and not _is_escaped_tex(vis_line, idx):
            spans.append((start, idx))
            start = idx + 1
    spans.append((start, body_end))
    return spans, has_row_break, body_end


def _table_number_match(cell: str):
    """Match the entire plain numeric cell, retaining its source replacement span."""
    return _re.fullmatch(rf"\s*(?P<number>{_TABLE_NUMBER})\s*(?:\\\\)?\s*", cell)


def _resolve_table_edit(raw_lines, vis_lines, line_offsets, problem):
    line_idx = problem["line"] - 1
    cell_idx = problem["col"]
    right = problem.get("right")
    if (not isinstance(right, str) or not _re.fullmatch(_TABLE_NUMBER, right)
            or not (0 <= line_idx < len(raw_lines))):
        return None
    raw_line = raw_lines[line_idx].removesuffix("\r")
    vis_line = vis_lines[line_idx].removesuffix("\r")
    spans, _, _ = _table_row_spans(vis_line)
    if not (0 <= cell_idx < len(spans)):
        return None
    cell_start, cell_end = spans[cell_idx]
    raw_cell = raw_line[cell_start:cell_end]
    vis_cell = vis_line[cell_start:cell_end]
    if raw_cell != vis_cell:
        return None
    match = _table_number_match(raw_cell)
    if not match:
        return None
    num_start, num_end = match.span("number")
    return {
        "line": problem["line"],
        "before": match.group("number"),
        "after": right,
        "skill": "doc-table-audit",
        "start": line_offsets[line_idx] + cell_start + num_start,
        "end": line_offsets[line_idx] + cell_start + num_end,
    }


def _is_repairable_incomplete_total(rows, width, shape_reason):
    """True when header and data rows are clean rectangular scalars and only the final total row is short or blank."""
    if shape_reason or width is None or width < 2 or len(rows) < 3:
        return False
    if any(len(c) != width for _, c in rows[:-1]):
        return False
    header_cells = rows[0][1]
    total_cells = rows[-1][1]
    if not header_cells or not total_cells or len(total_cells) > width:
        return False
    if total_cells[0].strip().lower() not in _TABLE_LABELS:
        return False
    if any(_table_number_match(c) for c in header_cells[1:]):
        return False
    if any(any(k in c[0].lower() for k in _TABLE_LABELS) for _, c in rows[:-1]):
        return False
    for _, data_cells in rows[1:-1]:
        if any(_table_number_match(cell) is None for cell in data_cells[1:]):
            return False
    if any(cell != "" and _table_number_match(cell) is None for cell in total_cells[1:]):
        return False
    return len(total_cells) < width or any(cell == "" for cell in total_cells[1:])


def _verify_table_grid(rows, expected=None, *, node_id="t-studio"):
    rec = {"id": node_id, "rows": rows, "expected": expected or {}}
    try:
        proc = subprocess.run([_sys.executable, AUDIT_TABLE], input=json.dumps(rec),
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=30, **_subprocess_window_kwargs())
        result = json.loads(proc.stdout.strip().splitlines()[-1])
        status = result.get("status")
        if status not in ("OK", "RETRY", "NEEDS_HUMAN"):
            raise ValueError("invalid table audit status")
        allowed_codes = (0, 1) if status == "NEEDS_HUMAN" else (0,)
        if proc.returncode not in allowed_codes:
            raise ValueError("invalid table audit exit code")
        return result
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, AttributeError, TypeError):
        return {"status": "NEEDS_HUMAN", "reason": "checker_error"}


def _extract_repairable_tables(content: str):
    """Extract simple ``tabular`` grids that have an unresolved repairable final total row."""
    tables = []
    visible_lines = mask_opaque(content).split("\n")
    raw_lines = content.split("\n")
    line_offsets, offset = [], 0
    for raw_line in raw_lines:
        line_offsets.append(offset)
        offset += len(raw_line) + 1

    in_tab, rows, width, shape_reason = False, [], None, ""

    def finalize_table():
        if not rows or shape_reason or width is None or width < 2 or len(rows) < 3:
            return
        if any(len(c) != width for _, c in rows[:-1]):
            return
        header_cells = rows[0][1]
        total_i, total_cells = rows[-1]
        if not total_cells or len(total_cells) > width or total_cells[0].strip().lower() not in _TABLE_LABELS:
            return
        if any(_table_number_match(c) for c in header_cells[1:]):
            return
        if any(any(k in c[0].lower() for k in _TABLE_LABELS) for _, c in rows[:-1]):
            return
        for _, data_cells in rows[1:-1]:
            if any(_table_number_match(cell) is None for cell in data_cells[1:]):
                return
        if any(cell != "" and _table_number_match(cell) is None for cell in total_cells[1:]):
            return
        expected = {"n_rows": len(rows), "n_cols": width}
        grid = [cells for _, cells in rows]
        audit_check = _verify_table_grid(grid, expected, node_id=f"t-{total_i+1:03d}")
        if audit_check.get("status") != "RETRY":
            return
        raw_line = raw_lines[total_i].removesuffix("\r")
        vis_line = visible_lines[total_i].removesuffix("\r")
        _spans, has_row_break, body_end = _table_row_spans(vis_line)
        if not has_row_break or raw_line[:body_end] != vis_line[:body_end]:
            return
        body_prefix = raw_line[:body_end]
        lead_len = len(body_prefix) - len(body_prefix.lstrip(" \t"))
        if not body_prefix.strip(" \t"):
            return
        start = line_offsets[total_i] + lead_len
        end = line_offsets[total_i] + body_end
        tables.append({
            "id": f"t-{total_i+1:03d}",
            "line": total_i + 1,
            "n_cols": width,
            "rows": grid,
            "expected": expected,
            "start": start,
            "end": end,
            "before": content[start:end],
            "trailing_space": " " if body_prefix.endswith((" ", "\t")) else "",
            "check": audit_check,
        })

    for i, raw_full in enumerate(raw_lines):
        vis_line = visible_lines[i].removesuffix("\r")
        vis_stripped = vis_line.strip()
        if not vis_stripped:
            continue
        if r"\begin{tabular}" in vis_line:
            if in_tab:
                shape_reason = "nested"
                continue
            in_tab, rows, shape_reason = True, [], ""
            spec = _re.fullmatch(r"\\begin\{tabular\}\s*\{([lcr|\s]+)\}", vis_stripped)
            width = sum(c in "lcr" for c in spec.group(1)) if spec else None
            continue
        if not in_tab:
            continue
        if r"\end{tabular}" in vis_line:
            if vis_stripped != r"\end{tabular}":
                shape_reason = "bad_end"
            finalize_table()
            rows, in_tab = [], False
            continue
        if vis_stripped in (r"\hline", r"\toprule", r"\midrule", r"\bottomrule"):
            continue
        spans, has_row_break, body_end = _table_row_spans(vis_line)
        if not has_row_break or r"\\" in vis_line[:body_end]:
            shape_reason = "bad_row"
        raw_line = raw_full.removesuffix("\r")
        cells = []
        for c_start, c_end in spans:
            raw_cell = raw_line[c_start:c_end]
            vis_cell = vis_line[c_start:c_end]
            cells.append(vis_cell.strip() if raw_cell == vis_cell else raw_cell.strip())
        rows.append((i, cells))
    return tables


def _table_problems(content: str):
    """Audit only rectangular, one-row-per-line tables with a header and final total.

    TeX macros, accounting notation, percentages and unit-bearing values need a
    human. Taking the first digit sequence from those cells changes their meaning.
    """
    problems, rows, in_tab, width, shape_reason = [], [], False, None, ""

    def audit_rows():
        if not rows:
            return
        total_i, total_cells = rows[-1]
        if _is_repairable_incomplete_total(rows, width, shape_reason):
            if len(total_cells) < width:
                problems.append({
                    "id": f"t-{total_i+1:03d}-shape",
                    "type": "table_total",
                    "line": total_i + 1,
                    "col": len(total_cells),
                    "status": "RETRY",
                    "reason": "合计行缺少数值单元格，可尝试模型补全并经表格检查器核验",
                })
                return
            for j in range(1, width):
                if total_cells[j] == "":
                    problems.append({
                        "id": f"t-{total_i+1:03d}-{j}",
                        "type": "table_total",
                        "line": total_i + 1,
                        "col": j,
                        "wrong": "",
                        "status": "RETRY",
                        "reason": f"合计列 {j+1} 为空，可尝试模型补全并经表格检查器核验",
                    })
                    continue
                cells = [c[j] for _, c in rows[1:]]
                matches = [_table_number_match(c) for c in cells]
                with localcontext() as ctx:
                    ctx.prec = max(28, sum(len(c) for c in cells) + 4)
                    values = [Decimal(m.group("number").replace(",", "")) for m in matches]
                    got, want = sum(values[:-1], Decimal(0)), values[-1]
                    if got != want:
                        right = format(got, "f")
                        if "." in right:
                            right = right.rstrip("0").rstrip(".")
                        problems.append({
                            "id": f"t-{total_i+1:03d}-{j}",
                            "type": "table_total",
                            "line": total_i + 1,
                            "col": j,
                            "wrong": total_cells[j],
                            "right": right,
                            "status": "RETRY",
                            "reason": f"合计列 {j+1}：标注 {want}，数据行之和 {got}",
                        })
            return
        base = {"id": f"t-{total_i+1:03d}-shape", "type": "table_total",
                "line": total_i + 1, "col": 0, "status": "NEEDS_HUMAN"}
        reason = shape_reason
        if width is None or width < 2 or any(len(c) != width for _, c in rows):
            reason = reason or "表格列数不一致或列格式不受支持，需人工核对"
        if reason:
            problems.append({**base, "reason": reason})
            return
        label = total_cells[0].lower()
        if not any(k in label for k in _TABLE_LABELS):
            return  # No supported total row to audit.
        if (label not in _TABLE_LABELS or len(rows) < 3
                or any(_table_number_match(c) for c in rows[0][1][1:])
                or any(any(k in c[0].lower() for k in _TABLE_LABELS) for _, c in rows[:-1])):
            problems.append({**base, "reason": "需要明确的表头、数据行及唯一的末行合计，保留原文供人工核对"})
            return
        for j in range(1, width):
            cells = [c[j] for _, c in rows[1:]]
            matches = [_table_number_match(c) for c in cells]
            item = {"id": f"t-{total_i+1:03d}-{j}", "type": "table_total",
                    "line": total_i + 1, "col": j, "wrong": total_cells[j]}
            if any(m is None for m in matches):
                problems.append({**item, "status": "NEEDS_HUMAN",
                                 "reason": f"合计列 {j+1} 含非纯数字或不支持的格式（如单位、百分比、括号或宏），需人工核对"})
                continue
            # Decimal avoids float rounding, including large integers and small fractions.
            with localcontext() as ctx:
                ctx.prec = max(28, sum(len(c) for c in cells) + 4)
                values = [Decimal(m.group("number").replace(",", "")) for m in matches]
                got, want = sum(values[:-1], Decimal(0)), values[-1]
                if got != want:
                    right = format(got, "f")
                    if "." in right:
                        right = right.rstrip("0").rstrip(".")
                    problems.append({**item, "right": right, "status": "RETRY",
                                     "reason": f"合计列 {j+1}：标注 {want}，数据行之和 {got}"})

    visible_lines = mask_opaque(content).split("\n")
    raw_lines = content.split("\n")
    for i, raw_full in enumerate(raw_lines):
        # Split strictly on "\n" so \f, \v, \u2028, \u2029 inside comments or
        # verbatim blocks never desynchronize line indices or character offsets.
        vis_line = visible_lines[i].removesuffix("\r")
        vis_stripped = vis_line.strip()
        if not vis_stripped:
            continue
        if r"\begin{tabular}" in vis_line:
            if in_tab:
                shape_reason = "嵌套表格不在自动合计检查范围，需人工核对"
                continue
            in_tab, rows, shape_reason = True, [], ""
            spec = _re.fullmatch(r"\\begin\{tabular\}\s*\{([lcr|\s]+)\}", vis_stripped)
            width = sum(c in "lcr" for c in spec.group(1)) if spec else None
            continue
        if not in_tab:
            continue
        if r"\end{tabular}" in vis_line:
            if vis_stripped != r"\end{tabular}":
                shape_reason = "表格结束标记必须独占一行，需人工核对"
            audit_rows()
            rows, in_tab = [], False
            continue
        if vis_stripped in (r"\hline", r"\toprule", r"\midrule", r"\bottomrule"):
            continue
        spans, has_row_break, body_end = _table_row_spans(vis_line)
        if not has_row_break or r"\\" in vis_line[:body_end]:
            shape_reason = "仅支持每行一条且以双反斜杠结束的简单表格行，需人工核对"
        raw_line = raw_full.removesuffix("\r")
        cells = []
        for c_start, c_end in spans:
            raw_cell = raw_line[c_start:c_end]
            vis_cell = vis_line[c_start:c_end]
            cells.append(vis_cell.strip() if raw_cell == vis_cell else raw_cell.strip())
        rows.append((i, cells))
    if in_tab:
        shape_reason = "表格缺少结束标记，需人工核对"
        audit_rows()
    return problems


def _cleanup_problems(content: str):
    return inspect_tex_cleanup(content)["problems"]


def _analyze(content: str):
    fp = _formula_problems(content)
    tp = _table_problems(content)
    cp = _cleanup_problems(content)
    return fp + tp + cp


def _formula_repair_context(attempt, check, previous_candidate=None, rejection_reason=None):
    return {"attempt": attempt,
            "checker": {"status": check.get("status", "RETRY"), "reason": check.get("reason", "")},
            "previous_candidate": previous_candidate, "rejection_reason": rejection_reason}


def _formula_rejection_feedback(outcome):
    reason, scope = outcome["reason"], outcome.get("scope", {})
    if "token_index" in scope:
        reason += (f"; token {scope['token_index']}: "
                   f"{str(scope.get('original_token'))[:96]!r} -> {str(scope.get('candidate_token'))[:96]!r}")
    return reason[:512]


def _check_formula_candidate(original, candidate, *, node_id, attempt, emit, remaining=None, allow_math_whitespace=False):
    """The same verifier and a source-preservation guard must both accept."""
    try:
        valid = (isinstance(candidate, str) and bool(candidate.strip()) and len(candidate) <= 32768
                 and not any((ord(c) < 32 or ord(c) == 127)
                             and not (allow_math_whitespace and c in "\n\r\t") for c in candidate)
                 and bool(candidate.encode("utf-8")))
    except UnicodeEncodeError:
        valid = False
    if not valid:
        check = {"status": "NEEDS_HUMAN", "reason": "invalid_candidate"}
        emit("CANDIDATE_CHECK", node_id=node_id, attempt=attempt, candidate=candidate,
             check=check, executed=False)
        return {"accepted": False, "check": check, "reason": "invalid_candidate"}
    check = _verify_formula(candidate)
    emit("CANDIDATE_CHECK", node_id=node_id, attempt=attempt, candidate=candidate, check=check)
    if check.get("status") == "NEEDS_ENV":
        return {"accepted": False, "check": check, "reason": "checker_unavailable"}
    if remaining is not None and remaining() <= 0:
        return {"accepted": False, "check": check, "reason": "planner_deadline_exhausted"}
    scope = assess_candidate(original, candidate)
    anchor = anchor_guard.anchor_drift(original, candidate)
    emit("CANDIDATE_SCOPE", node_id=node_id, attempt=attempt, candidate=candidate, scope=scope, anchor=anchor)
    if remaining is not None and remaining() <= 0:
        return {"accepted": False, "check": check, "reason": "planner_deadline_exhausted"}
    accepted = check.get("status") == "OK" and scope.get("allowed") is True and not anchor["drift"]
    reason = ("checker_accepted_not_user_adopted" if accepted else
              anchor["reason"] if anchor["drift"] else
              scope.get("reason", "mutation_scope_rejected") if scope.get("allowed") is not True else "checker_rejected")
    return {"accepted": accepted, "check": check, "scope": scope, "anchor": anchor, "reason": reason}


def _apply_fixes(content: str, log, *, provider=None, emit=None, use_model=True, skip_ordinals=()):
    provider = provider if provider is not None else PROVIDER
    if use_model and provider is None:
        provider = _new_provider()
    emit = emit or (lambda action, **fields: None)
    edits, replacements = [], []
    fp = (_formula_problems(content, emit) if use_model and not skip_ordinals
          else _formula_problems(content, emit, deterministic_only=not use_model, skip_ordinals=skip_ordinals))
    verifier_unavailable = False
    for p in fp:
        if verifier_unavailable or p["status"] == "NEEDS_ENV":
            verifier_unavailable = True
            log.append(f"[doc-formula-verify] {p['id']} 检查器不可用，保留原文并转人工")
            emit("REPAIR_SKIPPED", node_id=p["id"], reason="checker_unavailable")
            continue
        if p["status"] != "RETRY":
            log.append(f"[doc-formula-verify] {p['id']} 需要人工审阅，保留原文")
            emit("REPAIR_SKIPPED", node_id=p["id"], reason=p.get("repair_blocker") or "needs_human")
            continue
        latex = p["latex"]
        blocker = repair_blocker(latex)
        if blocker and not can_attempt_structural_repair(latex):
            log.append(f"[doc-formula-verify] {p['id']} 无法确定缺失内容，保留原文供人工核对：{blocker}")
            emit("REPAIR_SKIPPED", node_id=p["id"], reason=blocker)
            continue
        fixed, ok = None, False
        previous_candidate, rejection_reason = None, None
        feedback_check = {"status": p["status"], "reason": p.get("reason", "")}
        seen = set()
        deterministic = deterministic_candidate(latex)
        if deterministic is not None:
            seen.add(deterministic)
            emit("DETERMINISTIC_REPAIR", node_id=p["id"], original=latex,
                 candidate=deterministic, model_calls=0)
            outcome = _check_formula_candidate(latex, deterministic, node_id=p["id"],
                                               attempt=0, emit=emit, allow_math_whitespace=True)
            emit("CANDIDATE_ACCEPTED" if outcome["accepted"] else "CANDIDATE_REJECTED",
                 node_id=p["id"], attempt=0, candidate=deterministic,
                 reason=outcome["reason"], check=outcome["check"], provider="deterministic-formula", model_calls=0)
            if outcome["accepted"]:
                fixed, ok = deterministic, True
                log.append(f"[doc-formula-verify] {p['id']} 确定性语法修复 → 同一检查器回判 ✓ ：{fixed}")
            elif outcome["check"].get("status") == "NEEDS_ENV":
                verifier_unavailable = True
                log.append(f"[doc-formula-verify] {p['id']} 候选回判检查器不可用，停止尝试并保留原文")
            else:
                previous_candidate, rejection_reason = deterministic, _formula_rejection_feedback(outcome)
                feedback_check = outcome["check"]
        for attempt in (() if ok or verifier_unavailable or not use_model else (1, 2)):
            log.append(f"[doc-formula-verify] {p['id']} L{p['line']} RETRY → 模型文本修复（第 {attempt} 次）")
            context = _formula_repair_context(attempt, feedback_check, previous_candidate, rejection_reason)
            emit("PROVIDER_START", node_id=p["id"], attempt=attempt, original=latex, repair_context=context)
            cand = provider.repair_formula({"id": p["id"], "data": {"latex": latex, "repair_context": context}})
            provider_trace = getattr(provider, "last_trace", {})
            if not isinstance(provider_trace, dict):
                provider_trace = {"reason": "trace_unavailable", "model_calls": None}
            emit("PROVIDER_RESULT", node_id=p["id"], attempt=attempt,
                 candidate=cand, provider_trace=provider_trace)
            if not isinstance(cand, str) or not cand.strip():
                previous_candidate = None
                rejection_reason = provider_trace.get("reason") or "no_valid_candidate"
                log.append(f"[doc-formula-verify] {p['id']} 模型未返回有效候选：{rejection_reason}")
                emit("CANDIDATE_REJECTED", node_id=p["id"], attempt=attempt,
                     candidate=cand, reason=rejection_reason)
                continue
            if assess_candidate(latex, cand).get("method") == "unchanged":
                emit("CANDIDATE_REJECTED", node_id=p["id"], attempt=attempt,
                     candidate=cand, reason="model_abstained")
                log.append(f"[doc-formula-verify] {p['id']} 模型保持原文放弃修复，停止尝试并保留原文")
                break
            if cand in seen:
                emit("CANDIDATE_REJECTED", node_id=p["id"], attempt=attempt,
                     candidate=cand, reason="repeated_candidate")
                log.append(f"[doc-formula-verify] {p['id']} 重复候选，停止尝试并保留原文")
                break
            seen.add(cand)
            outcome = _check_formula_candidate(latex, cand, node_id=p["id"], attempt=attempt, emit=emit)
            emit("CANDIDATE_ACCEPTED" if outcome["accepted"] else "CANDIDATE_REJECTED",
                 node_id=p["id"], attempt=attempt, candidate=cand,
                 reason=outcome["reason"], check=outcome["check"])
            if outcome["check"].get("status") == "NEEDS_ENV":
                verifier_unavailable = True
                log.append(f"[doc-formula-verify] {p['id']} 候选回判检查器不可用，停止尝试并保留原文")
                break
            if outcome["accepted"]:
                fixed, ok = cand, True
                log.append(f"[doc-formula-verify] {p['id']} 修复 → 同一检查器与来源范围回判 ✓ ：{cand}")
                break
            previous_candidate, rejection_reason = cand, _formula_rejection_feedback(outcome)
            feedback_check = outcome["check"]
            log.append(f"[doc-formula-verify] {p['id']} 候选拒绝：{rejection_reason}")
        if ok and fixed != latex:
            start, end = p.get("body_start"), p.get("body_end")
            if isinstance(start, int) and isinstance(end, int) and content[start:end] == latex:
                replacements.append((start, end, fixed))
                edits.append({"line": p["line"], "before": latex, "after": fixed, "skill": "doc-formula-verify"})
                emit("CANDIDATE_EDIT", node_id=p["id"], line=p["line"], before=latex, after=fixed)
    for start, end, replacement in sorted(replacements, reverse=True):
        content = content[:start] + replacement + content[end:]

    content, table_edits = _apply_table_fixes(content, log, emit, provider=provider, use_model=use_model)
    content, cl_edits = _apply_cleanup_fixes(content, log, emit, provider=provider, use_model=use_model)
    return content, edits + table_edits + cl_edits


def _apply_table_fixes(content, log, emit, *, provider=None, use_model=False):
    edits = []
    tp = _table_problems(content)
    emit("TABLE_CHECK", problems=tp, model_calls=0)
    raw_lines = content.split("\n")
    vis_lines = mask_opaque(content).split("\n")
    orig_raw_lines = list(raw_lines)
    orig_vis_lines = list(vis_lines)
    line_offsets, offset = [], 0
    for raw_line in raw_lines:
        line_offsets.append(offset)
        offset += len(raw_line) + 1
    table_replacements = []
    for p in tp:
        if p["status"] != "RETRY" or not isinstance(p.get("right"), str):
            if not use_model or p["status"] != "RETRY":
                log.append(f"[doc-table-audit] {p['id']} {p['reason']} → 保留原文供人工审阅")
            continue
        resolved = _resolve_table_edit(raw_lines, vis_lines, line_offsets, p)
        if not resolved or resolved["before"] == resolved["after"]:
            continue
        log.append(f"[doc-table-audit] {p['id']} {p['reason']} → 重算为 {p['right']}")
        edits.append({k: resolved[k] for k in ("line", "before", "after", "skill")})
        table_replacements.append((resolved["start"], resolved["end"], resolved["after"]))
        emit("CANDIDATE_EDIT", node_id=p["id"], line=p["line"],
             before=resolved["before"], after=resolved["after"],
             provider="deterministic-table", model_calls=0)
    for start, end, replacement in sorted(table_replacements, reverse=True):
        content = content[:start] + replacement + content[end:]

    if use_model and provider is not None and callable(getattr(provider, "repair_table", None)):
        model_replacements = []
        for tbl in _extract_repairable_tables(content):
            previous_candidate, rejection_reason = None, None
            feedback_check = tbl["check"]
            seen = set()
            for attempt in (1, 2):
                context = {"attempt": attempt,
                           "checker": {"status": feedback_check.get("status", "RETRY"),
                                       "reason": feedback_check.get("reason", "")},
                           "previous_candidate": previous_candidate,
                           "rejection_reason": rejection_reason}
                emit("PROVIDER_START", node_id=tbl["id"], attempt=attempt,
                     original_rows=tbl["rows"], repair_context=context)
                cand_rows = provider.repair_table({
                    "id": tbl["id"],
                    "data": {"rows": tbl["rows"], "expected": tbl["expected"], "repair_context": context},
                })
                provider_trace = getattr(provider, "last_trace", {})
                if not isinstance(provider_trace, dict):
                    provider_trace = {"reason": "trace_unavailable", "model_calls": None}
                emit("PROVIDER_RESULT", node_id=tbl["id"], attempt=attempt,
                     candidate=cand_rows, provider_trace=provider_trace)
                if not isinstance(cand_rows, list) or not cand_rows:
                    previous_candidate = None
                    rejection_reason = provider_trace.get("reason") or "no_valid_candidate"
                    emit("CANDIDATE_REJECTED", node_id=tbl["id"], attempt=attempt,
                         candidate=cand_rows, reason=rejection_reason)
                    continue
                scope = assess_table_candidate(tbl["rows"], cand_rows, expected=tbl["expected"])
                if scope.get("reason") == "unchanged_candidate":
                    emit("CANDIDATE_REJECTED", node_id=tbl["id"], attempt=attempt,
                         candidate=cand_rows, reason="model_abstained")
                    break
                seen_key = json.dumps(cand_rows, ensure_ascii=False, separators=(",", ":"))
                if seen_key in seen:
                    emit("CANDIDATE_REJECTED", node_id=tbl["id"], attempt=attempt,
                         candidate=cand_rows, reason="repeated_candidate")
                    break
                seen.add(seen_key)
                audit_res = _verify_table_grid(cand_rows, tbl["expected"], node_id=tbl["id"])
                emit("CANDIDATE_CHECK", node_id=tbl["id"], attempt=attempt,
                     candidate=cand_rows, check=audit_res)
                emit("CANDIDATE_SCOPE", node_id=tbl["id"], attempt=attempt,
                     candidate=cand_rows, scope=scope)
                accepted = audit_res.get("status") == "OK" and scope.get("allowed") is True
                reason = ("table_verified" if accepted else
                          scope.get("reason", "table_scope_violation") if not scope.get("allowed")
                          else audit_res.get("reason", "checker_rejected"))
                emit("CANDIDATE_ACCEPTED" if accepted else "CANDIDATE_REJECTED",
                     node_id=tbl["id"], attempt=attempt, candidate=cand_rows,
                     reason=reason, check=audit_res)
                if accepted:
                    after_row = " & ".join(cand_rows[-1]) + tbl["trailing_space"]
                    if after_row != tbl["before"] and content[tbl["start"]:tbl["end"]] == tbl["before"]:
                        orig_line = orig_raw_lines[tbl["line"] - 1].removesuffix("\r")
                        orig_body_end = _table_row_spans(orig_vis_lines[tbl["line"] - 1].removesuffix("\r"))[2]
                        orig_prefix = orig_line[:orig_body_end]
                        orig_lead = len(orig_prefix) - len(orig_prefix.lstrip(" \t"))
                        orig_before = orig_line[orig_lead:orig_body_end]
                        edits = [e for e in edits if e["line"] != tbl["line"]]
                        model_replacements.append((tbl["start"], tbl["end"], after_row))
                        edits.append({"line": tbl["line"], "before": orig_before,
                                      "after": after_row, "skill": "doc-table-audit"})
                        emit("CANDIDATE_EDIT", node_id=tbl["id"], line=tbl["line"],
                             before=orig_before, after=after_row, skill="doc-table-audit")
                        log.append(f"[doc-table-audit] {tbl['id']} 模型补全合计行 → 范围与审计回判 ✓ ：{after_row}")
                    break
                previous_candidate, rejection_reason, feedback_check = cand_rows, reason, audit_res
        for start, end, replacement in sorted(model_replacements, reverse=True):
            content = content[:start] + replacement + content[end:]
    return content, edits


def _apply_cleanup_fixes(content, log, emit, *, provider=None, use_model=True):
    report = inspect_tex_cleanup(content)
    if not report["problems"]:
        return content, []
    emit("CLEANUP_CHECK", problems=report["problems"], model_calls=0)
    det = deterministic_cleanup_candidate(content)
    if det is not None:
        scope = assess_cleanup_candidate(content, det)
        if scope["allowed"]:
            c_edits = cleanup_edits(content, det)
            emit("DETERMINISTIC_REPAIR", node_id="cleanup-document",
                 candidate_edits=len(c_edits), model_calls=0)
            emit("CANDIDATE_ACCEPTED", node_id="cleanup-document", attempt=0,
                 reason=scope["reason"], check={"status": "OK"},
                 provider="deterministic-cleanup", model_calls=0)
            public_edits = [{k: e[k] for k in ("line", "before", "after", "skill")} for e in c_edits]
            for e in public_edits:
                emit("CANDIDATE_EDIT", node_id="cleanup-document", **e,
                     provider="deterministic-cleanup", model_calls=0)
            log.append(f"[latex-cleanup] 确定性清理 {len(public_edits)} 处零宽格式噪声")
            return det, public_edits
    if not use_model or provider is None or not callable(getattr(provider, "repair_cleanup", None)):
        return content, []
    previous_candidate, rejection_reason = None, None
    seen = set()
    for attempt in (1, 2):
        context = _formula_repair_context(attempt, {"status": "RETRY", "reason": report["problems"][0]["kind"]},
                                          previous_candidate, rejection_reason)
        emit("PROVIDER_START", node_id="cleanup-document", attempt=attempt, repair_context=context)
        cand = provider.repair_cleanup({"id": "cleanup-document",
                                        "data": {"content": content, "repair_context": context}})
        provider_trace = getattr(provider, "last_trace", {})
        if not isinstance(provider_trace, dict):
            provider_trace = {"reason": "trace_unavailable", "model_calls": None}
        emit("PROVIDER_RESULT", node_id="cleanup-document", attempt=attempt,
             candidate=cand, provider_trace=provider_trace)
        if not isinstance(cand, str) or not cand.strip():
            previous_candidate = None
            rejection_reason = provider_trace.get("reason") or "no_valid_candidate"
            emit("CANDIDATE_REJECTED", node_id="cleanup-document", attempt=attempt,
                 candidate=cand, reason=rejection_reason)
            continue
        if cand == content:
            emit("CANDIDATE_REJECTED", node_id="cleanup-document", attempt=attempt,
                 candidate=cand, reason="model_abstained")
            break
        if cand in seen:
            emit("CANDIDATE_REJECTED", node_id="cleanup-document", attempt=attempt,
                 candidate=cand, reason="repeated_candidate")
            break
        seen.add(cand)
        scope = assess_cleanup_candidate(content, cand)
        emit("CANDIDATE_SCOPE", node_id="cleanup-document", attempt=attempt, scope=scope)
        emit("CANDIDATE_ACCEPTED" if scope["allowed"] else "CANDIDATE_REJECTED",
             node_id="cleanup-document", attempt=attempt, reason=scope["reason"],
             check={"status": "OK" if scope["allowed"] else "RETRY"})
        if scope["allowed"]:
            c_edits = cleanup_edits(content, cand)
            public_edits = [{k: e[k] for k in ("line", "before", "after", "skill")} for e in c_edits]
            for e in public_edits:
                emit("CANDIDATE_EDIT", node_id="cleanup-document", **e)
            log.append(f"[latex-cleanup] 模型结构清洗修复 ✓（共 {len(public_edits)} 处）")
            return cand, public_edits
        previous_candidate, rejection_reason = cand, scope["reason"]
    return content, []


def _apply_planned_fixes(content, log, *, provider, emit, skill_selection=False, use_model_planner=True):
    """Install explicit checker/repair callbacks; the planner cannot supply edits."""
    parsed_math = analyze_math(content)
    nodes = [{**node, "math_kind": node["kind"], "kind": "formula",
              "start": node["body_start"], "end": node["body_end"]} for node in parsed_math["nodes"]]
    if r"\begin{tabular}" in mask_opaque(content):
        nodes.append({"id": "table-document", "kind": "table", "line": 1, "document_text": content})
    if inspect_tex_cleanup(content)["problems"]:
        nodes.append({"id": "cleanup-document", "kind": "cleanup", "line": 1, "document_text": content})

    verifier_unavailable = False
    formula_feedback = {}
    table_feedback = {}
    cleanup_feedback = {"previous_candidate": None, "rejection_reason": None, "seen": set()}

    def check(node):
        nonlocal verifier_unavailable
        if node["kind"] == "formula":
            if verifier_unavailable:
                result = {"status": "NEEDS_ENV", "reason": "checker_unavailable"}
            elif node.get("checkable", True):
                result = _verify_formula(node["latex"])
            else:
                grid = check_math_grids(node["latex"]) if node.get("reason") == "structured_math" else None
                result = grid or {"status": "NEEDS_HUMAN", "reason": node.get("reason", "复杂结构需人工核对")}
            if result.get("status") == "NEEDS_ENV":
                verifier_unavailable = True
            emit("CHECK", node_id=node["id"], line=node["line"], original=node["latex"],
                 checker="doc-formula-verify", check=result)
            return result
        if node["kind"] == "cleanup":
            c_problems = _cleanup_problems(content)
            emit("CLEANUP_CHECK", node_id=node["id"], problems=c_problems, model_calls=0)
            return {"status": "RETRY" if c_problems else "OK", "problems": c_problems}
        problems = _table_problems(content)
        emit("TABLE_CHECK", node_id=node["id"], problems=problems, model_calls=0)
        status = "NEEDS_HUMAN" if any(p["status"] != "RETRY" for p in problems) else ("RETRY" if problems else "OK")
        return {"status": status, "problems": problems}

    def repair(node, timeout):
        nonlocal verifier_unavailable
        if node["kind"] == "formula":
            original, attempt = node["latex"], node["attempts"]
            feedback = formula_feedback.setdefault(node["id"], {
                "previous_candidate": None, "rejection_reason": None, "seen": set()})
            calls = 0

            def finish(candidate, outcome, *, stop=False):
                nonlocal verifier_unavailable
                check_result = outcome["check"]
                if check_result.get("status") == "NEEDS_ENV":
                    verifier_unavailable = True
                    stop = True
                if outcome["reason"] == "planner_deadline_exhausted":
                    stop = True
                emit("CANDIDATE_ACCEPTED" if outcome["accepted"] else "CANDIDATE_REJECTED",
                     node_id=node["id"], attempt=attempt, candidate=candidate,
                     reason=outcome["reason"], check=check_result)
                feedback.update(previous_candidate=candidate, rejection_reason=_formula_rejection_feedback(outcome), check=check_result)
                edit = {"line": node["line"], "before": original, "after": candidate,
                        "skill": "doc-formula-verify", "start": node["start"], "end": node["end"]}
                return {"accepted": outcome["accepted"], "check": check_result,
                        "edits": [edit] if outcome["accepted"] and candidate != original else [],
                        "model_calls": calls, "stop": stop}

            if verifier_unavailable:
                return {"accepted": False, "check": {"status": "NEEDS_ENV", "reason": "checker_unavailable"},
                        "model_calls": 0, "stop": True}
            blocker = repair_blocker(original)
            if blocker and not can_attempt_structural_repair(original):
                emit("REPAIR_SKIPPED", node_id=node["id"], reason=blocker, model_calls=0)
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": blocker},
                        "model_calls": 0, "stop": True}
            deterministic = deterministic_candidate(original) if attempt == 1 else None
            if deterministic is not None:
                feedback["seen"].add(deterministic)
                emit("DETERMINISTIC_REPAIR", node_id=node["id"], original=original,
                     candidate=deterministic, model_calls=0)
                outcome = _check_formula_candidate(original, deterministic, node_id=node["id"],
                                                   attempt=attempt, emit=emit, remaining=planner.remaining_seconds,
                                                   allow_math_whitespace=True)
                if outcome["accepted"] or outcome["check"].get("status") == "NEEDS_ENV" or planner.remaining_seconds() <= 0:
                    return finish(deterministic, outcome)
                emit("CANDIDATE_REJECTED", node_id=node["id"], attempt=attempt,
                     candidate=deterministic, reason=outcome["reason"], check=outcome["check"],
                     provider="deterministic-formula", model_calls=0)
                feedback.update(previous_candidate=deterministic, rejection_reason=_formula_rejection_feedback(outcome), check=outcome["check"])
            if planner.remaining_seconds() <= 0:
                return finish(None, {"accepted": False, "check": {"status": "NEEDS_HUMAN"},
                                     "reason": "planner_deadline_exhausted"})
            context = _formula_repair_context(attempt, feedback.get("check", node.get("check", {})),
                                              feedback["previous_candidate"], feedback["rejection_reason"])
            emit("PROVIDER_START", node_id=node["id"], attempt=attempt, original=original, repair_context=context)
            repair_options = {"timeout": min(timeout, planner.remaining_seconds())}
            if skill_selection:
                repair_options["loaded_skill"] = node["loaded_skill"]
            calls = 1
            candidate = provider.repair_formula({"id": node["id"], "data": {
                "latex": original, "repair_context": context}}, **repair_options)
            provider_trace = getattr(provider, "last_trace", {})
            if not isinstance(provider_trace, dict):
                provider_trace = {"reason": "trace_unavailable", "model_calls": None}
            emit("PROVIDER_RESULT", node_id=node["id"], attempt=attempt, candidate=candidate,
                 provider_trace=provider_trace)
            if planner.remaining_seconds() <= 0:
                return finish(candidate, {"accepted": False, "check": {"status": "NEEDS_HUMAN"},
                                          "reason": "planner_deadline_exhausted"})
            if not isinstance(candidate, str) or not candidate.strip():
                reason = provider_trace.get("reason") or "no_valid_candidate"
                return finish(None, {"accepted": False, "check": node.get("check", {"status": "RETRY"}), "reason": reason})
            if assess_candidate(original, candidate).get("method") == "unchanged":
                return finish(candidate, {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "model_abstained"},
                                          "reason": "model_abstained"}, stop=True)
            if candidate in feedback["seen"]:
                return finish(candidate, {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "repeated_candidate"},
                                          "reason": "repeated_candidate"}, stop=True)
            feedback["seen"].add(candidate)
            outcome = _check_formula_candidate(original, candidate, node_id=node["id"],
                                               attempt=attempt, emit=emit, remaining=planner.remaining_seconds)
            return finish(candidate, outcome)
        if node["kind"] == "cleanup":
            attempt = node["attempts"]
            det = deterministic_cleanup_candidate(content) if attempt == 1 else None
            if det is not None:
                scope = assess_cleanup_candidate(content, det)
                if scope["allowed"]:
                    c_edits = cleanup_edits(content, det)
                    emit("DETERMINISTIC_REPAIR", node_id=node["id"], candidate_edits=len(c_edits), model_calls=0)
                    emit("CANDIDATE_ACCEPTED", node_id=node["id"], attempt=attempt,
                         reason=scope["reason"], check={"status": "OK"},
                         provider="deterministic-cleanup", model_calls=0)
                    return {"accepted": True, "check": {"status": "OK"}, "edits": c_edits, "model_calls": 0}
            if planner.remaining_seconds() <= 0:
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN"},
                        "model_calls": 0, "stop": True}
            if (planner.model_calls >= planner.budget.max_model_calls
                    or not callable(getattr(provider, "repair_cleanup", None))):
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "model_budget_or_unavailable"},
                        "model_calls": 0, "stop": True}
            first_kind = (node.get("check", {}).get("problems") or [{"kind": "cleanup"}])[0].get("kind", "cleanup")
            context = _formula_repair_context(attempt, {"status": "RETRY", "reason": first_kind},
                                              cleanup_feedback["previous_candidate"],
                                              cleanup_feedback["rejection_reason"])
            emit("PROVIDER_START", node_id=node["id"], attempt=attempt, repair_context=context)
            repair_options = {"timeout": min(timeout, planner.remaining_seconds())}
            if skill_selection:
                repair_options["loaded_skill"] = node["loaded_skill"]
            cand = provider.repair_cleanup(
                {"id": node["id"], "data": {"content": content, "repair_context": context}},
                **repair_options,
            )
            provider_trace = getattr(provider, "last_trace", {})
            if not isinstance(provider_trace, dict):
                provider_trace = {"reason": "trace_unavailable", "model_calls": None}
            emit("PROVIDER_RESULT", node_id=node["id"], attempt=attempt,
                 candidate=cand, provider_trace=provider_trace)
            if planner.remaining_seconds() <= 0:
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN"},
                        "model_calls": 1, "stop": True}
            if not isinstance(cand, str) or not cand.strip():
                reason = provider_trace.get("reason") or "no_valid_candidate"
                emit("CANDIDATE_REJECTED", node_id=node["id"], attempt=attempt, candidate=cand, reason=reason)
                cleanup_feedback.update(previous_candidate=None, rejection_reason=reason)
                return {"accepted": False, "check": {"status": "RETRY", "reason": reason}, "model_calls": 1}
            if cand == content:
                emit("CANDIDATE_REJECTED", node_id=node["id"], attempt=attempt, candidate=cand, reason="model_abstained")
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "model_abstained"},
                        "model_calls": 1, "stop": True}
            if cand in cleanup_feedback["seen"]:
                emit("CANDIDATE_REJECTED", node_id=node["id"], attempt=attempt, candidate=cand, reason="repeated_candidate")
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "repeated_candidate"},
                        "model_calls": 1, "stop": True}
            cleanup_feedback["seen"].add(cand)
            scope = assess_cleanup_candidate(content, cand)
            emit("CANDIDATE_SCOPE", node_id=node["id"], attempt=attempt, scope=scope)
            emit("CANDIDATE_ACCEPTED" if scope["allowed"] else "CANDIDATE_REJECTED",
                 node_id=node["id"], attempt=attempt, reason=scope["reason"],
                 check={"status": "OK" if scope["allowed"] else "RETRY"})
            if scope["allowed"]:
                return {"accepted": True, "check": {"status": "OK"},
                        "edits": cleanup_edits(content, cand), "model_calls": 1}
            cleanup_feedback.update(previous_candidate=cand, rejection_reason=scope["reason"])
            return {"accepted": False, "check": {"status": "RETRY", "reason": scope["reason"]}, "model_calls": 1}

        edits, line_offsets, offset = [], [], 0
        raw_lines = content.split("\n")
        vis_lines = mask_opaque(content).split("\n")
        for raw_line in raw_lines:
            line_offsets.append(offset)
            offset += len(raw_line) + 1
        for problem in node["check"]["problems"]:
            if problem["status"] != "RETRY" or not isinstance(problem.get("right"), str):
                continue
            resolved = _resolve_table_edit(raw_lines, vis_lines, line_offsets, problem)
            if not resolved:
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN"}, "model_calls": 0}
            if resolved["before"] != resolved["after"]:
                edits.append(resolved)
        working_content = content
        for edit in sorted(edits, key=lambda item: item["start"], reverse=True):
            working_content = working_content[:edit["start"]] + edit["after"] + working_content[edit["end"]:]
        if not _table_problems(working_content):
            return {"accepted": True, "check": {"status": "OK"}, "edits": edits, "model_calls": 0}

        repairable = _extract_repairable_tables(working_content)
        if not repairable or not callable(getattr(provider, "repair_table", None)):
            return {"accepted": False, "check": {"status": "NEEDS_HUMAN"}, "model_calls": 0, "stop": True}
        if planner.remaining_seconds() <= 0 or planner.model_calls >= planner.budget.max_model_calls:
            return {"accepted": False, "check": {"status": "NEEDS_HUMAN"}, "model_calls": 0, "stop": True}

        calls = 0
        attempt = node["attempts"]
        last_reason = "table_repair_rejected"
        model_table_edits = []
        for tbl in repairable:
            if planner.remaining_seconds() <= 0 or planner.model_calls + calls >= planner.budget.max_model_calls:
                break
            fb = table_feedback.setdefault(tbl["id"], {
                "previous_candidate": None, "rejection_reason": None,
                "check": tbl["check"], "seen": set(),
            })
            context = {"attempt": attempt,
                       "checker": {"status": fb["check"].get("status", "RETRY"),
                                   "reason": fb["check"].get("reason", "")},
                       "previous_candidate": fb["previous_candidate"],
                       "rejection_reason": fb["rejection_reason"]}
            emit("PROVIDER_START", node_id=tbl["id"], attempt=attempt,
                 original_rows=tbl["rows"], repair_context=context)
            repair_options = {"timeout": min(timeout, planner.remaining_seconds())}
            if skill_selection:
                repair_options["loaded_skill"] = node["loaded_skill"]
            calls += 1
            cand_rows = provider.repair_table(
                {"id": tbl["id"], "data": {"rows": tbl["rows"], "expected": tbl["expected"], "repair_context": context}},
                **repair_options,
            )
            provider_trace = getattr(provider, "last_trace", {})
            if not isinstance(provider_trace, dict):
                provider_trace = {"reason": "trace_unavailable", "model_calls": None}
            emit("PROVIDER_RESULT", node_id=tbl["id"], attempt=attempt,
                 candidate=cand_rows, provider_trace=provider_trace)
            if planner.remaining_seconds() <= 0:
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN"}, "model_calls": calls, "stop": True}
            if not isinstance(cand_rows, list) or not cand_rows:
                last_reason = provider_trace.get("reason") or "no_valid_candidate"
                emit("CANDIDATE_REJECTED", node_id=tbl["id"], attempt=attempt, candidate=cand_rows, reason=last_reason)
                fb.update(previous_candidate=None, rejection_reason=last_reason)
                continue
            scope = assess_table_candidate(tbl["rows"], cand_rows, expected=tbl["expected"])
            if scope.get("reason") == "unchanged_candidate":
                emit("CANDIDATE_REJECTED", node_id=tbl["id"], attempt=attempt,
                     candidate=cand_rows, reason="model_abstained")
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "model_abstained"},
                        "model_calls": calls, "stop": True}
            seen_key = json.dumps(cand_rows, ensure_ascii=False, separators=(",", ":"))
            if seen_key in fb["seen"]:
                emit("CANDIDATE_REJECTED", node_id=tbl["id"], attempt=attempt,
                     candidate=cand_rows, reason="repeated_candidate")
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "repeated_candidate"},
                        "model_calls": calls, "stop": True}
            fb["seen"].add(seen_key)
            audit_res = _verify_table_grid(cand_rows, tbl["expected"], node_id=tbl["id"])
            emit("CANDIDATE_CHECK", node_id=tbl["id"], attempt=attempt, candidate=cand_rows, check=audit_res)
            emit("CANDIDATE_SCOPE", node_id=tbl["id"], attempt=attempt, candidate=cand_rows, scope=scope)
            accepted = audit_res.get("status") == "OK" and scope.get("allowed") is True
            reason = ("table_verified" if accepted else
                      scope.get("reason", "table_scope_violation") if not scope.get("allowed")
                      else audit_res.get("reason", "checker_rejected"))
            emit("CANDIDATE_ACCEPTED" if accepted else "CANDIDATE_REJECTED",
                 node_id=tbl["id"], attempt=attempt, candidate=cand_rows,
                 reason=reason, check=audit_res)
            if accepted:
                orig_line = raw_lines[tbl["line"] - 1].removesuffix("\r")
                orig_body_end = _table_row_spans(vis_lines[tbl["line"] - 1].removesuffix("\r"))[2]
                body_prefix = orig_line[:orig_body_end]
                lead_len = len(body_prefix) - len(body_prefix.lstrip(" \t"))
                orig_start = line_offsets[tbl["line"] - 1] + lead_len
                orig_end = line_offsets[tbl["line"] - 1] + orig_body_end
                after_row = " & ".join(cand_rows[-1]) + (" " if body_prefix.endswith((" ", "\t")) else "")
                model_table_edits.append({
                    "line": tbl["line"],
                    "before": content[orig_start:orig_end],
                    "after": after_row,
                    "skill": "doc-table-audit",
                    "start": orig_start,
                    "end": orig_end,
                })
            else:
                last_reason = reason
                fb.update(previous_candidate=cand_rows, rejection_reason=reason, check=audit_res)

        replaced_lines = {item["line"] for item in model_table_edits}
        combined_edits = [e for e in edits if e["line"] not in replaced_lines] + model_table_edits
        after_working = content
        for edit in sorted(combined_edits, key=lambda item: item["start"], reverse=True):
            after_working = after_working[:edit["start"]] + edit["after"] + after_working[edit["end"]:]
        if combined_edits and not _table_problems(after_working):
            return {"accepted": True, "check": {"status": "OK"}, "edits": combined_edits, "model_calls": calls}
        return {"accepted": False, "check": {"status": "RETRY", "reason": last_reason}, "model_calls": calls}

    catalog = None
    if skill_selection:
        try:
            catalog = load_catalog()
        except (OSError, ValueError):
            emit("SKILL_SELECTION_REJECTED", reason="catalog_unavailable", state_rev=0)
    planner = ConstrainedPlanner(content, nodes, provider, check, repair, emit, skill_selection=skill_selection,
                                 catalog=catalog, use_model_planner=use_model_planner)
    edits, summary = planner.run()
    fixed = content
    for edit in sorted(edits, key=lambda edit: (edit["start"], edit["end"]), reverse=True):
        if fixed[edit["start"]:edit["end"]] != edit["before"]:
            raise ValueError("candidate_source_mismatch")
        fixed = fixed[:edit["start"]] + edit["after"] + fixed[edit["end"]:]
        emit("CANDIDATE_EDIT", **{k: v for k, v in edit.items() if k not in {"start", "end"}})
    public_edits = [{k: v for k, v in edit.items() if k not in {"start", "end"}} for edit in edits]
    log.append(f"[planner] 执行 {summary['executed']}，拒绝 {summary['rejected']}；候选需人工采用")
    if any(node.get("state") not in {"ok", "candidate"} for node in summary["nodes"]):
        # Only independently reproducible patches can proceed after a model deferral.
        pre_formulas = [n for n in summary["nodes"] if n.get("kind") == "formula" and "id" in n]
        mid_formulas = extract_math(fixed)
        if len(pre_formulas) == len(mid_formulas):
            mid_to_pre = {mid["id"]: pre["id"] for pre, mid in zip(pre_formulas, mid_formulas)}
            skip_ordinals = {
                idx for idx, pre in enumerate(pre_formulas, 1)
                if pre.get("state") in {"ok", "candidate"} or pre.get("attempts", 0) >= 1
            }
        else:
            mid_to_pre = {}
            skip_ordinals = set()
        resolved = set()

        def emit_fallback(action, **fields):
            node_id = fields.get("node_id", "")
            if action == "CANDIDATE_EDIT" and isinstance(node_id, str) and node_id.startswith("f-"):
                resolved.add(mid_to_pre.get(node_id, node_id))
            emit(action, **fields)

        if verifier_unavailable or planner.remaining_seconds() <= 0:
            fixed, local_edits = _apply_table_fixes(fixed, log, emit_fallback)
        else:
            fixed, local_edits = _apply_fixes(
                fixed, log, emit=emit_fallback, use_model=False, skip_ordinals=skip_ordinals
            )
        public_edits.extend(local_edits)
        if local_edits:
            summary["deterministic_resolved"] = sorted(resolved)
            emit("DETERMINISTIC_FALLBACK", edits=len(local_edits), model_calls=0)
            log.append(f"[studio] 规划后确认 {len(local_edits)} 处确定性修复")
    summary["lexical_diagnostics"] = analyze_math(fixed)["diagnostics"]
    return fixed, public_edits, summary


def _planned_problems(summary, content=None):
    # Planner candidates have already been checked. Re-running the whole source
    # here would execute unchosen checks after a refusal or an exhausted budget.
    problems = []
    resolved = set(summary.get("deterministic_resolved", ()))
    pre_formulas = [n for n in summary["nodes"] if n.get("kind") == "formula" and "id" in n]
    post_line_by_id = {}
    if isinstance(content, str):
        parsed = analyze_math(content)
        post_formulas = parsed["nodes"]
        diagnostics = parsed["diagnostics"]
        if len(pre_formulas) == len(post_formulas):
            post_line_by_id = {pre["id"]: post["line"] for pre, post in zip(pre_formulas, post_formulas)}
    else:
        diagnostics = summary.get("lexical_diagnostics", [])
    for node in summary["nodes"]:
        node_id = node.get("id")
        if node.get("state") in {"ok", "candidate"} or (node_id is not None and node_id in resolved):
            continue
        if node.get("kind") == "table":
            if isinstance(content, str):
                problems.extend(_table_problems(content))
            else:
                problems.append({"id": node_id or "table-document", "type": "table_total",
                                 "line": node.get("line", 1), "status": "NEEDS_HUMAN",
                                 "reason": node.get("human_reason", "planner_unresolved")})
        elif node.get("kind") == "cleanup":
            if isinstance(content, str):
                problems.extend(_cleanup_problems(content))
            else:
                problems.append({"id": node_id or "cleanup-document", "type": "cleanup",
                                 "line": node.get("line", 1), "status": "NEEDS_HUMAN",
                                 "reason": node.get("human_reason", "planner_unresolved")})
        else:
            problems.append({"id": node_id, "type": "formula",
                             "line": post_line_by_id.get(node_id, node.get("line", 1)),
                             "status": "NEEDS_HUMAN",
                             "reason": node.get("human_reason", "planner_unresolved")})
    return problems + _math_boundary_problems(diagnostics)


def _job_path(job_id):
    if not isinstance(job_id, str) or not _re.fullmatch(r"[a-f0-9]{8,32}", job_id):
        raise HTTPException(status_code=400, detail="bad job id")
    return os.path.join(STUDIO_STATE, "jobs", job_id)


def _save_job(job_id, job):
    directory = _job_path(job_id)
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "job.json")
    temporary = target + "." + _uuid.uuid4().hex + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(job, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)


def _read_job_events(job_id):
    """Recover complete events, including those before an interrupted write."""
    events = []
    try:
        with open(os.path.join(_job_path(job_id), "events.jsonl"), encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("job_id") == job_id:
                    events.append(event)
    except FileNotFoundError:
        pass
    return events


def _read_job(job_id):
    try:
        with open(os.path.join(_job_path(job_id), "job.json"), encoding="utf-8") as stream:
            job = json.load(stream)
    except (FileNotFoundError, ValueError):
        return None
    if (not isinstance(job, dict) or not isinstance(job.get("done"), bool)
            or not isinstance(job.get("log"), list)
            or not all(isinstance(line, str) for line in job["log"])
            or (job.get("result") is not None and not isinstance(job["result"], dict))
            or (job.get("error") is not None and not isinstance(job["error"], str))):
        return None
    # A single damaged record must not break sorting or JSON serialization of
    # all history, nor expose an invalid review to the decision endpoint.
    created_at = job.get("created_at", 0)
    review = job.get("review")
    if (type(created_at) not in (int, float)
            or (isinstance(created_at, float) and not math.isfinite(created_at))
            or (review is not None and (not isinstance(review, dict)
                or not isinstance(review.get("decision"), str)
                or review["decision"] not in {"accept", "reject"}))):
        return None
    if not job.get("done"):
        job.update(done=True, error="任务在服务重启或中断前未完成；请新建任务，历史事件仍保留。")
    if job.get("result") is None:
        job["trace"] = _read_job_events(job_id)
    return job


def _job_cancelled(job):
    with _job_lock:
        return bool(job.get("cancel_requested"))


def _studio_job(name: str, content: str, job_id: str):
    with _job_lock:
        job = _jobs[job_id]
        log = job["log"]
        skill_selection = job.get("skill_selection", False)
        planner_mode = job.get("planner_mode", False)
    started = time.monotonic()
    trace = []
    input_sha256 = None

    def emit(action, **fields):
        if _job_cancelled(job) and action not in {"JOB_ERROR", "JOB_CANCELLED"}:
            raise JobCancelled()
        with _job_lock:
            event = {"schema_version": 2, "job_id": job_id, "seq": len(trace) + 1,
                     "ts": time.time(), "input_sha256": input_sha256, "action": action, **fields}
            directory = _job_path(job_id)
            os.makedirs(directory, exist_ok=True)
            with open(os.path.join(directory, "events.jsonl"), "a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            trace.append(event)
            # Checkpoint the human-readable log too; full events stay in JSONL.
            _save_job(job_id, job)

    try:
        input_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        with _job_lock:
            _save_job(job_id, job)
        provider = _new_provider(skill_selection=True) if skill_selection else _new_provider()
        emit("JOB_START", name=name, provider_context=provider.fingerprint())
        with _job_lock:
            log.append(f"[studio] 编译修复前版本（原始文档）…")
        before = _studio_compile(content, name, "before-" + job_id)
        with _job_lock:
            log.append(f"[studio] 修复前编译：{'✓ 通过' if before['ok'] else '✗ 失败，请检查编译日志'}")
            _append_compiler_log(log, before)
        emit("COMPILE", phase="before", ok=before["ok"])
        planner_summary = None
        if planner_mode or skill_selection:
            fixed, edits, planner_summary = _apply_planned_fixes(content, log, provider=provider, emit=emit,
                                                                 skill_selection=skill_selection, use_model_planner=planner_mode)
        else:
            fixed, edits = _apply_fixes(content, log, provider=provider, emit=emit)
        with _job_lock:
            log.append(f"[studio] 共应用 {len(edits)} 处修复")
            log.append(f"[studio] 编译修复后版本…")
        after = _studio_compile(fixed, name, "after-" + job_id)
        emit("COMPILE", phase="after", ok=after["ok"])
        model_calls = sum(e.get("provider_trace", {}).get("model_calls") or 0
                          for e in trace if e["action"] in {"PROVIDER_RESULT", "PLANNER_RESULT", "SKILL_SELECTION_PROPOSED"})
        emit("JOB_END", model_calls=model_calls, edits=len(edits),
             candidate_sha256=hashlib.sha256(fixed.encode()).hexdigest())
        problems_after = _planned_problems(planner_summary, fixed) if planner_summary is not None else _analyze(fixed)
        result_payload = {"fixed_content": fixed, "edits": edits,
                          "compile_before": before, "compile_after": after,
                          "problems_after": problems_after,
                          "model": getattr(provider, "model", REPAIR_MODEL) if model_calls else None,
                          "configured_model": getattr(provider, "model", REPAIR_MODEL), "model_calls": model_calls,
                          "provider": provider.name if model_calls else "deterministic-checks",
                          "skill_mode": "selected" if skill_selection else SKILL_MODE,
                          "skill_selection": skill_selection, "planner_mode": planner_mode, "planner": planner_summary,
                          "trace": trace, "job_id": job_id,
                          "elapsed_seconds": round(time.monotonic() - started, 2),
                          "original_sha256": hashlib.sha256(content.encode()).hexdigest(),
                          "candidate_sha256": hashlib.sha256(fixed.encode()).hexdigest(),
                          "requires_review": True,
                          "scope": "TeX 数学片段语法与简单表格合计；不验证数学结论或 OCR 忠实度"}
        with _job_lock:
            log.append(f"[studio] 修复后编译：{'✓ 通过' if after['ok'] else '✗ 失败'}")
            _append_compiler_log(log, after)
            job["result"] = result_payload
            job["done"] = True
            _save_job(job_id, job)
    except JobCancelled:
        with _job_lock:
            job.update(done=True, cancelled=True, result=None, error="任务已取消；原文保持不变。")
            log.append("[studio] 取消已在阶段边界生效，未采用任何候选。")
            emit("JOB_CANCELLED")
            _save_job(job_id, job)
    except Exception as e:  # noqa: BLE001
        # Error text from dependencies may contain private paths or endpoints.
        with _job_lock:
            log.append(f"[studio] 任务失败：{type(e).__name__}")
            job["done"] = True
            job["error"] = f"任务失败（{type(e).__name__}）；请检查运行环境或输入后新建任务。"
            job["trace"] = trace
            try:
                emit("JOB_ERROR", reason=type(e).__name__)
                _save_job(job_id, job)
            except OSError:
                pass


@app.get("/studio")
def studio(request: Request, token: str = Query("")):
    _guard(token)
    response = FileResponse(os.path.join(os.path.dirname(__file__), "studio.html"),
                            headers={"Cache-Control": "no-store"})
    expires = int(time.time()) + MONACO_SESSION_TTL
    response.set_cookie(MONACO_COOKIE, f"{expires}.{_monaco_signature(expires)}",
                        max_age=MONACO_SESSION_TTL, path=MONACO_PREFIX + "/",
                        httponly=True, samesite="strict",
                        secure=request.url.scheme == "https")
    return response


@app.get("/api/studio/files")
def studio_files(token: str = Query("")):
    _guard(token)
    return _document_call(lambda: _documents().listing())


def _runtime_call(operation):
    try:
        return operation()
    except LocalRuntimeError as error:
        raise HTTPException(status_code=error.status, detail=error.message) from None


def _studio_tools():
    return {
        "tectonic": bool(shutil.which(_tectonic_command())),
        "pdftoppm": bool(shutil.which("pdftoppm")),
        "pdfinfo": bool(shutil.which("pdfinfo")),
    }


def _normalize_settings_body(body):
    if not isinstance(body, dict) or set(body) != {"base_url", "model"}:
        raise LocalRuntimeError("invalid_settings", "连接设置仅支持本机地址和模型名称。")
    return {"base_url": validate_base_url(body["base_url"]), "model": _model_name(body["model"])}


@app.get("/api/studio/config")
def studio_config(token: str = Query(""), probe: bool = False):
    _guard(token)
    local_mode = _is_local_mode()
    tools = _studio_tools()
    if local_mode:
        config = _runtime_call(lambda: _local_runtime().probe() if probe else _local_runtime().get_config())
    else:
        base_url = os.environ.get("VLM_BASE_URL") or os.environ.get("VLM_BASE") or VLM_BASE_URL
        config = {"base_url": base_url, "model": REPAIR_MODEL, "local_mode": False, "offline": False,
                  "model_available": None, "tools": tools,
                  "limits": {"file_bytes": MAX_FILE_BYTES, "pdf_pages": MAX_PDF_PAGES,
                             "image_pixels": MAX_IMAGE_PIXELS}}
    return {**config, "local_mode": local_mode, "offline": local_mode,
            "tools": tools,
            "max_document_bytes": 2 * 1024 * 1024, "max_import_pages": 5,
            "math_scope": ["$...$", "$$...$$", "\\(...\\)", "\\[...\\]", "equation", "align"]}


@app.post("/api/studio/settings")
def studio_settings(token: str = Query(""), body: dict = None):
    _guard(token)
    models = _managed_models()
    with models.lock:
        active = models.connection()
        if active:
            normalized = _runtime_call(lambda: _normalize_settings_body(body))
            if normalized == active:
                return {**_local_runtime().get_config(), "local_mode": True, "offline": True, "tools": _studio_tools()}
        job = models.job
        if job and job["action"] == "start" and job["state"] == "running":
            raise HTTPException(status_code=409, detail="请等当前模型启动结束。")
        result = _runtime_call(lambda: _local_runtime(managed=False).update_settings(body))
        if active:
            _runtime_call(models.stop)
    # Settings are per-Studio; no user-global agent/model configuration is changed.
    return {**result, "local_mode": True, "offline": True, "tools": _studio_tools()}


def _guard_local_models(token):
    _guard(token)
    if not _is_local_mode():
        raise HTTPException(status_code=404, detail="内置模型仅用于本地 Studio。")


@app.get("/api/studio/models")
def studio_models(token: str = Query("")):
    _guard_local_models(token)
    return _managed_models().status()


@app.post("/api/studio/models/{action}")
def studio_model_action(action: str, token: str = Query(""), body: dict = None):
    _guard_local_models(token)
    models = _managed_models()
    if action == "stop":
        _runtime_call(models.stop)
        return models.status()
    return _runtime_call(lambda: models.submit(action, (body or {}).get("profile")))


@app.post("/api/studio/tools/install")
def studio_tools_install(token: str = Query(""), body: dict = None):
    _guard(token)
    # 仅安装用户显式请求的工具;启动与文档处理过程不做任何下载。
    tool = (body or {}).get("tool", "tectonic")
    try:
        if tool == "poppler":
            result = tool_fetch.install_poppler()
        elif tool == "tectonic":
            result = tool_fetch.install_tectonic()
        else:
            raise HTTPException(status_code=400, detail="未知工具;支持 tectonic 或 poppler。")
    except tool_fetch.ToolFetchError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except OSError as error:
        raise HTTPException(status_code=502, detail=f"下载失败：{error}")
    if tool == "tectonic":
        os.environ["TECTONIC"] = result["path"]
    elif tool == "poppler" and isinstance(result.get("path"), str) and result["path"]:
        current_entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
        if result["path"] not in current_entries:
            os.environ["PATH"] = os.pathsep.join([result["path"], *current_entries])
    return {**result, "tools": {"tectonic": bool(shutil.which(_tectonic_command())),
                                "pdftoppm": bool(shutil.which("pdftoppm")),
                                "pdfinfo": bool(shutil.which("pdfinfo"))}}


@app.post("/api/studio/probe")
def studio_probe(token: str = Query(""), body: dict = None):
    _guard(token)
    return _runtime_call(lambda: _local_runtime().probe(body))


@app.post("/api/studio/import")
def studio_import(token: str = Query(""), body: dict = None):
    _guard(token)
    return _runtime_call(lambda: _local_runtime().import_document(body))


@app.post("/api/studio/math")
def studio_math(token: str = Query(""), body: dict = None):
    _guard(token)
    content = _document_call(lambda: document_text((body or {}).get("content")))
    return analyze_math(content)


@app.get("/api/studio/file")
def studio_file(name: str = Query(""), token: str = Query("")):
    _guard(token)
    return _document_call(lambda: _documents().read(name))


@app.post("/api/studio/create")
def studio_create(token: str = Query(""), body: dict = None):
    _guard(token)
    name, content = _document_body(body)
    return _document_call(lambda: _documents().save(name, content, create=True))


@app.post("/api/studio/create-split")
def studio_create_split(token: str = Query(""), body: dict = None):
    _guard(token)
    documents = (body or {}).get("documents")
    if (not isinstance(documents, list) or not 1 <= len(documents) <= MAX_PDF_PAGES
            or any(not isinstance(document, dict) for document in documents)):
        raise HTTPException(status_code=400, detail=f"每次请选择 1–{MAX_PDF_PAGES} 页拆分。")
    entries = [_document_body(document) for document in documents]
    return _document_call(lambda: _documents().create_many(entries))


@app.post("/api/studio/save")
def studio_save(token: str = Query(""), body: dict = None):
    _guard(token)
    name, content = _document_body(body)
    return _document_call(lambda: _documents().save(name, content, (body or {}).get("expected_sha256")))


@app.post("/api/studio/rename")
def studio_rename(token: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    return _document_call(lambda: _documents().rename(body.get("name"), body.get("new_name"), body.get("expected_sha256")))


@app.post("/api/studio/delete")
def studio_delete(token: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    result = _document_call(lambda: _documents().delete(body.get("name"), body.get("expected_sha256")))
    builds = Path(STUDIO_STATE) / "builds" / result["name"].removesuffix(".tex")
    if not builds.is_symlink():
        shutil.rmtree(builds, ignore_errors=True)
    return result


@app.post("/api/studio/analyze")
def studio_analyze(token: str = Query(""), name: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    content = _document_call(lambda: document_text(body.get("content", "")))
    problems = _analyze(content)
    return {"problems": problems,
            "summary": {"formula": sum(1 for p in problems if p["type"] == "formula"),
                        "table": sum(1 for p in problems if p["type"] == "table_total"),
                        "cleanup": sum(1 for p in problems if p["type"] == "cleanup")}}


@app.post("/api/studio/fix")
def studio_fix(token: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    name, content = _document_body(body)
    planner_mode = body.get("planner_mode", False)
    if type(planner_mode) is not bool:
        raise HTTPException(status_code=400, detail="planner_mode must be boolean")
    skill_selection = body.get("skill_selection", False)
    if type(skill_selection) is not bool:
        raise HTTPException(status_code=400, detail="skill_selection must be boolean")
    job_id = _uuid.uuid4().hex
    record = {"done": False, "name": name, "created_at": time.time(),
              "log": [f"[studio] 任务 {job_id} 接收：{name}"],
              "result": None, "planner_mode": planner_mode, "skill_selection": skill_selection}
    # Persist acceptance before returning an ID, even if shutdown precedes the worker.
    try:
        with _job_lock:
            _jobs[job_id] = record
            _save_job(job_id, record)
        threading.Thread(target=_studio_job, args=(name, content, job_id), daemon=True).start()
    except (OSError, RuntimeError):
        with _job_lock:
            _jobs.pop(job_id, None)
        raise HTTPException(status_code=503, detail="could not start repair task") from None
    return {"job": job_id}


@app.get("/api/studio/fixstatus")
def studio_fixstatus(id: str = Query(""), token: str = Query("")):
    _guard(token)
    _job_path(id)
    with _job_lock:
        job = _jobs.get(id) or _read_job(id)
        if not job:
            raise HTTPException(status_code=404, detail="no job")
        return {"done": job["done"], "log": list(job["log"][-30:]), "result": job.get("result"),
                "error": job.get("error"), "trace": list(job.get("trace", [])),
                "review": job.get("review"), "cancel_requested": bool(job.get("cancel_requested", False)),
                "cancelled": bool(job.get("cancelled", False))}


@app.get("/api/studio/jobs")
def studio_jobs(token: str = Query("")):
    _guard(token)
    with _job_lock:
        ids = set(_jobs)
        memory_jobs = {job_id: dict(job) for job_id, job in _jobs.items()}
    directory = Path(STUDIO_STATE) / "jobs"
    if directory.is_dir():
        ids.update(p.name for p in directory.iterdir() if p.is_dir() and _re.fullmatch(r"[a-f0-9]{8,32}", p.name))
    jobs = []
    for job_id in ids:
        job = memory_jobs.get(job_id) or _read_job(job_id)
        if not job:
            continue
        jobs.append({"id": job_id, "name": job.get("name", "历史文档"),
                     "created_at": job.get("created_at", 0), "done": job["done"],
                     "error": job.get("error"), "review": job.get("review"),
                     "cancel_requested": bool(job.get("cancel_requested")),
                     "cancelled": bool(job.get("cancelled")),
                     "has_candidate": isinstance(job.get("result"), dict),
                     "original_sha256": (job.get("result") or {}).get("original_sha256")})
    return {"jobs": sorted(jobs, key=lambda job: job["created_at"], reverse=True)[:100]}


@app.post("/api/studio/jobs/{job_id}/decision")
def studio_job_decision(job_id: str, token: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    with _job_lock:
        job = _jobs.get(job_id) or _read_job(job_id)
        result = (job or {}).get("result")
        if not job or not job["done"] or not isinstance(result, dict):
            raise HTTPException(status_code=409, detail="没有已完成、可审阅的候选。")
        if any(not isinstance(result.get(key), str)
               or not _re.fullmatch(r"[a-f0-9]{64}", result[key])
               for key in ("original_sha256", "candidate_sha256")):
            raise HTTPException(status_code=409, detail="候选记录不完整；请重新生成。")
        decision = body.get("decision")
        if not isinstance(decision, str) or decision not in {"accept", "reject"}:
            raise HTTPException(status_code=400, detail="decision 必须为 accept 或 reject。")
        name, content = _document_body(body)
        if (name != job.get("name", name) or text_hash(content) != result["original_sha256"]
                or body.get("candidate_sha256") != result["candidate_sha256"]):
            raise HTTPException(status_code=409, detail="原文或候选已变化；请重新生成。")
        if job.get("review") and job["review"]["decision"] != decision:
            raise HTTPException(status_code=409, detail="此候选已有相反的审阅决定。")
        if not job.get("review"):
            if decision == "accept" and any(
                edit.get("skill") == "doc-formula-verify"
                and repair_blocker(edit.get("before")) == "missing_script_operand"
                for edit in result.get("edits", [])
            ):
                raise HTTPException(status_code=409, detail="此旧候选含有无法从原文确定的上下标，请核对原文后手动补全。")
            job["review"] = {"decision": decision, "at": time.time(),
                             "original_sha256": result["original_sha256"],
                             "candidate_sha256": result["candidate_sha256"]}
            events = _read_job_events(job_id)
            event = {"schema_version": 2, "job_id": job_id, "seq": len(events) + 1,
                     "ts": time.time(), "action": "USER_ACCEPTED" if decision == "accept" else "USER_REJECTED",
                     **job["review"]}
            with open(os.path.join(_job_path(job_id), "events.jsonl"), "a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            _save_job(job_id, job)
            _jobs[job_id] = job
        return {"job_id": job_id, **job["review"]}


class JobCancelled(Exception):
    pass


@app.post("/api/studio/jobs/{job_id}/cancel")
def studio_job_cancel(job_id: str, token: str = Query("")):
    _guard(token)
    _job_path(job_id)
    with _job_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="没有运行中的任务。")
        if not job["done"]:
            job["cancel_requested"] = True
            _save_job(job_id, job)
        return {"job_id": job_id, "done": job["done"], "cancel_requested": job.get("cancel_requested", False)}


# Default-off single-formula handoff to one server-configured Math Agent.
def _handoff_client():
    return FormulaHandoffClient(STUDIO_STATE)


def _handoff_call(operation):
    try:
        return operation()
    except HandoffError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from None
    except OSError:
        raise HTTPException(status_code=503, detail="handoff_storage_unavailable") from None


@app.get("/api/studio/handoff/config")
def studio_handoff_config(token: str = Query("")):
    _guard(token)
    return {"enabled": os.environ.get("TEXADA_MATH_HANDOFF_ENABLED", "0") == "1", "checkpoint": CHECKPOINT}


@app.post("/api/studio/handoff")
def studio_formula_handoff(token: str = Query(""), body: dict = None):
    _guard(token)
    return _handoff_call(lambda: _handoff_client().propose(body))


@app.post("/api/studio/handoff/{transfer_id}/decision")
def studio_handoff_decision(transfer_id: str, token: str = Query(""), body: dict = None):
    _guard(token)
    return _handoff_call(lambda: _handoff_client().decide(transfer_id, body))
