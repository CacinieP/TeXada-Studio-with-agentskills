"""TeXada Studio 本地编辑器后端（FastAPI）。

启动（仓库根目录，先设置 DEMO_TOKEN）:
  python -m uvicorn app:app --host 127.0.0.1 --port 8888 --app-dir webui
配置与依赖见 README.md；仅用于可信用户的单进程部署。
"""

import hashlib
import hmac
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from document_store import DocumentStore, DocumentError, document_name, document_text, text_hash
from local_runtime import LocalRuntime, LocalRuntimeError, make_local_provider

TOKEN = os.environ.get("DEMO_TOKEN", "")
if not TOKEN.strip():
    raise RuntimeError("DEMO_TOKEN must be set to a non-empty secret before starting the server")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(REPO, "state", "demo")
VLM_MODEL = os.environ.get("VLM_MODEL", "MiniCPM-V-4.7-1B")
VLM_BASE_URL = os.environ.get("VLM_BASE_URL", "http://127.0.0.1:11434")
TECTONIC = os.path.expanduser(os.environ.get("TECTONIC", "tectonic"))

app = FastAPI(title="TeXada Studio Local")
_run = {"proc": None, "log": [], "done": True, "code": None, "started": None}


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
               "--vlm", VLM_BASE_URL, "--vlm-model", VLM_MODEL]
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
    d = os.path.join(RENDER, f"tmp-{h}")
    os.makedirs(d, exist_ok=True)
    tex = ("\\documentclass[border=6pt]{standalone}\n\\usepackage{amsmath,amssymb}\n"
           "\\begin{document}\n$\\displaystyle " + latex + "$\n\\end{document}\n")
    texf = os.path.join(d, "f.tex")
    with open(texf, "w") as f:
        f.write(tex)
    try:
        r = subprocess.run([TECTONIC, "-o", d, texf],
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None
    pdf = os.path.join(d, "f.pdf")
    if r.returncode != 0 or not os.path.exists(pdf):
        return None
    subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile", pdf, png[:-4]], check=True)
    return png if os.path.exists(png) else None


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
    runtime_platform = " ".join(part for part in (
        platform.system(), platform.release(), platform.machine()) if part)
    configured_model = VLM_MODEL
    if os.environ.get("TEXADA_LOCAL_MODE", "1") == "1":
        try:
            configured_model = _local_runtime().get_config()["model"]
        except LocalRuntimeError:
            pass
    return {"host": platform.node(), "platform": runtime_platform,
            "python": platform.python_version(), "configured_model": configured_model,
            "model": configured_model,
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
from docforensics.vlm import OpenAICompatibleProvider  # noqa: E402
from docforensics.planner import ConstrainedPlanner  # noqa: E402
from docforensics.skill_selection import load_catalog  # noqa: E402
from docforensics.handoff import FormulaHandoffClient, HandoffError, CHECKPOINT  # noqa: E402
from docforensics.tex_context import analyze_math, extract_math, mask_opaque  # noqa: E402

SAMPLE_DOCS = os.path.join(REPO, "samples", "docs")
STUDIO_STATE = os.environ.get("TEXADA_STUDIO_STATE_DIR", os.path.join(REPO, "state", "studio"))
STUDIO_DOCS = os.path.join(STUDIO_STATE, "documents")
VERIFY = os.path.join(REPO, "skills", "doc-formula-verify", "scripts", "verify.py")
SKILL_MODE = os.environ.get("SKILL_MODE", "on")


def _new_provider(*, skill_selection=False):
    # Selection must see metadata first; do not eagerly load the fixed formula body.
    if os.environ.get("TEXADA_LOCAL_MODE", "1") == "1":
        config = _local_runtime().get_config()
        return make_local_provider(config["base_url"], config["model"],
                                   skill_mode="off" if skill_selection else SKILL_MODE)
    return OpenAICompatibleProvider(VLM_BASE_URL, VLM_MODEL, skill_mode="off" if skill_selection else SKILL_MODE)


def _local_runtime():
    return LocalRuntime(STUDIO_STATE, base_url=os.environ.get("VLM_BASE_URL"), model=os.environ.get("VLM_MODEL"))


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
    _document_call(lambda: document_name(name))
    if not isinstance(tag, str) or not _re.fullmatch(r"[\w-]{1,80}", tag):
        raise HTTPException(status_code=400, detail="bad artifact tag")
    return Path(STUDIO_STATE) / name.removesuffix(".tex") / tag


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
        command = [TECTONIC, "--untrusted", "--only-cached", "--keep-logs",
                   "-o", str(directory), str(texf)]
        try:
            run = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return {**result, "log": "编译超过 120 秒，已停止。请检查文档或本机 TeX 缓存。"}
        except OSError:
            return {**result, "log": "Tectonic not found; install it or set TECTONIC（本机缺少编译器）。"}
        log = (run.stderr or run.stdout or "")[-2400:]
        if run.returncode != 0 or not (directory / "main.pdf").is_file():
            return {**result, "log": log or "未生成 PDF；请检查本机 TeX 缓存和文档语法。"}
        base = f"/api/studio/preview/{quote(name)}/{tag}"
        result.update(compile_ok=True, pdf=f"/api/studio/pdf/{quote(name)}/{tag}", log=log)
        page_count = 1
        try:
            info = subprocess.run(["pdfinfo", str(directory / "main.pdf")],
                                  capture_output=True, text=True, timeout=10)
            match = _re.search(r"^Pages:\s+(\d+)", info.stdout, _re.MULTILINE)
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
                           check=True, capture_output=True, timeout=45)
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
    tag = "live-" + hashlib.sha1(content.encode()).hexdigest()[:12]
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
    return FileResponse(p, media_type="application/pdf", filename=name.replace(".tex", f"-{tag}.pdf"))


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
                                capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout.strip().splitlines()[-1])
        expected_codes = {"OK": 0, "RETRY": 0, "NEEDS_HUMAN": 1, "NEEDS_ENV": 2}
        status = data.get("status")
        if not isinstance(status, str) or result.returncode != expected_codes.get(status):
            raise ValueError("verifier did not complete")
        return data
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, AttributeError):
        return {"status": "NEEDS_ENV", "reason": "公式检查器不可用，请检查 SymPy / antlr 依赖与服务日志"}


