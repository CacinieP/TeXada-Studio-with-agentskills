"""doc-forensics 演示 Web UI 后端（FastAPI）。

启动（节点上）:
  DEMO_TOKEN=<token> ~/.venvs/docf/bin/uvicorn app:app --host 0.0.0.0 --port 8888 --app-dir ~/doc-forensics/webui
公网经跳板映射 8888→80<NN>，token 必填（守则：公网服务必须鉴权）。
"""

import hashlib
import json
import os
import shlex
import subprocess
import threading
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

TOKEN = os.environ.get("DEMO_TOKEN", "docf-demo")
REPO = os.path.expanduser("~/doc-forensics")
STATE = os.path.join(REPO, "state", "demo")
VLM_MODEL = "qwen3.8:27b-q4_K_M"

app = FastAPI(title="doc-forensics demo")
_run = {"proc": None, "log": [], "done": True, "code": None, "started": None}


def _guard(token: str):
    if token != TOKEN:
        raise HTTPException(status_code=401, detail="bad token")


def _run_pipeline(fresh: bool):
    _run.update(log=[], done=False, code=None, started=time.time())
    inner = "rm -rf state/demo && " if fresh else ""
    inner += (f"PYTHONPATH=harness ~/.venvs/docf/bin/python -m docforensics run samples "
              f"--state state/demo --vlm http://127.0.0.1:11434 --vlm-model {VLM_MODEL}; "
              f"echo RUN_EXIT_$?")
    p = subprocess.Popen(["bash", "-c", inner], cwd=REPO, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, bufsize=1)
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
        r = subprocess.run([os.path.expanduser("~/bin/tectonic"), "-o", d, texf],
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
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    mem = subprocess.run(["bash", "-c", "free -h | sed -n 2p | awk '{print \"mem used \"$3\" / \"$2}'"],
                         capture_output=True, text=True).stdout.strip()
    models = subprocess.run(["bash", "-c", "~/lib/bin/ollama list 2>/dev/null | tail -n +2 | awk '{print $1\" \"$3}'"],
                            capture_output=True, text=True).stdout.strip()
    return {"gpu": gpu, "mem": mem, "models": models, "host": os.uname().nodename}


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
