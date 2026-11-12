"""E2E 发行驱动的预检与证据写盘契约测试；不依赖宿主环境（CI 为 ubuntu 无 .venv/tectonic）。"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
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
        # 钉住的破坏：required 名单匹配不上 ollama 的 :latest 后缀 id。
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

        models = probe_models(DEAD, urlopen=_fake_urlopen)
        self.assertEqual(models, ["openbmb/minicpm-v4.7:latest", "minicpm-ocr:latest"])


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


if __name__ == "__main__":
    unittest.main()