def _formula_problems(content: str, emit=None):
    problems = []
    parsed = analyze_math(content)
    for node in parsed["nodes"]:
        vj = (_verify_formula(node["latex"]) if node["checkable"] else
              {"status": "NEEDS_HUMAN", "reason": "复杂数学结构保留原文供人工核对：" + node["reason"]})
        if emit:
            emit("CHECK", node_id=node["id"], line=node["line"], original=node["latex"],
                 checker="doc-formula-verify", check=vj)
        if vj.get("status") != "OK":
            problems.append({**node, "type": "formula", "status": vj["status"], "reason": vj.get("reason", "")})
    for index, diagnostic in enumerate(parsed["diagnostics"]):
        problems.append({**diagnostic, "id": f"math-boundary-{index}", "type": "formula",
                         "status": "NEEDS_HUMAN", "latex": "",
                         "reason": "数学边界未闭合或无法可靠抽取，请先检查原文：" + diagnostic.get("reason", diagnostic.get("code", "unknown"))})
    return problems


def _table_number_match(cell: str):
    """Match the entire plain numeric cell, retaining its source replacement span."""
    return _re.fullmatch(rf"\s*(?P<number>{_TABLE_NUMBER})\s*(?:\\\\)?\s*", cell)


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

    visible_lines = mask_opaque(content).splitlines()
    for i, line in enumerate(content.splitlines()):
        # Keep raw text for numeric replacement; masked source only decides
        # whether this line is executable TeX rather than a printed example.
        if not visible_lines[i].strip():
            continue
        stripped = line.strip()
        if stripped.startswith("%"):
            continue
        if r"\begin{tabular}" in visible_lines[i]:
            if in_tab:
                shape_reason = "嵌套表格不在自动合计检查范围，需人工核对"
                continue
            in_tab, rows, shape_reason = True, [], ""
            spec = _re.fullmatch(r"\\begin\{tabular\}\s*\{([lcr|\s]+)\}", stripped)
            width = sum(c in "lcr" for c in spec.group(1)) if spec else None
            continue
        if not in_tab:
            continue
        if r"\end{tabular}" in visible_lines[i]:
            if stripped != r"\end{tabular}":
                shape_reason = "表格结束标记必须独占一行，需人工核对"
            audit_rows()
            rows, in_tab = [], False
            continue
        if not stripped or stripped in (r"\hline", r"\toprule", r"\midrule", r"\bottomrule"):
            continue
        if not stripped.endswith(r"\\") or r"\\" in stripped[:-2]:
            shape_reason = "仅支持每行一条且以双反斜杠结束的简单表格行，需人工核对"
        body = stripped[:-2] if stripped.endswith(r"\\") else stripped
        rows.append((i, [c.strip() for c in body.split("&")]))
    if in_tab:
        shape_reason = "表格缺少结束标记，需人工核对"
        audit_rows()
    return problems


