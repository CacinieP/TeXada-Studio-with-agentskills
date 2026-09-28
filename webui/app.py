"""TeXada Studio with Agent Skills 演示 Web UI 后端（FastAPI）。

启动（仓库根目录，先设置 DEMO_TOKEN）:
  python -m uvicorn app:app --host 127.0.0.1 --port 8888 --app-dir webui
配置与依赖见 README.md；仅用于可信用户的单进程部署。
"""

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import threading
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

TOKEN = os.environ.get("DEMO_TOKEN", "")
if not TOKEN.strip():
    raise RuntimeError("DEMO_TOKEN must be set to a non-empty secret before starting the server")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(REPO, "state", "demo")
VLM_MODEL = os.environ.get("VLM_MODEL", "qwen3.8:27b-q4_K_M")
TECTONIC = os.path.expanduser(os.environ.get("TECTONIC", "tectonic"))

app = FastAPI(title="TeXada Studio with Agent Skills demo")
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


def _run_pipeline(fresh: bool):
    _run.update(log=[], done=False, code=None, started=time.time())
    if fresh and os.path.exists(STATE):
        shutil.rmtree(STATE)
    command = [sys.executable, "-m", "docforensics", "run", "samples", "--state", STATE,
               "--vlm", "http://127.0.0.1:11434", "--vlm-model", VLM_MODEL]
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
    def output(command):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            return result.stdout.strip() if result.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    gpu = output(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"])
    mem_lines = output(["free", "-h"]).splitlines()
    mem = mem_lines[1] if len(mem_lines) > 1 else ""
    models = output(["ollama", "list"])
    return {"gpu": gpu, "mem": mem, "models": models, "host": os.uname().nodename,
            "model": VLM_MODEL}


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
from docforensics.vlm import OllamaProvider  # noqa: E402

SAMPLE_DOCS = os.path.join(REPO, "samples", "docs")
STUDIO_STATE = os.path.join(REPO, "state", "studio")
STUDIO_DOCS = os.path.join(STUDIO_STATE, "documents")
VERIFY = os.path.join(REPO, "skills", "doc-formula-verify", "scripts", "verify.py")
SKILL_MODE = os.environ.get("SKILL_MODE", "on")


def _new_provider():
    return OllamaProvider("http://127.0.0.1:11434", VLM_MODEL, skill_mode=SKILL_MODE)


PROVIDER = _new_provider()
_TABLE_LABELS = ("合计", "总计", "total")
_TABLE_NUMBER = r"[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)"
_jobs = {}


def _studio_compile(content: str, name: str, tag: str):
    d = os.path.join(STUDIO_STATE, name.replace(".tex", ""), tag)
    os.makedirs(d, exist_ok=True)
    texf = os.path.join(d, "main.tex")
    with open(texf, "w") as f:
        f.write(content)
    try:
        r = subprocess.run([TECTONIC, "-o", d, texf], capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        return {"ok": False, "log": "compile timeout", "png": None}
    except FileNotFoundError:
        return {"ok": False, "log": "Tectonic not found; install it or set TECTONIC", "png": None}
    ok = r.returncode == 0
    png = None
    if ok:
        try:
            subprocess.run(["pdftoppm", "-png", "-r", "100", "-singlefile",
                            os.path.join(d, "main.pdf"), os.path.join(d, "preview")],
                           check=True, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "log": "PDF generated but preview conversion failed; check pdftoppm", "png": None}
        p = os.path.join(d, "preview.png")
        png = f"/api/studio/preview/{name}/{tag}?v={int(time.time())}" if os.path.exists(p) else None
    return {"ok": ok, "log": (r.stderr or r.stdout or "")[-600:], "png": png}


@app.post("/api/studio/preview")
def studio_preview_live(token: str = Query(""), body: dict = None):
    """编译当前编辑器内容并返回整页渲染（预览窗口用）。"""
    _guard(token)
    body = body or {}
    name, content = body.get("name", ""), body.get("content", "")
    if not _re.fullmatch(r"[\w.-]+\.tex", name):
        raise HTTPException(status_code=400, detail="bad name")
    tag = "live-" + hashlib.sha1(content.encode()).hexdigest()[:12]
    res = _studio_compile(content, name, tag)
    return {"ok": res["ok"], "png": res["png"], "log": res["log"]}


@app.post("/api/studio/upload")
def studio_upload(token: str = Query(""), body: dict = None):
    """导入 .tex 文档到被 Git 忽略的 state/studio/documents。"""
    _guard(token)
    body = body or {}
    name, content = body.get("name", ""), body.get("content", "")
    if not _re.fullmatch(r"[\w\u4e00-\u9fff.-]+\.tex", name or ""):
        raise HTTPException(status_code=400, detail="仅支持 .tex 文件名")
    if name in (".", "..") or "/" in name:
        raise HTTPException(status_code=400, detail="bad name")
    os.makedirs(STUDIO_DOCS, exist_ok=True)
    with open(os.path.join(STUDIO_DOCS, name), "w") as f:
        f.write(content)
    return {"ok": True, "name": name}


@app.get("/api/studio/pdf/{name}/{tag}")
def studio_pdf(name: str, tag: str, token: str = Query("")):
    _guard(token)
    if not (_re.fullmatch(r"[\w.-]+", name) and _re.fullmatch(r"[\w-]+", tag)):
        raise HTTPException(status_code=400, detail="bad path")
    p = os.path.join(STUDIO_STATE, name.replace(".tex", ""), tag, "main.pdf")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="no pdf")
    return FileResponse(p, media_type="application/pdf", filename=name.replace(".tex", f"-{tag}.pdf"))


@app.get("/api/studio/preview/{name}/{tag}")
def studio_preview(name: str, tag: str, token: str = Query("")):
    _guard(token)
    _safe = _re.fullmatch(r"[\w.-]+", name) and _re.fullmatch(r"[\w-]+", tag)
    if not _safe:
        raise HTTPException(status_code=400, detail="bad path")
    p = os.path.join(STUDIO_STATE, name.replace(".tex", ""), tag, "preview.png")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="no preview")
    return FileResponse(p)


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
    problems, nid = [], 0
    for i, line in enumerate(content.splitlines(), 1):
        for m in _re.finditer(r"(?<!\\)\$(.+?)(?<!\\)\$", line):
            nid += 1
            vj = _verify_formula(m.group(1))
            if emit:
                emit("CHECK", node_id=f"f-{i:03d}-{nid}", line=i, original=m.group(1),
                     checker="doc-formula-verify", check=vj)
            if vj.get("status") != "OK":
                problems.append({"id": f"f-{i:03d}-{nid}", "type": "formula", "line": i,
                                 "latex": m.group(1), "status": vj["status"],
                                 "reason": vj.get("reason", "")})
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

    for i, line in enumerate(content.splitlines()):
        stripped = line.strip()
        if stripped.startswith("%"):
            continue
        if r"\begin{tabular}" in line:
            if in_tab:
                shape_reason = "嵌套表格不在自动合计检查范围，需人工核对"
                continue
            in_tab, rows, shape_reason = True, [], ""
            spec = _re.fullmatch(r"\\begin\{tabular\}\s*\{([lcr|\s]+)\}", stripped)
            width = sum(c in "lcr" for c in spec.group(1)) if spec else None
            continue
        if not in_tab:
            continue
        if r"\end{tabular}" in line:
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
    emit = emit or (lambda action, **fields: None)
    lines = content.splitlines(keepends=True)
    edits = []
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
        li = p["line"] - 1
        latex = p["latex"]
        fixed, ok = None, False
        for attempt in (1, 2):
            log.append(f"[doc-formula-verify] {p['id']} L{p['line']} RETRY → 本地模型文本修复（第 {attempt} 次）")
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
            old = f"${latex}$"
            if old in lines[li]:
                lines[li] = lines[li].replace(old, f"${fixed}$", 1)
                edits.append({"line": p["line"], "before": latex, "after": fixed, "skill": "doc-formula-verify"})
                emit("CANDIDATE_EDIT", node_id=p["id"], line=p["line"], before=latex, after=fixed)
    content = "".join(lines)

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


