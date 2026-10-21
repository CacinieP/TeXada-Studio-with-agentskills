"""Selection precedes loading, applicability gates bodies, and UI flags stay independent."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from test_static_assets import ROOT, studio
from test_planner import ScriptedProvider
from docforensics.planner import ConstrainedPlanner, PlannerBudget
from docforensics.skill_selection import load_catalog, load_selected_skill, validate_selection
from docforensics.vlm import OpenAICompatibleProvider


class SelectingFixture(ScriptedProvider):
    def __init__(self, choice="appropriate"):
        super().__init__()
        self.choice = choice
        self.loaded = []
        self.plan_calls = 0

    def select_skill(self, snapshot, *, timeout=120):
        self.last_trace = {"model_calls": 0, "reason": "offline_fixture_selection"}
        selected = self.choice
        if selected == "appropriate":
            selected = next(c["skill_id"] for c in snapshot["catalog"] if c["node_kind"] == snapshot["node"]["kind"])
        return {"skill_id": selected, "state_rev": snapshot["state_rev"], "reason": "fixture route"}

    def plan_action(self, *args, **kwargs):
        self.plan_calls += 1
        return super().plan_action(*args, **kwargs)

    def repair_formula(self, node, *, timeout=120, loaded_skill=None):
        self.loaded.append(loaded_skill)
        return super().repair_formula(node, timeout=timeout)


class SkillSelectionTest(unittest.TestCase):
    def test_catalog_reads_metadata_without_loading_bodies(self):
        with patch("docforensics.skill_selection._read_skill", side_effect=AssertionError("body read is forbidden")):
            catalog = load_catalog()
        self.assertEqual(set(catalog), {"doc-formula-verify", "doc-table-audit"})
        for name, capability in catalog.items():
            self.assertEqual(capability.version, "1.0.0")
            self.assertEqual(capability.metadata_sha256, hashlib.sha256((ROOT / "skills" / name / "capability.json").read_bytes()).hexdigest())
        node = {"kind": "formula", "latex": "x+"}
        for choice, reason in (("doc-table-audit", "skill_not_applicable"), ("ocr-layout", "skill_not_allowed"), (None, "selection_declined")):
            self.assertEqual(validate_selection({"skill_id": choice, "state_rev": 2, "reason": "test"}, node, 2, catalog)[1], reason)
        self.assertEqual(validate_selection({"skill_id": "doc-formula-verify", "state_rev": True, "reason": "test"}, node, 2, catalog)[1], "stale_selection")
        self.assertEqual(validate_selection({"skill_id": [], "state_rev": 2, "reason": "test"}, node, 2, catalog)[1], "skill_not_allowed")

    def test_body_version_and_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("doc-formula-verify", "doc-table-audit"):
                shutil.copytree(ROOT / "skills" / name, root / name)
            catalog = load_catalog(root)
            for name in catalog:
                loaded = load_selected_skill(catalog[name], skill_root=root)
                self.assertEqual(loaded.sha256, hashlib.sha256((root / name / "SKILL.md").read_bytes()).hexdigest())
                self.assertIsNotNone(loaded.checker_sha256)
            body = root / "doc-formula-verify" / "SKILL.md"
            body.write_text(body.read_text().replace("version: 1.0.0", "version: 2.0.0"))
            with self.assertRaisesRegex(ValueError, "skill_version_mismatch"):
                load_selected_skill(catalog["doc-formula-verify"], skill_root=root)
            body.unlink()
            body.symlink_to(ROOT / "skills" / "doc-formula-verify" / "SKILL.md")
            with self.assertRaisesRegex(ValueError, "skill_path_escape"):
                load_selected_skill(catalog["doc-formula-verify"], skill_root=root)

    def test_unknown_metadata_capability_and_arbitrary_schema_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("doc-formula-verify", "doc-table-audit"):
                shutil.copytree(ROOT / "skills" / name, root / name)
            path = root / "doc-table-audit" / "capability.json"
            original = json.loads(path.read_text())
            for updates in ({"capability": "ocr"}, {"supported_actions": ["execute-code"]}, {"schema_version": True}, {"input_schema": {}}):
                path.write_text(json.dumps({**original, **updates}))
                with self.assertRaises(ValueError):
                    load_catalog(root)

    def test_declined_wrong_and_unknown_skills_never_load_or_execute(self):
        for choice in (None, "doc-table-audit", "untrusted-path"):
            events = []
            with self.subTest(choice=choice), patch("docforensics.skill_selection.load_selected_skill") as load, \
                    patch.object(studio, "_verify_formula", side_effect=AssertionError("checker must not run")):
                candidate, edits, report = studio._apply_planned_fixes("$x+$", [], provider=SelectingFixture(choice),
                            emit=lambda action, **fields: events.append({"action": action, **fields}),
                            skill_selection=True, use_model_planner=False)
                load.assert_not_called()
            self.assertEqual(candidate, "$x+$")
            self.assertFalse(edits)
            self.assertEqual(report["selection_rejections"], 1)
            self.assertEqual(report["nodes"][0]["state"], "human")
            self.assertFalse(any(e["action"] == "SKILL_LOADED" for e in events))

    def test_no_applicable_and_missing_catalog_are_visible_without_model_call(self):
        provider = SelectingFixture()
        provider.select_skill = Mock(side_effect=AssertionError("no applicable capability"))
        events = []
        host = ConstrainedPlanner("untrusted", [{"id": "image", "kind": "image", "line": 1}], provider,
                                  Mock(), Mock(), lambda action, **fields: events.append({"action": action, **fields}),
                                  skill_selection=True, catalog=load_catalog(), use_model_planner=False)
        _, report = host.run()
        self.assertEqual(report["nodes"][0]["human_reason"], "no_applicable_skill")
        self.assertEqual(report["reserved_model_calls"], 0)
        with patch.object(studio, "load_catalog", side_effect=ValueError("bad metadata")):
            candidate, _, report = studio._apply_planned_fixes("$x+$", [], provider=provider,
                         emit=lambda action, **fields: events.append({"action": action, **fields}), skill_selection=True)
        self.assertEqual(candidate, "$x+$")
        self.assertTrue(any(e.get("reason") == "catalog_unavailable" for e in events))

    def test_independent_fixed_selection_routes_then_loads_exact_body(self):
        events = []
        provider = SelectingFixture()
        with patch.object(studio, "_verify_formula", side_effect=lambda value: {"status": "OK" if value == "x+1" else "RETRY"}):
            candidate, edits, report = studio._apply_planned_fixes("$x+$", [], provider=provider,
                            emit=lambda action, **fields: events.append({"action": action, **fields}),
                            skill_selection=True, use_model_planner=False)
        self.assertEqual(candidate, "$x+1$")
        self.assertEqual(provider.plan_calls, 0)
        self.assertEqual(report["mode"], "fixed-skill-selection")
        self.assertEqual(report["reserved_model_calls"], 2)  # One selection, one repair.
        self.assertEqual(len(provider.loaded), 1)
        self.assertEqual(provider.loaded[0].name, "doc-formula-verify")
        actions = [event["action"] for event in events]
        self.assertLess(actions.index("SKILL_SELECTED"), actions.index("SKILL_LOADED"))
        self.assertLess(actions.index("SKILL_LOADED"), actions.index("CHECK"))
        self.assertEqual(report["loaded_skills"][0]["body_sha256"], provider.loaded[0].sha256)
        self.assertTrue(edits)

    def test_selection_shares_model_budget_with_planner_and_repairs(self):
        host = ConstrainedPlanner("$x+$", [{"id": "f-1", "kind": "formula", "latex": "x+", "line": 1}],
                                  SelectingFixture(), Mock(return_value={"status": "RETRY"}), Mock(),
                                  skill_selection=True, catalog=load_catalog(), budget=PlannerBudget(max_model_calls=1))
        _, report = host.run()
        self.assertEqual(report["selection_calls"], 1)
        self.assertEqual(report["reserved_model_calls"], 1)
        self.assertEqual(report["executed"], 0)
        self.assertEqual(report["nodes"][0]["state"], "human")
        host.check.assert_not_called()

    def test_selected_table_body_is_loaded_without_formula_or_ocr_model(self):
        content = "\\begin{tabular}{lr}\nItem & Value \\\\\nA & 2 \\\\\nTotal & 3 \\\\\n\\end{tabular}\n"
        provider = SelectingFixture()
        provider.repair_formula = Mock(side_effect=AssertionError("formula call is forbidden"))
        candidate, _, report = studio._apply_planned_fixes(content, [], provider=provider,
                        emit=lambda *args, **kwargs: None, skill_selection=True, use_model_planner=False)
        self.assertIn("Total & 2", candidate)
        self.assertEqual(report["loaded_skills"][0]["skill_id"], "doc-table-audit")
        self.assertEqual(report["reserved_model_calls"], 1)
        provider.repair_formula.assert_not_called()

    def test_selected_formula_body_reaches_actual_sdk_prompt_only_after_loading(self):
        with patch("docforensics.vlm.load_skill", side_effect=AssertionError("eager body loading")):
            provider = studio._new_provider(skill_selection=True)
        self.assertIsNone(provider.skill)
        loaded = load_selected_skill(load_catalog()["doc-formula-verify"])
        response = {"choices": [{"message": {"content": json.dumps({"latex": "x+1"})}}]}
        with patch("docforensics.vlm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as network:
            self.assertEqual(provider.repair_formula({"data": {"latex": "x+"}}, loaded_skill=loaded), "x+1")
        payload = json.loads(network.call_args.args[0].data)
        self.assertIn(loaded.instructions, payload["messages"][0]["content"])
        self.assertEqual(payload["model"], studio.VLM_MODEL)
        self.assertEqual(provider.last_trace["skill_sha256"], loaded.sha256)
        self.assertEqual(provider.last_trace["skill_mode"], "selected")
        with patch("docforensics.vlm.urllib.request.urlopen") as network:
            self.assertIsNone(provider.repair_formula({"data": {"latex": "x+"}}, loaded_skill=load_selected_skill(load_catalog()["doc-table-audit"])))
        network.assert_not_called()

    def test_selection_sdk_uses_catalog_only_and_counts_failed_attempts(self):
        provider = OpenAICompatibleProvider("http://localhost:9000/v1", "MiniCPM-V-4.7-1B")
        snapshot = {"state_rev": 3, "node": {"kind": "formula"}, "catalog": [cap.public() for cap in load_catalog().values()]}
        proposal = {"skill_id": "doc-formula-verify", "state_rev": 3, "reason": "formula"}
        response = {"choices": [{"message": {"content": json.dumps(proposal)}}]}
        with patch("docforensics.vlm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as network:
            self.assertEqual(provider.select_skill(snapshot, timeout=6), proposal)
        payload = json.loads(network.call_args.args[0].data)
        self.assertEqual(payload["model"], "MiniCPM-V-4.7-1B")
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(json.loads(payload["messages"][-1]["content"]), snapshot)
        self.assertNotIn("instructions", payload["messages"][-1]["content"])
        self.assertEqual(network.call_args.kwargs["timeout"], 6)
        self.assertEqual(provider.last_trace["model_calls"], 1)
        with patch("docforensics.vlm.urllib.request.urlopen", side_effect=TimeoutError("private detail")):
            self.assertIsNone(provider.select_skill(snapshot))
        self.assertEqual(provider.last_trace["model_calls"], 1)
        self.assertEqual(provider.last_trace["reason"], "timeout")
        self.assertNotIn("private detail", json.dumps(provider.last_trace))

    def test_declined_selection_job_preserves_original_without_late_checker(self):
        job_id = "8" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None, "skill_selection": True}}, clear=True), \
                patch.object(studio, "_new_provider", return_value=SelectingFixture(None)), \
                patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                patch.object(studio, "_verify_formula", side_effect=AssertionError("declined tools must stay unexecuted")) as checker:
            studio._studio_job("input.tex", "$x+$", job_id)
            result = studio._read_job(job_id)["result"]
        checker.assert_not_called()
        self.assertEqual(result["fixed_content"], "$x+$")
        self.assertEqual(result["problems_after"][0]["reason"], "selection_declined")
        self.assertTrue(any(e["action"] == "HUMAN_REQUESTED" for e in result["trace"]))

    def test_api_freezes_independent_flags_and_persists_selection_result(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, clear=True), patch.object(studio, "_new_provider", return_value=SelectingFixture()) as factory, \
                patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                patch.object(studio, "_verify_formula", side_effect=lambda value: {"status": "OK" if value == "x+1" else "RETRY"}), \
                TestClient(studio.app) as client, patch.object(studio.threading, "Thread") as thread:
            for value in ("on", 1, None):
                response = client.post("/api/studio/fix", params={"token": studio.TOKEN},
                                       json={"name": "input.tex", "content": "$x+$", "skill_selection": value})
                self.assertEqual(response.status_code, 400)
            response = client.post("/api/studio/fix", params={"token": studio.TOKEN},
                                   json={"name": "input.tex", "content": "$x+$", "skill_selection": True, "planner_mode": False})
            thread.call_args.kwargs["target"](*thread.call_args.kwargs["args"])
            result = studio._read_job(response.json()["job"])["result"]
            self.assertTrue(result["skill_selection"])
            self.assertFalse(result["planner_mode"])
            self.assertEqual(result["skill_mode"], "selected")
            self.assertEqual(result["fixed_content"], "$x+1$")
            factory.assert_called_once_with(skill_selection=True)
            self.assertTrue(any(e["action"] == "SKILL_LOADED" for e in result["trace"]))


if __name__ == "__main__":
    unittest.main()