def _analyze(content: str):
    fp = _formula_problems(content)
    tp = _table_problems(content)
    return fp + tp


def _apply_fixes(content: str, log, *, provider=None, emit=None):
    provider = provider if provider is not None else PROVIDER
    if provider is None:
        provider = _new_provider()
    emit = emit or (lambda action, **fields: None)
    edits, replacements = [], []
    fp = _formula_problems(content, emit)
    verifier_unavailable = False
    for p in fp:
        if verifier_unavailable or p["status"] == "NEEDS_ENV":
            verifier_unavailable = True
            log.append(f"[doc-formula-verify] {p['id']} 检查器不可用，保留原文并转人工")
            emit("REPAIR_SKIPPED", node_id=p["id"], reason="checker_unavailable")
            continue
        if p["status"] != "RETRY":
            log.append(f"[doc-formula-verify] {p['id']} 需要人工审阅，保留原文")
            emit("REPAIR_SKIPPED", node_id=p["id"], reason="needs_human")
            continue
        latex = p["latex"]
        fixed, ok = None, False
        for attempt in (1, 2):
            log.append(f"[doc-formula-verify] {p['id']} L{p['line']} RETRY → 模型文本修复（第 {attempt} 次）")
            emit("PROVIDER_START", node_id=p["id"], attempt=attempt, original=latex)
            cand = provider.repair_formula({"id": p["id"], "data": {"latex": latex}})
            provider_trace = getattr(provider, "last_trace", {})
            if not isinstance(provider_trace, dict):
                provider_trace = {"reason": "trace_unavailable", "model_calls": None}
            emit("PROVIDER_RESULT", node_id=p["id"], attempt=attempt,
                 candidate=cand, provider_trace=provider_trace)
            if not isinstance(cand, str) or not cand.strip():
                log.append(f"[doc-formula-verify] {p['id']} 模型未返回有效候选")
                emit("CANDIDATE_REJECTED", node_id=p["id"], attempt=attempt,
                     candidate=cand, reason="no_valid_candidate")
                continue
            vj = _verify_formula(cand)
            emit("CANDIDATE_CHECK", node_id=p["id"], attempt=attempt, candidate=cand, check=vj)
            if vj.get("status") == "NEEDS_ENV":
                verifier_unavailable = True
                log.append(f"[doc-formula-verify] {p['id']} 候选回判检查器不可用，停止尝试并保留原文")
                emit("CANDIDATE_REJECTED", node_id=p["id"], attempt=attempt,
                     candidate=cand, reason="checker_unavailable", check=vj)
                break
            if vj.get("status") == "OK":
                fixed, ok = cand, True
                log.append(f"[doc-formula-verify] {p['id']} 修复 → SymPy 回判 ✓ ：{cand}")
                emit("CANDIDATE_ACCEPTED", node_id=p["id"], attempt=attempt,
                     candidate=cand, check=vj, meaning="checker_accepted_not_user_adopted")
                break
            log.append(f"[doc-formula-verify] {p['id']} SymPy 拒绝：{vj.get('reason','')[:80]}")
            emit("CANDIDATE_REJECTED", node_id=p["id"], attempt=attempt,
                 candidate=cand, reason="checker_rejected", check=vj)
        if ok and fixed != latex:
            start, end = p.get("body_start"), p.get("body_end")
            if isinstance(start, int) and isinstance(end, int) and content[start:end] == latex:
                replacements.append((start, end, fixed))
                edits.append({"line": p["line"], "before": latex, "after": fixed, "skill": "doc-formula-verify"})
                emit("CANDIDATE_EDIT", node_id=p["id"], line=p["line"], before=latex, after=fixed)
    for start, end, replacement in sorted(replacements, reverse=True):
        content = content[:start] + replacement + content[end:]

    tp = _table_problems(content)
    emit("TABLE_CHECK", problems=tp, model_calls=0)
    lines = content.splitlines(keepends=True)
    for p in tp:
        if p["status"] != "RETRY" or not isinstance(p.get("right"), str):
            log.append(f"[doc-table-audit] {p['id']} {p['reason']} → 保留原文供人工审阅")
            continue
        li = p["line"] - 1
        cells = lines[li].split("&")
        j = p["col"]
        if j < len(cells):
            match = _table_number_match(cells[j])
            if not match or not _re.fullmatch(_TABLE_NUMBER, p["right"]):
                continue
            start, end = match.span("number")
            replacement = cells[j][:start] + p["right"] + cells[j][end:]
            if replacement == cells[j]:
                continue
            log.append(f"[doc-table-audit] {p['id']} {p['reason']} → 重算为 {p['right']}")
            edits.append({"line": p["line"], "before": match.group("number"), "after": p["right"], "skill": "doc-table-audit"})
            cells[j] = replacement
            lines[li] = "&".join(cells)
            emit("CANDIDATE_EDIT", node_id=p["id"], line=p["line"],
                 before=match.group("number"), after=p["right"],
                 provider="deterministic-table", model_calls=0)
    content = "".join(lines)
    return content, edits


