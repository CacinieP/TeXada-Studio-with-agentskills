"""E2E 发行驱动的预检与证据写盘契约测试；不依赖宿主环境（CI 为 ubuntu 无 .venv/tectonic）。"""
import hashlib
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest

from e2e_release_check import (
    PreflightError,
    make_call,
    preflight,
    probe_latex_tools,
    probe_python,
    probe_models,
    run_e2e1_compile,
    run_e2e2_repair,
    run_e2e3_ocr,
    run_e2e4_persistence,
    smoke_app,
    write_evidence,
)

DEAD = "http://127.0.0.1:1/v1"


def _ok_python():
    return "/fake/venv/bin/python"


def _ok_tools():
    return ["tectonic", "pdfinfo"]


class PreflightTests(unittest.TestCase):
    def test_preflight_fails_loudly_when_model_endpoint_is_down(self):
        # 钉住的破坏：模型端点不可达时预检静默通过（真实 probe_models 打死端点）。
        with self.assertRaises(PreflightError):
            preflight(models_base=DEAD,
                      probe_python=_ok_python, probe_latex_tools=_ok_tools,
                      probe_models=probe_models)

    def test_preflight_skip_model_does_not_require_models(self):
        # 钉住的破坏：--skip_model 仍然去连/校验模型（探针被调用即抛错）。
        def _must_not_run(_base):
            raise AssertionError("models probe must not run when skip_model=True")

        summary = preflight(skip_model=True, models_base=DEAD,
                            probe_python=_ok_python, probe_latex_tools=_ok_tools,
                            probe_models=_must_not_run)
        self.assertEqual(summary, {"python": "/fake/venv/bin/python",
                                   "latex_tools": ["tectonic", "pdfinfo"],
                                   "models": []})

    def test_preflight_missing_tool_is_loud_and_names_the_tool(self):
        # 钉住的破坏：缺编译工具时软通过，或报错不指名缺失工具。
        with self.assertRaises(PreflightError) as ctx:
            preflight(models_base=DEAD,
                      probe_python=_ok_python,
                      probe_latex_tools=lambda: probe_latex_tools(
                          tools=("tectonic",), which=lambda _name: None),
                      probe_models=probe_models)
        self.assertIn("tectonic", str(ctx.exception))

    def test_preflight_missing_venv_is_loud(self):
        # 钉住的破坏：缺 .venv 时软通过。
        with self.assertRaises(PreflightError):
            preflight(models_base=DEAD,
                      probe_python=lambda: probe_python(
                          python_path=Path("/nonexistent/venv/bin/python")),
                      probe_latex_tools=_ok_tools,
                      probe_models=probe_models)

    def test_probe_models_accepts_latest_tag_suffixes(self):
        # 钉住的破坏：required 名与 ollama 的 :latest 后缀 id 对不上（归一化匹配）。
        def _fake_urlopen(_url, timeout=0):
            class _Resp:
                def read(self):
                    return json.dumps({"object": "list", "data": [
                        {"id": "openbmb/minicpm-v4.7:latest"},
                        {"id": "minicpm-ocr:latest"}]}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

            return _Resp()

        models = probe_models(DEAD, ("openbmb/minicpm-v4.7", "minicpm-ocr"), urlopen=_fake_urlopen)
        self.assertEqual(models, ["openbmb/minicpm-v4.7:latest", "minicpm-ocr:latest"])

    def test_probe_models_rejects_unserved_model_name(self):
        # 钉住的破坏：子串匹配放行「端点不服务该名字」（如 minicpm-v4.7 ≠ minicpm-v4.7-35b-a3b-q4）。
        def _fake_urlopen(_url, timeout=0):
            class _Resp:
                def read(self):
                    return json.dumps({"object": "list", "data": [{"id": "minicpm-v4.7:latest"}]}).encode()

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

            return _Resp()

        with self.assertRaises(PreflightError) as ctx:
            probe_models(DEAD, ("minicpm-v4.7-35b-a3b-q4",), urlopen=_fake_urlopen)
        self.assertIn("minicpm-v4.7-35b-a3b-q4", str(ctx.exception))


class WriteEvidenceTests(unittest.TestCase):
    def test_write_evidence_emits_json_and_summary(self):
        results = [{"id": "E2E-1", "passed": True, "detail": "ok", "elapsed_seconds": 1.0}]
        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = write_evidence(results, Path(tmp))
            parsed = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["results"], results)
            self.assertTrue(parsed["all_passed"])
            summary = md_path.read_text(encoding="utf-8")
            self.assertIn("E2E-1", summary)
            self.assertIn("全部通过", summary)

    def test_write_evidence_verdict_reflects_failures(self):
        results = [{"id": "E2E-2", "passed": False, "detail": "模型未落稿", "elapsed_seconds": 2.0}]
        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = write_evidence(results, Path(tmp))
            self.assertFalse(json.loads(json_path.read_text(encoding="utf-8"))["all_passed"])
            self.assertIn("未通过", md_path.read_text(encoding="utf-8"))


