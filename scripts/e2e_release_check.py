"""E2E 发行驱动：预检、场景执行、证据写盘。

仅用于可信本机环境：真实 LaTeX 编译、真实 Ollama OCR 模型、真实 Studio 后端。
运行入口见 docs/superpowers/plans/2026-11-12-e2e-release.md。
"""
import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "harness"))
from docforensics.__main__ import repair_model_default  # noqa: E402  # #23 契约同源

REQUIRED_MODELS = (repair_model_default(), "minicpm-ocr")
DEFAULT_MODELS_BASE = "http://127.0.0.1:11434/v1"
OCR_SCRIPT = REPO_ROOT / "skills/doc-ocr-extract/scripts/ocr_extract.py"
LAYOUT_SCRIPT = REPO_ROOT / "skills/doc-ocr-extract/scripts/ocr_to_layout.py"
_OCR_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class PreflightError(RuntimeError):
    """预检失败：环境或模型不满足真实 E2E 运行条件，消息含修复提示。"""


def probe_python(python_path=REPO_ROOT / ".venv/bin/python"):
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


def _served_name(name):
    """去掉 :tag 后缀（如 minicpm-ocr:latest → minicpm-ocr）；其余原样。"""
    return name.rsplit(":", 1)[0] if ":" in name.split("/")[-1] else name


def probe_models(models_base, required=None, *, urlopen=None, timeout=2.0):
    """模型端点必须可达且确切服务修复线与 OCR 线的模型名；失败必须响亮。"""
    required = required or REQUIRED_MODELS
    urlopen = urlopen or urllib.request.urlopen
    url = models_base.rstrip("/") + "/models"
    try:
        with urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        ids = [m["id"] for m in payload["data"]]
    except Exception as exc:
        raise PreflightError(
            f"模型端点不可达或响应异常：{models_base}（{exc}；确认 Ollama 正在 11434 端口运行）") from exc
    served = {_served_name(mid) for mid in ids}
    for req in required:
        if _served_name(req) not in served:
            raise PreflightError(
                f"模型 {req} 未在端点 {models_base} 服务（现有：{ids}；Ollama 请用在册名，或 `ollama cp` 建别名）")
    return ids


def preflight(skip_model=False, *, models_base=DEFAULT_MODELS_BASE, required=None,
              probe_python=probe_python, probe_latex_tools=probe_latex_tools,
              probe_models=probe_models):
    """真实 E2E 前置检查；skip_model 仅供日常开发，发布运行禁用。"""
    python = probe_python()
    latex_tools = probe_latex_tools()
    models = [] if skip_model else probe_models(models_base, required)
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


def run_e2e2_repair(call, case_path):
    """E2E-2：落稿确定性定界符修复，缺失下标保留人工处理。"""
    t0 = time.time()
    cases = json.loads(Path(case_path).read_text(encoding="utf-8"))["cases"]
    case = next(c for c in cases if c["original_latex"] == "a_+b")
    delimiter = r"\left(\frac{x^2-1}{x-1}"
    content = ("\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n"
               + "$" + delimiter + "$.\n$" + case["original_latex"] + "$.\n\\end{document}\n")
    name = f"{case['id']}.tex"

    def fail(detail):
        return {"id": "E2E-2", "passed": False, "detail": detail,
                "elapsed_seconds": time.time() - t0}

    problems = call("/api/studio/analyze", {"name": name, "content": content}).get("problems") or []
    if not problems:
        return fail(f"analyze 未发现可修问题（case={case['id']}）")
    job = call("/api/studio/fix", {"name": name, "content": content})["job"]
    deadline = time.time() + 600
    entry = None
    while time.time() < deadline:
        entry = next((e for e in call("/api/studio/jobs").get("jobs", []) if e["id"] == job), None)
        if entry is None or entry["done"]:
            break
        time.sleep(2)
    if entry is None or not entry["done"]:
        return fail(f"job 未完成（{job}）")
    if entry.get("error"):
        return fail(f"job 失败：{entry['error']}")
    result = call(f"/api/studio/fixstatus?id={job}").get("result") or {}
    model = result.get("configured_model") or result.get("model") or "?"
    edits = result.get("edits") or []
    problems_after = result.get("problems_after") or []
    if len(problems_after) != 1 or problems_after[0].get("repair_blocker") != "missing_script_operand":
        return fail(f"缺下标未保留为唯一人工审阅项（repair_model={model}）")
    if len(edits) != 1:
        return fail(f"预期一处定界符编辑（repair_model={model}）")
    if result.get("original_sha256") == result.get("candidate_sha256"):
        return fail(f"内容哈希未变化（repair_model={model}）")
    if result.get("fixed_content") != content.replace(delimiter, delimiter + r"\right)"):
        return fail(f"候选未保留原文或未正确闭合定界符（repair_model={model}）")
    compile_after = result.get("compile_after") or {}
    if not compile_after.get("ok"):
        return fail(f"修复后编译失败（repair_model={model}）：{compile_after.get('log', '')[-600:]}")
    if result.get("model_calls") != 0:
        return fail(f"确定性修复或缺下标错误调用了模型（repair_model={model}）")
    return {"id": "E2E-2", "passed": True,
            "detail": f"case={case['id']} edits={len(edits)} "
                      f"model_calls={result.get('model_calls')} repair_model={model}",
            "elapsed_seconds": time.time() - t0}