def _apply_planned_fixes(content, log, *, provider, emit, skill_selection=False, use_model_planner=True):
    """Install explicit checker/repair callbacks; the planner cannot supply edits."""
    nodes = [{**node, "math_kind": node["kind"], "kind": "formula",
              "start": node["body_start"], "end": node["body_end"]} for node in extract_math(content)]
    if r"\begin{tabular}" in mask_opaque(content):
        nodes.append({"id": "table-document", "kind": "table", "line": 1, "document_text": content})

    def check(node):
        if node["kind"] == "formula":
            result = (_verify_formula(node["latex"]) if node.get("checkable", True) else
                      {"status": "NEEDS_HUMAN", "reason": node.get("reason", "复杂结构需人工核对")})
            emit("CHECK", node_id=node["id"], line=node["line"], original=node["latex"],
                 checker="doc-formula-verify", check=result)
            return result
        problems = _table_problems(content)
        emit("TABLE_CHECK", node_id=node["id"], problems=problems, model_calls=0)
        status = "NEEDS_HUMAN" if any(p["status"] != "RETRY" for p in problems) else ("RETRY" if problems else "OK")
        return {"status": status, "problems": problems}

    def repair(node, timeout):
        if node["kind"] == "formula":
            emit("PROVIDER_START", node_id=node["id"], attempt=node["attempts"], original=node["latex"])
            repair_options = {"timeout": timeout}
            if skill_selection:
                repair_options["loaded_skill"] = node["loaded_skill"]
            candidate = provider.repair_formula({"id": node["id"], "data": {"latex": node["latex"]}}, **repair_options)
            emit("PROVIDER_RESULT", node_id=node["id"], attempt=node["attempts"], candidate=candidate,
                 provider_trace=getattr(provider, "last_trace", {}))
            if planner.remaining_seconds() <= 0:
                emit("CANDIDATE_REJECTED", node_id=node["id"], candidate=candidate, reason="planner_deadline_exhausted")
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN", "reason": "planner_deadline_exhausted"}}
            valid_candidate = (isinstance(candidate, str) and bool(candidate.strip()) and len(candidate) <= 32768
                               and not any(ord(c) < 32 or ord(c) == 127 for c in candidate))
            result = _verify_formula(candidate) if valid_candidate else {"status": "RETRY"}
            accepted = result.get("status") == "OK"
            emit("CANDIDATE_CHECK", node_id=node["id"], candidate=candidate, check=result)
            if planner.remaining_seconds() <= 0:
                emit("CANDIDATE_REJECTED", node_id=node["id"], candidate=candidate, reason="planner_deadline_exhausted")
                return {"accepted": False, "check": result}
            emit("CANDIDATE_ACCEPTED" if accepted else "CANDIDATE_REJECTED", node_id=node["id"],
                 candidate=candidate, reason="checker_accepted_not_user_adopted" if accepted else "checker_rejected")
            edit = {"line": node["line"], "before": node["latex"], "after": candidate,
                    "skill": "doc-formula-verify", "start": node["start"], "end": node["end"]}
            return {"accepted": accepted, "check": result, "edits": [edit] if accepted and candidate != node["latex"] else []}
        edits, line_offsets, offset = [], [], 0
        lines = content.splitlines(keepends=True)
        for line in lines:
            line_offsets.append(offset)
            offset += len(line)
        for problem in node["check"]["problems"]:
            if problem["status"] != "RETRY" or not isinstance(problem.get("right"), str):
                continue
            line_idx = problem["line"] - 1
            cells = lines[line_idx].split("&")
            cell_idx = problem["col"]
            match = _table_number_match(cells[cell_idx])
            if not match or not _re.fullmatch(_TABLE_NUMBER, problem["right"]):
                return {"accepted": False, "check": {"status": "NEEDS_HUMAN"}}
            cell_offset = sum(len(cell) + 1 for cell in cells[:cell_idx])
            start, end = match.span("number")
            edits.append({"line": problem["line"], "before": match.group("number"), "after": problem["right"],
                          "skill": "doc-table-audit", "start": line_offsets[line_idx] + cell_offset + start,
                          "end": line_offsets[line_idx] + cell_offset + end})
        return {"accepted": True, "check": {"status": "OK"}, "edits": edits}

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
    for edit in sorted(edits, key=lambda edit: edit["start"], reverse=True):
        if fixed[edit["start"]:edit["end"]] != edit["before"]:
            raise ValueError("candidate_source_mismatch")
        fixed = fixed[:edit["start"]] + edit["after"] + fixed[edit["end"]:]
        emit("CANDIDATE_EDIT", **{k: v for k, v in edit.items() if k not in {"start", "end"}})
    public_edits = [{k: v for k, v in edit.items() if k not in {"start", "end"}} for edit in edits]
    log.append(f"[planner] 执行 {summary['executed']}，拒绝 {summary['rejected']}；候选需人工采用")
    return fixed, public_edits, summary