def _job_path(job_id):
    if not isinstance(job_id, str) or not _re.fullmatch(r"[a-f0-9]{8,32}", job_id):
        raise HTTPException(status_code=400, detail="bad job id")
    return os.path.join(STUDIO_STATE, "jobs", job_id)


def _save_job(job_id, job):
    directory = _job_path(job_id)
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "job.json")
    temporary = target + ".tmp"
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
        provider = _new_provider()
        emit("JOB_START", name=name, provider_context=provider.fingerprint())
        log.append(f"[studio] 编译修复前版本（原始文档）…")
        before = _studio_compile(content, name, "before-" + job_id)
        log.append(f"[studio] 修复前编译：{'✓ 通过' if before['ok'] else '✗ 失败，请检查编译日志'}")
        emit("COMPILE", phase="before", ok=before["ok"])
        fixed, edits = _apply_fixes(content, log, provider=provider, emit=emit)
        log.append(f"[studio] 共应用 {len(edits)} 处修复")
        log.append(f"[studio] 编译修复后版本…")
        after = _studio_compile(fixed, name, "after-" + job_id)
        emit("COMPILE", phase="after", ok=after["ok"])
        model_calls = sum(e.get("provider_trace", {}).get("model_calls") or 0
                          for e in trace if e["action"] == "PROVIDER_RESULT")
        emit("JOB_END", model_calls=model_calls, edits=len(edits),
             candidate_sha256=hashlib.sha256(fixed.encode()).hexdigest())
        log.append(f"[studio] 修复后编译：{'✓ 通过' if after['ok'] else '✗ 失败'}")
        job["result"] = {"fixed_content": fixed, "edits": edits,
                         "compile_before": before, "compile_after": after,
                         "problems_after": _analyze(fixed),
                         "model": VLM_MODEL if model_calls else None,
                         "configured_model": VLM_MODEL, "model_calls": model_calls,
                         "provider": "local-model-text" if model_calls else "deterministic-checks",
                         "skill_mode": SKILL_MODE, "trace": trace, "job_id": job_id,
                         "elapsed_seconds": round(time.monotonic() - started, 2),
                         "original_sha256": hashlib.sha256(content.encode()).hexdigest(),
                         "candidate_sha256": hashlib.sha256(fixed.encode()).hexdigest(),
                         "requires_review": True,
                         "scope": "行内公式语法与简单表格合计；不验证数学语义，不读取图像"}
        job["done"] = True
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
    files = {f for directory in (SAMPLE_DOCS, STUDIO_DOCS) if os.path.isdir(directory)
             for f in os.listdir(directory) if f.endswith(".tex")}
    return {"files": sorted(files)}