def _classify_review_line(line: str) -> dict:
    """E2E 用轻量复核分类：整行数学→formula，管道行→table，其余→text。

    只服务于 E2E-3 的链路验收（分类正确性不在验收面）；整行公式判定刻意保守，
    行内数学归 text 与人工复核实践一致。"""
    stripped = line.strip()
    if stripped.count("|") >= 2:
        return {"action": "accept", "type": "table", "separator": "pipe"}
    if re.fullmatch(r"\$[^$]*\$|\\\([^)]*\\\)|\\\[[^\]]*\\\]", stripped) or stripped.startswith("\\begin{"):
        return {"action": "accept", "type": "formula"}
    return {"action": "accept", "type": "text"}


def run_e2e3_ocr(image_dir, *, model="minicpm-ocr:latest", base=DEFAULT_MODELS_BASE,
                 run_ocr=None, python=None, workdir=None) -> dict:
    """E2E-3 OCR→布局：真实 OCR 推理 + 复核门 + 布局落盘（两段式）。

    段 1（真实 OCR）：子进程跑 ocr_extract.py（或注入的 run_ocr 替代模型调用），
      判据 ocr_status_ok：status=OK 且 lines 非空且记录级门（review_items 空、
      output_complete 真）过。
    段 2（布局落稿）：真实 ocr_to_layout.py 两跑——无 review 出模板（门不可跳），
      再携哈希绑定的复核决策出布局；判据 layout_bound_to_source（布局绑定记录哈希）
      与 no_pending_blockers（review_items 空才出布局，契约保证）。
    """
    image_dir = Path(image_dir)
    images = sorted(p for p in image_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in _OCR_IMAGE_SUFFIXES) if image_dir.is_dir() else []
    if not images:
        raise PreflightError(f"样本图像目录为空或不存在：{image_dir}")
    image = images[0]
    python = Path(python or sys.executable)
    started = time.monotonic()
    result = {"id": "E2E-3", "passed": False, "image": image.name, "ocr_model": model,
              "criteria": {name: False for name in ("ocr_status_ok", "review_gate_enforced",
                                                    "layout_emitted", "layout_bound_to_source",
                                                    "no_pending_blockers")}, "detail": ""}
    criteria = result["criteria"]
    if run_ocr is None:
        # ocr_extract 的 path 自带 /v1（其 DEFAULT_BASE 为服务器根），
        # 这里剥掉 OpenAI 风格的 /v1 后缀，避免拼成 /v1/v1/…（2026-11-12 实跑教训）。
        ocr_base = base[:-3] if base.endswith("/v1") else base
        proc = subprocess.run(
            [str(python), str(OCR_SCRIPT), str(image), "--model", model, "--base", ocr_base,
             "--transport", "openai", "--profile", "minicpm-ocr"],
            capture_output=True, text=True, timeout=600)
        code, stdout = proc.returncode, proc.stdout
    else:
        code, stdout = run_ocr(image, model, base[:-3] if base.endswith("/v1") else base)
    record = None
    for line in stdout.splitlines():
        if line.strip():
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            break
    lines = record.get("lines") if isinstance(record, dict) else None
    record_ok = (isinstance(record, dict) and record.get("status") == "OK"
                 and isinstance(lines, list) and bool(lines)
                 and record.get("review_items") == []
                 and record.get("output_complete") is True)
    criteria["ocr_status_ok"] = record_ok
    result["lines"] = len(lines) if isinstance(lines, list) else 0
    if not record_ok:
        result["detail"] = "OCR 记录未过记录级门（status=OK/lines 非空/review_items 空/output_complete 真）"
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result
    own_workdir = workdir is None
    root = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="e2e3-"))
    try:
        root.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(record, ensure_ascii=False).encode("utf-8")
        record_path = root / "record.json"
        record_path.write_bytes(raw)
        import importlib.util
        spec = importlib.util.spec_from_file_location("_ocr_to_layout", LAYOUT_SCRIPT)
        layout_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(layout_mod)
        digest = layout_mod.record_digest(record)  # 单一事实源：与 converter 同一摘要算法
        gate_dir = root / "gate"
        gate = subprocess.run(
            [str(python), str(LAYOUT_SCRIPT), str(record_path), "--doc", "e2e-ocr-01",
             "--output-dir", str(gate_dir)], capture_output=True, text=True, timeout=120)
        criteria["review_gate_enforced"] = (
            gate.returncode == 1 and (gate_dir / "review-template.json").exists()
            and not (gate_dir / "layout.json").exists())
        decisions = []
        index = 0
        while index < len(record["lines"]):
            kind = _classify_review_line(record["lines"][index])
            if kind["type"] == "table":
                end = index
                while (end + 1 < len(record["lines"])
                       and _classify_review_line(record["lines"][end + 1])["type"] == "table"):
                    end += 1
                decisions.append({"start_line": index + 1, "end_line": end + 1, **kind})
                index = end + 1
            else:
                decisions.append({"start_line": index + 1, "end_line": index + 1, **kind})
                index += 1
        review_path = root / "review-decisions.json"
        review_path.write_text(json.dumps(
            {"record_sha256": digest, "reviewer": "e2e-release-check", "decisions": decisions},
            ensure_ascii=False), encoding="utf-8")
        reviewed_dir = root / "reviewed"
        conv = subprocess.run(
            [str(python), str(LAYOUT_SCRIPT), str(record_path), "--review", str(review_path),
             "--doc", "e2e-ocr-01", "--output-dir", str(reviewed_dir)],
            capture_output=True, text=True, timeout=120)
        layout_path = reviewed_dir / "layout.json"
        criteria["layout_emitted"] = conv.returncode == 0 and layout_path.exists()
        if criteria["layout_emitted"]:
            layout = json.loads(layout_path.read_text(encoding="utf-8"))
            nodes = layout.get("nodes", [])
            result["layout"] = {
                "node_types": sorted({n.get("type") for n in nodes}),
                "record_sha256": layout.get("ocr_record_sha256"),
                "node_count": len(nodes)}
            criteria["layout_bound_to_source"] = bool(nodes) and layout.get("ocr_record_sha256") == digest and all(
                n.get("ocr_source", {}).get("record_sha256") == digest for n in nodes)
            review_result = json.loads((reviewed_dir / "review.json").read_text(encoding="utf-8"))
            criteria["no_pending_blockers"] = review_result.get("review_items") == []
        else:
            criteria["layout_bound_to_source"] = False
            criteria["no_pending_blockers"] = False
            result["detail"] = f"布局未产出：converter exit={conv.returncode} {conv.stderr.strip()[-200:]}"
    finally:
        if own_workdir:
            shutil.rmtree(root, ignore_errors=True)
    result["passed"] = all(criteria.values())
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def run_e2e4_persistence(call_factory, *, name="e2e-persistence-01.tex", content=None) -> dict:
    """E2E-4 持久化：后端 A 存档 → 关停 A → 新后端 B 读回。

    call_factory() 每次产出一个**新后端**的调用器（可带 close()）；防假绿：
    读回必须来自工厂第二次产出（新进程），内容逐字节一致且哈希跨进程一致。
    落点 state/studio/documents/（STUDIO_DOCS），两后端共享同一磁盘目录。
    """
    content = content if content is not None else (
        "% TeXada E2E-4 persistence probe\n\\documentclass{article}\n"
        "\\begin{document}\ne2e-4 probe\n\\end{document}\n")
    started = time.monotonic()
    criteria = {"write_ok": False, "read_back_matches": False,
                "hash_consistent": False, "cross_restart": False}
    result = {"id": "E2E-4", "passed": False, "criteria": criteria, "detail": ""}
    expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _close(call):
        close = getattr(call, "close", None)
        if callable(close):
            close()

    call_a = call_factory()
    try:
        saved = call_a("/api/studio/save", {"name": name, "content": content})
    except Exception as exc:
        result["detail"] = f"存档失败：{exc!r}"
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result
    criteria["write_ok"] = (isinstance(saved, dict) and saved.get("ok") is True
                            and saved.get("sha256") == expected_hash)
    _close(call_a)
    call_b = call_factory()
    criteria["cross_restart"] = call_b is not call_a
    try:
        read = call_b(f"/api/studio/file?name={urllib.parse.quote(name)}")
    except Exception as exc:
        result["detail"] = f"读回失败：{exc!r}"
        _close(call_b)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result
    _close(call_b)
    criteria["read_back_matches"] = isinstance(read, dict) and read.get("content") == content
    criteria["hash_consistent"] = (isinstance(read, dict) and isinstance(saved, dict)
                                   and read.get("sha256") == expected_hash == saved.get("sha256"))
    if not all(criteria.values()):
        result["detail"] = "持久化判据未全过：" + ",".join(k for k, v in criteria.items() if not v)
    result["passed"] = all(criteria.values())
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def _persistence_factory(token, env_extra):
    """E2E-4 契约工厂：每次调用产出一个全新后端进程的调用器（close() 关停）。"""
    def factory():
        proc, base_url = boot_backend(token, env_extra=env_extra)
        call = make_call(base_url, token)
        wait_ready(call)

        def close():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

        call.close = close
        return call

    return factory