def _planned_problems(summary):
    # Planner candidates have already been checked. Re-running the whole source
    # here would execute unchosen checks after a refusal or an exhausted budget.
    return [{"id": node["id"], "type": "formula" if node["kind"] == "formula" else "table_total",
             "line": node.get("line", 1), "status": "NEEDS_HUMAN",
             "reason": node.get("human_reason", "planner_unresolved")}
            for node in summary["nodes"] if node["state"] not in {"ok", "candidate"}]


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
    if not job.get("done"):
        job.update(done=True, error="任务在服务重启或中断前未完成；请新建任务，历史事件仍保留。")
    if job.get("result") is None:
        job["trace"] = _read_job_events(job_id)
    return job


def _studio_job(name: str, content: str, job_id: str):
    job = _jobs[job_id]
    started = time.monotonic()
    log = job["log"]
    trace = []
    input_sha256 = None

    def emit(action, **fields):
        if job.get("cancel_requested") and action not in {"JOB_ERROR", "JOB_CANCELLED"}:
            raise JobCancelled()
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
        _save_job(job_id, job)
        skill_selection = job.get("skill_selection", False)
        provider = _new_provider(skill_selection=True) if skill_selection else _new_provider()
        emit("JOB_START", name=name, provider_context=provider.fingerprint())
        log.append(f"[studio] 编译修复前版本（原始文档）…")
        before = _studio_compile(content, name, "before-" + job_id)
        log.append(f"[studio] 修复前编译：{'✓ 通过' if before['ok'] else '✗ 失败，请检查编译日志'}")
        emit("COMPILE", phase="before", ok=before["ok"])
        planner_mode = job.get("planner_mode", False)
        planner_summary = None
        if planner_mode or skill_selection:
            fixed, edits, planner_summary = _apply_planned_fixes(content, log, provider=provider, emit=emit,
                                                                 skill_selection=skill_selection, use_model_planner=planner_mode)
        else:
            fixed, edits = _apply_fixes(content, log, provider=provider, emit=emit)
        log.append(f"[studio] 共应用 {len(edits)} 处修复")
        log.append(f"[studio] 编译修复后版本…")
        after = _studio_compile(fixed, name, "after-" + job_id)
        emit("COMPILE", phase="after", ok=after["ok"])
        model_calls = sum(e.get("provider_trace", {}).get("model_calls") or 0
                          for e in trace if e["action"] in {"PROVIDER_RESULT", "PLANNER_RESULT", "SKILL_SELECTION_PROPOSED"})
        emit("JOB_END", model_calls=model_calls, edits=len(edits),
             candidate_sha256=hashlib.sha256(fixed.encode()).hexdigest())
        log.append(f"[studio] 修复后编译：{'✓ 通过' if after['ok'] else '✗ 失败'}")
        job["result"] = {"fixed_content": fixed, "edits": edits,
                         "compile_before": before, "compile_after": after,
                         "problems_after": _planned_problems(planner_summary) if planner_summary is not None else _analyze(fixed),
                         "model": getattr(provider, "model", VLM_MODEL) if model_calls else None,
                         "configured_model": getattr(provider, "model", VLM_MODEL), "model_calls": model_calls,
                         "provider": provider.name if model_calls else "deterministic-checks",
                         "skill_mode": "selected" if skill_selection else SKILL_MODE,
                         "skill_selection": skill_selection, "planner_mode": planner_mode, "planner": planner_summary,
                         "trace": trace, "job_id": job_id,
                         "elapsed_seconds": round(time.monotonic() - started, 2),
                         "original_sha256": hashlib.sha256(content.encode()).hexdigest(),
                         "candidate_sha256": hashlib.sha256(fixed.encode()).hexdigest(),
                         "requires_review": True,
                         "scope": "TeX 数学片段语法与简单表格合计；不验证数学结论或 OCR 忠实度"}
        job["done"] = True
        _save_job(job_id, job)
    except JobCancelled:
        job.update(done=True, result=None, error="任务已取消；原文保持不变。")
        log.append("[studio] 取消已在阶段边界生效，未采用任何候选。")
        emit("JOB_CANCELLED")
        _save_job(job_id, job)
    except Exception as e:  # noqa: BLE001
        # Error text from dependencies may contain private paths or endpoints.
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