class MakeCallTests(unittest.TestCase):
    """make_call 的真实边界契约：POST JSON、token 查询串、二进制响应。"""

    def setUp(self):
        outer = self
        self.received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                outer.received["path"] = self.path
                outer.received["body"] = self.rfile.read(length)
                payload = json.dumps({"tag": "live-x"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                outer.received["path"] = self.path
                pdf = b"%PDF-1.7 fixture"
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(pdf)))
                self.end_headers()
                self.wfile.write(pdf)

            def log_message(self, *_args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.call = make_call(f"http://127.0.0.1:{self.port}", "sekret")
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_make_call_posts_json_and_sends_token(self):
        result = self.call("/api/studio/preview", {"name": "a.tex", "content": "x"})
        self.assertEqual(result, {"tag": "live-x"})
        self.assertIn("token=sekret", self.received["path"])
        self.assertEqual(json.loads(self.received["body"]), {"name": "a.tex", "content": "x"})

    def test_make_call_returns_bytes_for_binary_responses(self):
        pdf = self.call("/api/studio/pdf/a.tex/live-x")
        self.assertEqual(pdf, b"%PDF-1.7 fixture")
        self.assertIn("token=sekret", self.received["path"])


class E2E1CompileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.fixture_dir = Path(tmp.name)
        self.content = "\\documentclass{article}\n\\begin{document}\n$x^2+1$\n\\end{document}\n"
        (self.fixture_dir / "paper.tex").write_text(self.content, encoding="utf-8")

    def test_compile_scenario_passes_when_pdf_comes_back(self):
        outer = self

        def call(path, payload=None):
            if path == "/api/studio/preview":
                outer.assertEqual(payload["name"], "paper.tex")
                outer.assertEqual(payload["content"], outer.content)
                return {"tag": "live-x"}
            if path == "/api/studio/pdf/paper.tex/live-x":
                return b"%PDF-1.7 fixture"
            outer.fail(f"unexpected path {path}")

        result = run_e2e1_compile(call, self.fixture_dir)
        self.assertTrue(result["passed"])
        self.assertEqual(result["id"], "E2E-1")
        self.assertEqual(sorted(result), ["detail", "elapsed_seconds", "id", "passed"])

    def test_compile_scenario_fails_when_pdf_missing(self):
        def call(path, payload=None):
            return {"tag": "live-x"} if path == "/api/studio/preview" else b""

        result = run_e2e1_compile(call, self.fixture_dir)
        self.assertFalse(result["passed"])
        self.assertIn("no pdf", result["detail"])

    def test_compile_scenario_fails_on_non_pdf_bytes(self):
        def call(path, payload=None):
            return {"tag": "live-x"} if path == "/api/studio/preview" else b"<html>error</html>"

        result = run_e2e1_compile(call, self.fixture_dir)
        self.assertFalse(result["passed"])


class E2E2RepairTests(unittest.TestCase):
    """修复场景四判据：job 完成、落稿编辑（哈希变化）、复核全绿、NEEDS_HUMAN/失败=不过。"""

    MODEL = "minicpm-v4.7-35b-a3b-q4"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.case_path = Path(tmp.name) / "smoke_cases.json"
        self.case_path.write_text(json.dumps({"cases": [
            {"id": "S01", "case_kind": "control", "original_latex": "x+1"},
            {"id": "S02", "case_kind": "injected", "original_latex": "a_+b",
             "reference_latex": "a_1+b"},
        ]}), encoding="utf-8")

    @staticmethod
    def _result(**overrides):
        original = r"\left(\frac{x^2-1}{x-1}"
        repaired = original + r"\right)"
        result = {"fixed_content": ("\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n"
                                    + "$" + repaired + "$.\n$a_+b$.\n\\end{document}\n"),
                  "edits": [{"line": 4, "before": original, "after": repaired, "skill": "doc-formula-verify"}],
                  "compile_before": {"ok": False}, "compile_after": {"ok": True},
                  "problems_after": [{"status": "NEEDS_HUMAN", "repair_blocker": "missing_script_operand"}],
                  "model": E2E2RepairTests.MODEL,
                  "configured_model": E2E2RepairTests.MODEL, "model_calls": 0,
            "original_sha256": "00", "candidate_sha256": "11"}
        result.update(overrides)
        return result

    def _run(self, *, result=None, jobs_entry=None, analyze_problems=None):
        outer = self
        analyze_problems = (analyze_problems if analyze_problems is not None
                            else [{"id": "f-003-1", "type": "formula", "status": "RETRY"}])
        jobs_entry = jobs_entry or {"id": "j1", "done": True, "error": None}
        result = result if result is not None else self._result()

        def call(path, payload=None):
            if path == "/api/studio/analyze":
                return {"problems": analyze_problems, "summary": {"formula": 1, "table": 0}}
            if path == "/api/studio/fix":
                outer.assertEqual(payload["name"], "S02.tex")
                outer.assertIn("a_+b", payload["content"])
                return {"job": "j1"}
            if path == "/api/studio/jobs":
                return {"jobs": [jobs_entry]}
            if path == "/api/studio/fixstatus?id=j1":
                return {"done": True, "result": result, "error": None}
            outer.fail(f"unexpected path {path}")

        return run_e2e2_repair(call, self.case_path)

    def test_repair_scenario_passes_all_four_criteria(self):
        out = self._run()
        self.assertTrue(out["passed"])
        self.assertEqual(out["id"], "E2E-2")
        self.assertEqual(sorted(out), ["detail", "elapsed_seconds", "id", "passed"])
        self.assertIn("repair_model=" + self.MODEL, out["detail"])
        self.assertIn("S02", out["detail"])

    def test_repair_scenario_fails_on_needs_human(self):
        out = self._run(result=self._result(
            problems_after=[{"id": "f-1", "type": "formula", "status": "NEEDS_HUMAN"}]))
        self.assertFalse(out["passed"])
        self.assertIn("缺下标", out["detail"])

    def test_repair_scenario_fails_on_job_error(self):
        out = self._run(jobs_entry={"id": "j1", "done": True, "error": "任务失败（RuntimeError）"})
        self.assertFalse(out["passed"])
        self.assertIn("RuntimeError", out["detail"])

    def test_repair_scenario_fails_without_landed_edit(self):
        out = self._run(result=self._result(edits=[], original_sha256="00", candidate_sha256="00"))
        self.assertFalse(out["passed"])

    def test_repair_scenario_fails_when_analyze_finds_no_problem(self):
        out = self._run(analyze_problems=[])
        self.assertFalse(out["passed"])
        self.assertIn("analyze", out["detail"])


class E2E3OcrTests(unittest.TestCase):
    """E2E-3 两段式：真 OCR 记录 → 复核门 → 布局。

    抓什么：① OCR 记录必须 status=OK 且带非空 lines（含记录级门：
    review_items 空、output_complete 真）才进布局段；② 复核门不可跳过
    （无 review 只出模板不出布局）；③ 布局必须绑定记录哈希且带
    formula/table/text 节点；④ NEEDS_HUMAN 记录直接不过、不得出布局。
    段 1 的模型子进程以 canned 输出替代（慢/外部）；段 2 跑真实
    ocr_to_layout.py（本地快）。
    """

    RECORD = {
        "id": "e2e3", "status": "OK", "reason": "", "model": "minicpm-ocr",
        "lines": ["Kinetic energy $E$ is", "\\(x^2+1\\)", "a | b | c", "1 | 2 | 3"],
        "review_items": [], "output_complete": True,
    }

    def _fake(self, record):
        stdout = json.dumps(record, ensure_ascii=False) + "\n"
        calls = []

        def runner(image, model, base):
            calls.append((Path(image).name, model, base))
            return 0, stdout

        return runner, calls

    def test_ok_record_produces_hash_bound_layout(self):
        runner, calls = self._fake(self.RECORD)
        out = run_e2e3_ocr(Path("samples/ocr"), run_ocr=runner)
        self.assertTrue(out["passed"], out)
        for name in ("ocr_status_ok", "review_gate_enforced", "layout_emitted",
                     "layout_bound_to_source", "no_pending_blockers"):
            self.assertTrue(out["criteria"][name], (name, out))
        self.assertEqual(out["layout"]["node_types"], ["formula", "table", "text"])
        self.assertEqual(calls[0][1], "minicpm-ocr:latest")
        # 抓回退点：ocr_extract 的 base 约定是服务器根（path 自带 /v1），
        # /v1 后缀必须被剥掉，否则拼成 /v1/v1/… 秒 404（2026-11-12 实跑教训）。
        self.assertEqual(calls[0][2], "http://127.0.0.1:11434")

    def test_needs_human_record_fails_without_layout(self):
        record = {"id": "e2e3", "status": "NEEDS_HUMAN", "reason": "bad_response_json",
                  "model": "minicpm-ocr", "review_items": [{"reason": "bad_response_json", "scope": "record"}],
                  "output_complete": False}
        runner, _ = self._fake(record)
        out = run_e2e3_ocr(Path("samples/ocr"), run_ocr=runner)
        self.assertFalse(out["passed"])
        self.assertFalse(out["criteria"]["ocr_status_ok"])
        self.assertFalse(out["criteria"]["layout_emitted"])


class E2E4PersistenceTests(unittest.TestCase):
    """E2E-4 持久化：写过 → 新后端读回 → 哈希一致。

    抓什么：防假绿两点——① 必须调用工厂两次（第二次是新后端进程读回，
    同进程读回不算数）；② 读回内容必须与写入逐字节一致、哈希跨进程一致，
    不一致即不过（防「只写不读」和「读回错内容也绿」）。
    """

    def _factory(self, tamper=None):
        store = {}
        calls = []

        def factory():
            def call(path, payload=None):
                if path.startswith("/api/studio/save"):
                    store["content"] = payload["content"]
                    store["name"] = payload["name"]
                    return {"ok": True, "sha256": hashlib.sha256(payload["content"].encode()).hexdigest()}
                if path.startswith("/api/studio/file"):
                    content = tamper(store["content"]) if tamper else store["content"]
                    return {"name": store["name"], "content": content,
                            "sha256": hashlib.sha256(content.encode()).hexdigest()}
                raise AssertionError(f"意外端点：{path}")
            calls.append(call)
            return call

        return factory, calls

    def test_write_then_new_backend_readback_passes(self):
        factory, calls = self._factory()
        out = run_e2e4_persistence(factory)
        self.assertTrue(out["passed"], out)
        self.assertEqual(len(calls), 2)  # 防假绿：工厂必须被调两次（两次新后端）
        for name in ("write_ok", "read_back_matches", "hash_consistent", "cross_restart"):
            self.assertTrue(out["criteria"][name], (name, out))

    def test_readback_mismatch_fails(self):
        factory, _ = self._factory(tamper=lambda content: content + "tampered\n")
        out = run_e2e4_persistence(factory)
        self.assertFalse(out["passed"])
        self.assertFalse(out["criteria"]["read_back_matches"])
        self.assertFalse(out["criteria"]["hash_consistent"])


class E2E5AppSmokeTests(unittest.TestCase):
    """E2E-5 .app 冒烟：nodeinfo 200 → SIGTERM → 5s 内 code=0（#50 行为契约）。

    抓什么：① SIGTERM 后必须在 5 秒内退出（超时即不过——#50 回归的发行面）；
    ② 退出码必须 0（crash 不算过）；③ nodeinfo 不通不得冒充通过。
    popen 假件 + ready_probe 注入（慢/外部替代）；session.json 发现走真逻辑。
    """

    def _run(self, *, returncode=0, hang=False, ready=True):
        state = Path(tempfile.mkdtemp(prefix="e2e5-test-"))
        procs = []

        class FakeProc:
            returncode = None
            sent = None
            killed = False

            def send_signal(self, sig):
                self.sent = sig

            def wait(self, timeout=None):
                if hang:
                    raise subprocess.TimeoutExpired("app", timeout)
                self.returncode = returncode
                return returncode

            def kill(self):
                self.killed = True

        def factory(argv, **kwargs):
            (state / "session.json").write_text(json.dumps({
                "url": "http://127.0.0.1:18199/studio?token=tok",
                "base_url": "http://127.0.0.1:18199", "running": True}))
            proc = FakeProc()
            procs.append(proc)
            return proc

        out = smoke_app(Path("/fake/TeXada Studio.app"), timeout=1.0,
                        popen_factory=factory,
                        ready_probe=lambda base, token: ready,
                        state_dir=state)
        return out, procs

    def test_sigterm_bounded_graceful_exit_passes(self):
        out, procs = self._run()
        self.assertTrue(out["passed"], out)
        for name in ("app_launched", "nodeinfo_ready", "sigterm_bounded_exit", "graceful_exit_code"):
            self.assertTrue(out["criteria"][name], (name, out))
        self.assertIsNotNone(procs[0].sent)  # 必须真的发过 SIGTERM

    def test_hang_after_sigterm_fails(self):
        out, procs = self._run(hang=True)
        self.assertFalse(out["passed"])
        self.assertFalse(out["criteria"]["sigterm_bounded_exit"])
        self.assertFalse(out["criteria"]["graceful_exit_code"])
        self.assertTrue(procs[0].killed)  # 超时后必须杀掉，不留悬挂进程

    def test_nonzero_exit_fails(self):
        out, _ = self._run(returncode=1)
        self.assertFalse(out["passed"])
        self.assertTrue(out["criteria"]["sigterm_bounded_exit"])
        self.assertFalse(out["criteria"]["graceful_exit_code"])

    def test_nodeinfo_not_ready_fails(self):
        out, _ = self._run(ready=False)
        self.assertFalse(out["passed"])
        self.assertFalse(out["criteria"]["nodeinfo_ready"])


if __name__ == "__main__":
    unittest.main()