def build_app(output) -> Path:
    """子进程 desktop/build_bundle.py --output <dir> 构建 .app，返回其路径。"""
    output = Path(output).resolve()
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "desktop/build_bundle.py"), "--output", str(output)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        raise PreflightError(f"构建 .app 失败：{(proc.stderr or proc.stdout)[-500:]}")
    apps = sorted(output.glob("*.app"))
    if not apps:
        raise PreflightError(f"构建产物缺少 .app：{output}")
    return apps[-1]


def _probe_nodeinfo(base_url, token) -> bool:
    try:
        with urllib.request.urlopen(
                f"{base_url}/api/nodeinfo?token={urllib.parse.quote(token)}", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def smoke_app(app_path, *, timeout=30.0, popen_factory=subprocess.Popen,
              ready_probe=None, state_dir=None) -> dict:
    """E2E-5 .app 冒烟：启动 → /api/nodeinfo 200 → SIGTERM → 5s 内 code=0。

    后两条是 #50 修复的行为契约（照 NativeTerminateIntegrationTests 口径）。
    token 由 .app 自生成、从 session.json 发现（产品真实行为）；
    popen_factory / ready_probe 仅供测试注入（慢/外部替代）。
    """
    started = time.monotonic()
    criteria = {"app_launched": False, "nodeinfo_ready": False,
                "sigterm_bounded_exit": False, "graceful_exit_code": False,
                "session_stopped": False}
    result = {"id": "E2E-5", "passed": False, "criteria": criteria, "detail": ""}
    app_path = Path(app_path)
    try:
        exec_name = plistlib.loads((app_path / "Contents/Info.plist").read_bytes()).get("CFBundleExecutable", "")
    except OSError:
        exec_name = ""  # 仅测试注入假件时到此；真 .app 缺 plist 会在拉起时响亮失败
    binary = app_path / "Contents/MacOS" / (exec_name or app_path.stem)
    own_state = state_dir is None
    state = Path(state_dir) if state_dir else Path(tempfile.mkdtemp(prefix="e2e5-"))
    proc = None
    try:
        proc = popen_factory([str(binary), "--state-dir", str(state), "--port", str(_free_port())],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        session = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            path = state / "session.json"
            if path.exists():
                try:
                    candidate = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    candidate = None
                if isinstance(candidate, dict) and candidate.get("base_url"):
                    session = candidate
                    break
            time.sleep(0.2)
        criteria["app_launched"] = session is not None
        if session is not None:
            token = next((v for k, v in urllib.parse.parse_qsl(
                urllib.parse.urlparse(session.get("url", "")).query) if k == "token"), "")
            probe = ready_probe or _probe_nodeinfo
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if probe(session["base_url"], token):
                    criteria["nodeinfo_ready"] = True
                    break
                time.sleep(0.3)
        if criteria["nodeinfo_ready"]:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5.0)
                criteria["sigterm_bounded_exit"] = True
                criteria["graceful_exit_code"] = proc.returncode == 0
                path = state / "session.json"
                if not path.exists():
                    criteria["session_stopped"] = True
                else:
                    try:
                        after = json.loads(path.read_text(encoding="utf-8"))
                    except ValueError:
                        after = None
                    criteria["session_stopped"] = isinstance(after, dict) and after.get("running") is False
            except subprocess.TimeoutExpired:
                result["detail"] = "SIGTERM 后 5 秒未退出（#50 契约违约）"
    finally:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
        if own_state:
            shutil.rmtree(state, ignore_errors=True)
    if not all(criteria.values()) and not result["detail"]:
        result["detail"] = "冒烟判据未全过：" + ",".join(k for k, v in criteria.items() if not v)
    result["passed"] = all(criteria.values())
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def boot_backend(token, *, python=None, cwd=None, env_extra=None):
    """起真实 uvicorn 后端；返回 (popen, base_url)。"""
    port = _free_port()
    env = dict(os.environ)
    env["DEMO_TOKEN"] = token
    env.update(env_extra or {})
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
    ap.add_argument("--models-base", default=DEFAULT_MODELS_BASE,
                    help="OpenAI 兼容模型端点（默认本机 Ollama）")
    ap.add_argument("--repair-model", default=None,
                    help="修复线模型名（默认取契约 repair_model_default()）")
    ap.add_argument("--ocr-model", default="minicpm-ocr:latest")
    args = ap.parse_args(argv)
    repair_model = args.repair_model or repair_model_default()

    try:
        summary = preflight(skip_model=args.skip_model, models_base=args.models_base,
                            required=(repair_model, args.ocr_model))
    except PreflightError as exc:
        print(f"[e2e] 预检失败：{exc}", file=sys.stderr)
        return 2
    print(f"[e2e] 预检通过：python={summary['python']} tools={summary['latex_tools']} "
          f"models={len(summary['models'])} 个 repair_model={repair_model}")

    with tempfile.TemporaryDirectory(prefix="texada-release-state-") as state:
        return _run_scenarios(args, repair_model, state)


def _run_scenarios(args, repair_model, state):
    def want(sid):
        return not args.only or sid in args.only

    backend_env = {"VLM_BASE_URL": args.models_base, "REPAIR_MODEL": repair_model,
                   "TEXADA_STUDIO_STATE_DIR": state}
    token = uuid.uuid4().hex + uuid.uuid4().hex
    results = []
    if want("E2E-1") or want("E2E-2"):
        proc, base_url = boot_backend(token, env_extra=backend_env)
    else:
        proc, base_url = None, ""
    try:
        call = make_call(base_url, token) if base_url else None
        if call is not None:
            wait_ready(call)
        if want("E2E-1"):
            print("[e2e] E2E-1 编译场景…")
            results.append(run_e2e1_compile(call, REPO_ROOT / "samples/docs"))
        if want("E2E-2"):
            print("[e2e] E2E-2 修复场景（确定性补定界符，保留缺项）…")
            results.append(run_e2e2_repair(call, REPO_ROOT / "samples/research/smoke_cases.json"))
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    if want("E2E-3"):
        print("[e2e] E2E-3 OCR→布局场景（真实模型，可能较久）…")
        results.append(run_e2e3_ocr(REPO_ROOT / "samples/ocr", model=args.ocr_model,
                                    base=args.models_base))
    if want("E2E-4"):
        print("[e2e] E2E-4 持久化场景（两起两停后端）…")
        results.append(run_e2e4_persistence(_persistence_factory(token, backend_env)))
    if want("E2E-5"):
        print("[e2e] E2E-5 .app 构建与冒烟（构建可能较久）…")
        output = REPO_ROOT / "dist-app"
        shutil.rmtree(output, ignore_errors=True)
        app = build_app(output)
        results.append(smoke_app(app))
    json_path, md_path = write_evidence(results, Path(args.evidence_dir))
    print(f"[e2e] 证据：{json_path} / {md_path}")
    for r in results:
        print(f"[e2e] {r['id']}: {'通过' if r['passed'] else '未通过'}（{r['elapsed_seconds']:.1f}s）{r['detail']}")
    return 0 if (results and all(r["passed"] for r in results)) else 1


if __name__ == "__main__":
    sys.exit(main())
