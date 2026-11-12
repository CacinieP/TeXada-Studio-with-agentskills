"""E2E 发行驱动的预检与证据写盘契约测试；不依赖宿主环境（CI 为 ubuntu 无 .venv/tectonic）。"""
import json
from pathlib import Path
import tempfile
import unittest

from e2e_release_check import (
    PreflightError,
    preflight,
    probe_latex_tools,
    probe_python,
    probe_models,
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


if __name__ == "__main__":
    unittest.main()