@app.get("/api/studio/config")
def studio_config(token: str = Query(""), probe: bool = False):
    _guard(token)
    runtime = _local_runtime()
    config = _runtime_call(runtime.probe if probe else runtime.get_config)
    return {**config, "local_mode": os.environ.get("TEXADA_LOCAL_MODE", "1") == "1", "offline": True,
            "tools": {"tectonic": bool(shutil.which(TECTONIC)), "pdftoppm": bool(shutil.which("pdftoppm")),
                      "pdfinfo": bool(shutil.which("pdfinfo"))},
            "max_document_bytes": 2 * 1024 * 1024, "max_import_pages": 5,
            "math_scope": ["$...$", "$$...$$", "\\(...\\)", "\\[...\\]", "equation", "align"]}


@app.post("/api/studio/settings")
def studio_settings(token: str = Query(""), body: dict = None):
    _guard(token)
    result = _runtime_call(lambda: _local_runtime().update_settings(body))
    # Settings are per-Studio; no user-global agent/model configuration is changed.
    return {**result, "local_mode": True, "offline": True,
            "tools": {"tectonic": bool(shutil.which(TECTONIC)), "pdftoppm": bool(shutil.which("pdftoppm"))}}


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
    return _document_call(lambda: _documents().delete(body.get("name"), body.get("expected_sha256")))