@app.get("/api/studio/file")
def studio_file(name: str = Query(""), token: str = Query("")):
    _guard(token)
    if not _re.fullmatch(r"[\w.-]+\.tex", name):
        raise HTTPException(status_code=400, detail="bad name")
    path = os.path.join(STUDIO_DOCS, name)
    if not os.path.isfile(path):
        path = os.path.join(SAMPLE_DOCS, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="no file")
    with open(path) as f:
        return {"name": name, "content": f.read()}


@app.post("/api/studio/analyze")
def studio_analyze(token: str = Query(""), name: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    content = body.get("content", "")
    problems = _analyze(content)
    return {"problems": problems,
            "summary": {"formula": sum(1 for p in problems if p["type"] == "formula"),
                        "table": sum(1 for p in problems if p["type"] == "table_total")}}


@app.post("/api/studio/fix")
def studio_fix(token: str = Query(""), body: dict = None):
    _guard(token)
    body = body or {}
    name, content = body.get("name", ""), body.get("content", "")
    if not isinstance(name, str) or not _re.fullmatch(r"[\w.-]+\.tex", name):
        raise HTTPException(status_code=400, detail="bad name")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="content must be text")
    try:
        content.encode("utf-8")
    except UnicodeEncodeError:
        raise HTTPException(status_code=400, detail="content must be valid UTF-8 text") from None
    job_id = _uuid.uuid4().hex
    _jobs[job_id] = {"done": False, "log": [f"[studio] 任务 {job_id} 接收：{name}"], "result": None}
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
            "error": job.get("error"), "trace": job.get("trace", [])}
