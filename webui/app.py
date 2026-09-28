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

_sys.path.insert(0, os.path.join(REPO, "harness"))
from docforensics.vlm import OllamaProvider  # noqa: E402

SAMPLE_DOCS = os.path.join(REPO, "samples", "docs")
STUDIO_STATE = os.path.join(REPO, "state", "studio")
STUDIO_DOCS = os.path.join(STUDIO_STATE, "documents")
VERIFY = os.path.join(REPO, "skills", "doc-formula-verify", "scripts", "verify.py")
PROVIDER = OllamaProvider("http://127.0.0.1:11434", VLM_MODEL)
_TABLE_LABELS = ("合计", "总计", "total")
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


def _formula_problems(content: str):
    problems, nid = [], 0
    for i, line in enumerate(content.splitlines(), 1):
        for m in _re.finditer(r"(?<!\\)\$(.+?)(?<!\\)\$", line):
            nid += 1
            fid = f"f-{i:03d}-{nid}"
            v = subprocess.run([_sys.executable, VERIFY, m.group(1)], capture_output=True, text=True)
            try:
                vj = json.loads(v.stdout.strip().splitlines()[-1])
            except Exception:
                vj = {"status": "OK"}
            if vj.get("status") != "OK":
                problems.append({"id": fid, "type": "formula", "line": i, "latex": m.group(1),
                                 "status": vj.get("status", "RETRY"), "reason": vj.get("reason", "")})
    return problems


def _table_problems(content: str):
    problems, lines = [], content.splitlines()
    in_tab, rows, start = False, [], 0
    for i, line in enumerate(lines + [r"\end{tabular}"]):
        if r"\begin{tabular}" in line:
            in_tab, rows, start = True, [], i
            continue
        if in_tab and "&" in line:
            rows.append((i, [c.strip() for c in line.split("&")]))
        if r"\end{tabular}" in line and in_tab:
            in_tab = False
            if rows and any(k in rows[-1][1][0].lower() for k in _TABLE_LABELS):
                total_i, total_cells = rows[-1]
                data = [c for li, c in rows[1:-1]]
                for j in range(1, len(total_cells)):
                    vals = []
                    for c in data:
                        if j >= len(c):
                            continue
                        m = _re.search(r"[+-]?\d[\d,]*\.?\d*", c[j])
                        vals.append(float(m.group(0).replace(",", "")) if m else None)
                    if any(v is None for v in vals):
                        continue
                    want = _re.search(r"[+-]?\d[\d,]*\.?\d*", total_cells[j])
                    want = float(want.group(0).replace(",", "")) if want else None
                    got = sum(vals)
                    if want is None or abs(got - want) > 1e-9:
                        problems.append({"id": f"t-{total_i+1:03d}-{j}", "type": "table_total",
                                         "line": total_i + 1, "col": j, "wrong": total_cells[j],
                                         "right": str(int(got)) if got == int(got) else str(got),
                                         "status": "RETRY",
                                         "reason": f"合计列 {j+1}：标注 {want}，数据行之和 {got}"})
            rows, in_tab = [], False
    return problems


def _analyze(content: str):
    fp = _formula_problems(content)
    tp = _table_problems(content)
    return fp + tp


def _apply_fixes(content: str, log):
    lines = content.splitlines()
    edits = []
    fp = _formula_problems(content)
    for p in fp:
        li = p["line"] - 1
        latex = p["latex"]
        fixed, ok = None, False
        for attempt in (1, 2):
            log.append(f"[doc-formula-verify] {p['id']} L{p['line']} RETRY → VLM 重识别（第 {attempt} 次）")
            cand = PROVIDER.repair_formula({"id": p["id"], "data": {"latex": latex}})
            if not cand:
                log.append(f"[doc-formula-verify] {p['id']} VLM 无有效修复")
                continue
            v = subprocess.run([_sys.executable, VERIFY, cand], capture_output=True, text=True)
            try:
                vj = json.loads(v.stdout.strip().splitlines()[-1])
            except Exception:
                vj = {"status": "RETRY"}
            if vj.get("status") == "OK":
                fixed, ok = cand, True
                log.append(f"[doc-formula-verify] {p['id']} 修复 → SymPy 回判 ✓ ：{cand}")
                break
            log.append(f"[doc-formula-verify] {p['id']} SymPy 拒绝：{vj.get('reason','')[:80]}")
        if ok and fixed != latex:
            old = f"${latex}$"
            if old in lines[li]:
                lines[li] = lines[li].replace(old, f"${fixed}$", 1)
                edits.append({"line": p["line"], "before": latex, "after": fixed, "skill": "doc-formula-verify"})
    content = "\n".join(lines) + ("\n" if content.endswith("\n") else "")

    tp = _table_problems(content)
    lines = content.splitlines()
    for p in tp:
        li = p["line"] - 1
        cells = lines[li].split("&")
        j = p["col"]
        if j < len(cells):
            log.append(f"[doc-table-audit] {p['id']} {p['reason']} → 重算为 {p['right']}")
            edits.append({"line": p["line"], "before": cells[j].strip(), "after": p["right"], "skill": "doc-table-audit"})
            # 只替换数值本身，保留行尾 \\ 等表格结构
            cells[j] = _re.sub(r"[+-]?\d[\d,]*\.?\d*", p["right"], cells[j], count=1)
            lines[li] = "&".join(cells)
    content = "\n".join(lines) + ("\n" if content.endswith("\n") else "")
    return content, edits


def _studio_job(name: str, content: str, job_id: str):
    job = _jobs[job_id]
    log = job["log"]
    try:
        log.append(f"[studio] 编译修复前版本（原始文档）…")
        before = _studio_compile(content, name, "before")
        log.append(f"[studio] 修复前编译：{'✓ 通过' if before['ok'] else '✗ 失败（存在注入错误）'}")
        fixed, edits = _apply_fixes(content, log)
        log.append(f"[studio] 共应用 {len(edits)} 处修复")
        log.append(f"[studio] 编译修复后版本…")
        after = _studio_compile(fixed, name, "after")
        log.append(f"[studio] 修复后编译：{'✓ 通过' if after['ok'] else '✗ 失败'}")
        job["result"] = {"fixed_content": fixed, "edits": edits,
                         "compile_before": before, "compile_after": after,
                         "problems_after": _analyze(fixed)}
        job["done"] = True
    except Exception as e:  # noqa: BLE001
        log.append(f"[studio] 出错：{e}")
        job["done"] = True
        job["error"] = str(e)


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
    if not _re.fullmatch(r"[\w.-]+\.tex", name):
        raise HTTPException(status_code=400, detail="bad name")
    job_id = _uuid.uuid4().hex[:8]
    _jobs[job_id] = {"done": False, "log": [f"[studio] 任务 {job_id} 接收：{name}"], "result": None}
    threading.Thread(target=_studio_job, args=(name, content, job_id), daemon=True).start()
    return {"job": job_id}


@app.get("/api/studio/fixstatus")
def studio_fixstatus(id: str = Query(""), token: str = Query("")):
    _guard(token)
    job = _jobs.get(id)
    if not job:
        raise HTTPException(status_code=404, detail="no job")
    return {"done": job["done"], "log": job["log"][-30:], "result": job.get("result"),
            "error": job.get("error")}