@app.post("/api/studio/analyze")
def studio_analyze(token: str = Query(""), name: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    content = _document_call(lambda: document_text(body.get("content", "")))
    problems = _analyze(content)
    return {"problems": problems,
            "summary": {"formula": sum(1 for p in problems if p["type"] == "formula"),
                        "table": sum(1 for p in problems if p["type"] == "table_total")}}


@app.post("/api/studio/fix")
def studio_fix(token: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    name, content = body.get("name", ""), body.get("content", "")
    name, content = _document_body(body)
    planner_mode = body.get("planner_mode", False)
    if type(planner_mode) is not bool:
        raise HTTPException(status_code=400, detail="planner_mode must be boolean")
    skill_selection = body.get("skill_selection", False)
    if type(skill_selection) is not bool:
        raise HTTPException(status_code=400, detail="skill_selection must be boolean")
    job_id = _uuid.uuid4().hex
    _jobs[job_id] = {"done": False, "name": name, "created_at": time.time(),
                     "log": [f"[studio] 任务 {job_id} 接收：{name}"],
                     "result": None, "planner_mode": planner_mode, "skill_selection": skill_selection}
    # Persist acceptance before returning an ID, even if shutdown precedes the worker.
    try:
        _save_job(job_id, _jobs[job_id])
        threading.Thread(target=_studio_job, args=(name, content, job_id), daemon=True).start()
    except (OSError, RuntimeError):
        _jobs.pop(job_id, None)
        raise HTTPException(status_code=503, detail="could not start repair task") from None
    return {"job": job_id}


@app.get("/api/studio/fixstatus")
def studio_fixstatus(id: str = Query(""), token: str = Query("")):
    _guard(token)
    _job_path(id)
    job = _jobs.get(id) or _read_job(id)
    if not job:
        raise HTTPException(status_code=404, detail="no job")
    return {"done": job["done"], "log": job["log"][-30:], "result": job.get("result"),
            "error": job.get("error"), "trace": job.get("trace", []),
            "review": job.get("review"), "cancel_requested": job.get("cancel_requested", False)}


@app.get("/api/studio/jobs")
def studio_jobs(token: str = Query("")):
    _guard(token)
    ids = set(_jobs)
    directory = Path(STUDIO_STATE) / "jobs"
    if directory.is_dir():
        ids.update(p.name for p in directory.iterdir() if p.is_dir() and _re.fullmatch(r"[a-f0-9]{8,32}", p.name))
    jobs = []
    for job_id in ids:
        job = _jobs.get(job_id) or _read_job(job_id)
        if not job:
            continue
        jobs.append({"id": job_id, "name": job.get("name", "历史文档"),
                     "created_at": job.get("created_at", 0), "done": job["done"],
                     "error": job.get("error"), "review": job.get("review"),
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
        decision = body.get("decision")
        if decision not in {"accept", "reject"}:
            raise HTTPException(status_code=400, detail="decision 必须为 accept 或 reject。")
        name, content = _document_body(body)
        if (name != job.get("name", name) or text_hash(content) != result["original_sha256"]
                or body.get("candidate_sha256") != result["candidate_sha256"]):
            raise HTTPException(status_code=409, detail="原文或候选已变化；请重新生成。")
        if job.get("review") and job["review"]["decision"] != decision:
            raise HTTPException(status_code=409, detail="此候选已有相反的审阅决定。")
        if not job.get("review"):
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
