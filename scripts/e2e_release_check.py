"""E2E 发行驱动：预检、场景执行、证据写盘。

仅用于可信本机环境：真实 LaTeX 编译、真实 Ollama 模型、真实 Studio 后端。
运行入口见 docs/superpowers/plans/2026-11-12-e2e-release.md。
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

REQUIRED_MODELS = ("openbmb/minicpm-v4.7", "minicpm-ocr")
DEFAULT_MODELS_BASE = "http://127.0.0.1:11434/v1"


class PreflightError(RuntimeError):
    """预检失败：环境或模型不满足真实 E2E 运行条件，消息含修复提示。"""


def probe_python(python_path=Path(".venv/bin/python")):
    """真实运行需要仓库 .venv（macOS ARM 开发环境）。"""
    if not Path(python_path).exists():
        raise PreflightError(f"缺少虚拟环境 {python_path}（先 python3 -m venv .venv 并安装依赖）")
    return str(python_path)


def probe_latex_tools(tools=("tectonic", "pdfinfo"), which=None):
    """编译与 PDF 检查工具必须在 PATH（brew poppler / install_local_tools.py）。"""
    which = which or shutil.which
    missing = [t for t in tools if which(t) is None]
    if missing:
        raise PreflightError(
            f"缺少 LaTeX 工具 {missing}（`brew install poppler` 或 `.venv/bin/python scripts/install_local_tools.py`）")
    return list(tools)


def probe_models(models_base, required=REQUIRED_MODELS, urlopen=None, timeout=2.0):
    """模型端点必须可达且含修复线与 OCR 线所需模型；失败必须响亮。"""
    urlopen = urlopen or urllib.request.urlopen
    url = models_base.rstrip("/") + "/models"
    try:
        with urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        ids = [m["id"] for m in payload["data"]]
    except Exception as exc:
        raise PreflightError(
            f"模型端点不可达或响应异常：{models_base}（{exc}；确认 Ollama 正在 11434 端口运行）") from exc
    for req in required:
        if not any(req in mid for mid in ids):
            raise PreflightError(f"模型 {req} 不在端点 {models_base}（现有：{ids}）")
    return ids


def preflight(skip_model=False, *, models_base=DEFAULT_MODELS_BASE,
              probe_python=probe_python, probe_latex_tools=probe_latex_tools,
              probe_models=probe_models):
    """真实 E2E 前置检查；skip_model 仅供日常开发，发布运行禁用。"""
    python = probe_python()
    latex_tools = probe_latex_tools()
    models = [] if skip_model else probe_models(models_base)
    return {"python": python, "latex_tools": list(latex_tools), "models": list(models)}


def write_evidence(results, out_dir):
    """落盘 e2e-results.json 与 SUMMARY.md；返回 (json_path, md_path)。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_passed = bool(results) and all(r.get("passed") for r in results)
    json_path = out_dir / "e2e-results.json"
    json_path.write_text(json.dumps({"results": results, "all_passed": all_passed},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# E2E 发行验收结果", ""]
    for r in results:
        mark = "通过" if r.get("passed") else "未通过"
        lines.append(f"- {r.get('id')}: {mark}（{r.get('elapsed_seconds', 0):.1f}s）{r.get('detail', '')}")
    lines += ["", "总判定：" + ("全部通过" if all_passed else "未通过")]
    md_path = out_dir / "SUMMARY.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def make_call(base_url, token):
    """注入式 API 调用器：POST JSON→dict，GET 二进制→bytes；token 走查询串（同 webui _guard）。"""
    def call(path, payload=None):
        sep = "&" if "?" in path else "?"
        url = f"{base_url}{path}{sep}token={token}"
        if payload is None:
            req = urllib.request.Request(url, method="GET")
        else:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                         method="POST",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        return json.loads(raw.decode("utf-8")) if "json" in ctype else raw
    return call


def run_e2e1_compile(call, fixture_dir):
    """E2E-1：打开真实 .tex → 编译出 PDF。"""
    t0 = time.time()
    files = sorted(Path(fixture_dir).glob("*.tex"))
    if not files:
        return {"id": "E2E-1", "passed": False, "detail": f"fixture 缺 .tex：{fixture_dir}",
                "elapsed_seconds": 0.0}
    src = files[0]
    res = call("/api/studio/preview", {"name": src.name, "content": src.read_text(encoding="utf-8")})
    tag = res.get("tag", "")
    pdf = call(f"/api/studio/pdf/{src.name}/{tag}")
    elapsed = time.time() - t0
    if not pdf:
        return {"id": "E2E-1", "passed": False, "detail": f"no pdf（{src.name} tag={tag}）",
                "elapsed_seconds": elapsed}
    if not pdf.startswith(b"%PDF"):
        return {"id": "E2E-1", "passed": False, "detail": f"非 PDF 响应（{src.name} tag={tag}）",
                "elapsed_seconds": elapsed}
    return {"id": "E2E-1", "passed": True,
            "detail": f"{src.name} → {len(pdf)} 字节 PDF（tag={tag}）", "elapsed_seconds": elapsed}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def boot_backend(token, *, python=None, cwd=None):
    """起真实 uvicorn 后端；返回 (popen, base_url)。"""
    port = _free_port()
    env = dict(os.environ)
    env["DEMO_TOKEN"] = token
    proc = subprocess.Popen(
        [python or sys.executable, "-m", "uvicorn", "app:app",
         "--host", "127.0.0.1", "--port", str(port), "--app-dir", "webui"],
        cwd=str(cwd or Path(__file__).resolve().parent.parent), env=env)
    return proc, f"http://127.0.0.1:{port}"


def wait_ready(call, timeout=30.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            call("/api/nodeinfo")
            return True
        except Exception as exc:  # 连接被拒属正常启动期
            last = exc
            time.sleep(0.3)
    raise RuntimeError(f"后端未在 {timeout}s 内就绪：{last}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="TeXada Studio E2E 发行验收驱动")
    ap.add_argument("--only", action="append", help="只跑指定场景（可重复）")
    ap.add_argument("--skip-model", action="store_true",
                    help="跳过模型预检（仅供日常开发，发布运行禁用）")
    ap.add_argument("--evidence-dir", default="docs/evaluation-results/e2e-release-01")
    args = ap.parse_args(argv)

    def want(sid):
        return not args.only or sid in args.only

    try:
        summary = preflight(skip_model=args.skip_model)
    except PreflightError as exc:
        print(f"[e2e] 预检失败：{exc}", file=sys.stderr)
        return 2
    print(f"[e2e] 预检通过：python={summary['python']} tools={summary['latex_tools']} "
          f"models={len(summary['models'])} 个")

    token = uuid.uuid4().hex + uuid.uuid4().hex
    proc, base_url = boot_backend(token)
    results = []
    try:
        call = make_call(base_url, token)
        wait_ready(call)
        if want("E2E-1"):
            print("[e2e] E2E-1 编译场景…")
            results.append(run_e2e1_compile(call, Path("samples/docs")))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    json_path, md_path = write_evidence(results, Path(args.evidence_dir))
    print(f"[e2e] 证据：{json_path} / {md_path}")
    for r in results:
        print(f"[e2e] {r['id']}: {'通过' if r['passed'] else '未通过'}（{r['elapsed_seconds']:.1f}s）{r['detail']}")
    return 0 if (results and all(r["passed"] for r in results)) else 1


if __name__ == "__main__":
    sys.exit(main())
