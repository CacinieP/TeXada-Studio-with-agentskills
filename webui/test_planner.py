"""Host adversarial boundaries and product-path planner tests; no external API."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from test_static_assets import studio
from docforensics.planner import ConstrainedPlanner, PlannerBudget
from docforensics.vlm import OpenAICompatibleProvider


class ScriptedProvider:
    name = "fixture"

    def __init__(self, illegal=False):
        self.last_trace = {}
        self.illegal = illegal

    def fingerprint(self):
        return {"provider": "fixture"}

    def plan_action(self, snapshot, *, timeout=120):
        self.last_trace = {"model_calls": 0, "reason": "offline_fixture"}
        node = next(n for n in snapshot["nodes"] if n["action_mask"])
        if self.illegal:
            self.illegal = False
            action = "run-shell"
        else:
            action = node["action_mask"][0]
        return {"action": action, "node_id": node["id"], "state_rev": snapshot["state_rev"],
                "params": {"reason": "uncertain"} if action == "request-human" else {}}

    def repair_formula(self, node, *, timeout=120):
        self.last_trace = {"model_calls": 0, "reason": "offline_fixture"}
        return "x+1"


class PlannerTest(unittest.TestCase):
    def make_host(self, **kwargs):
        self.check, self.repair = Mock(return_value={"status": "RETRY"}), Mock(return_value={"accepted": False})
        self.events = []
        return ConstrainedPlanner("$x+$", [{"id": "f-001-1", "kind": "formula", "line": 1}],
                                  ScriptedProvider(), self.check, self.repair,
                                  lambda action, **fields: self.events.append({"action": action, **fields}), **kwargs)

    def test_bad_actions_never_reach_check_or_repair(self):
        good = {"action": "check-formula", "node_id": "f-001-1", "state_rev": 0, "params": {}}
        mutations = [{"action": "run-shell"}, {"node_id": "outside"}, {"state_rev": -1}, {"state_rev": True},
                     {"action": "check-table"}, {"action": "propose-repair"}, {"params": {"code": "danger"}},
                     {"params": []}, {"unexpected": "field"}]
        host = self.make_host()
        for change in mutations:
            with self.subTest(change=change):
                self.assertFalse(host.execute({**good, **change}))
        self.assertFalse(host.execute(None))
        self.check.assert_not_called()
        self.repair.assert_not_called()
        self.assertEqual(host.state_rev, 0)
        self.assertEqual(host.rejected, 10)
        self.assertEqual([e["action"] for e in self.events], ["PLANNER_PROPOSED", "PLANNER_REJECTED"] * 10)

    def test_checked_state_and_revision_bind_repair(self):
        host = self.make_host()
        self.assertTrue(host.execute({"action": "check-formula", "node_id": "f-001-1", "state_rev": 0, "params": {}}))
        self.assertEqual(host.snapshot()["nodes"][0]["action_mask"], ["propose-repair", "request-human"])
        self.assertFalse(host.execute({"action": "propose-repair", "node_id": "f-001-1", "state_rev": 0, "params": {}}))
        self.repair.assert_not_called()
        self.assertTrue(host.execute({"action": "propose-repair", "node_id": "f-001-1", "state_rev": 1, "params": {}}))
        self.repair.assert_called_once()
        self.assertEqual(host.model_calls, 1)

    def test_model_and_time_budget_stop_before_execution(self):
        host = self.make_host(budget=PlannerBudget(max_steps=2, max_model_calls=1))
        host.run()
        self.assertEqual(host.steps, 1)
        self.assertEqual(host.model_calls, 1)
        self.repair.assert_not_called()
        self.assertEqual(host.nodes[0]["state"], "human")
        host = self.make_host(clock=lambda: 300)
        host.started = 0
        self.assertFalse(host.execute({"action": "check-formula", "node_id": "f-001-1", "state_rev": 0, "params": {}}))
        self.check.assert_not_called()

    def test_environment_error_masks_repair_and_requests_human(self):
        host = self.make_host()
        self.check.return_value = {"status": "NEEDS_ENV"}
        _, report = host.run()
        self.repair.assert_not_called()
        self.assertEqual(report["nodes"][0]["state"], "human")
        self.assertEqual(report["executed"], 2)

    def test_repeated_illegal_decisions_are_bounded(self):
        host = self.make_host(budget=PlannerBudget(max_steps=3))
        host.provider.plan_action = lambda snapshot, **kwargs: {"action": "exec", "node_id": "f-001-1", "state_rev": 0, "params": {}}
        _, report = host.run()
        self.assertEqual((report["steps"], report["rejected"], report["executed"]), (3, 3, 0))
        self.check.assert_not_called()
        self.assertEqual(report["nodes"][0]["state"], "human")

    def test_real_sdk_surface_uses_same_checkpoint_and_strict_json(self):
        provider = OpenAICompatibleProvider("http://localhost:9000/v1", "MiniCPM-V-4.7-1B")
        proposal = {"action": "request-human", "node_id": "f-1", "state_rev": 0, "params": {"reason": "uncertain"}}
        response = {"choices": [{"message": {"content": json.dumps(proposal)}}]}
        with patch("docforensics.vlm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as network:
            self.assertEqual(provider.plan_action({"state_rev": 0}, timeout=7), proposal)
        payload = json.loads(network.call_args.args[0].data)
        self.assertEqual(payload["model"], "MiniCPM-V-4.7-1B")
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(len(payload["messages"]), 2)
        self.assertNotIn("loaded_skill", payload["messages"][0]["content"])
        self.assertEqual(network.call_args.kwargs["timeout"], 7)
        self.assertEqual(provider.last_trace["model_calls"], 1)
        for content in ('{"action":"a","action":"b"}', '```json\n{}\n```', '[]', '{"a":NaN}'):
            response["choices"][0]["message"]["content"] = content
            with patch("docforensics.vlm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                self.assertIsNone(provider.plan_action({"state_rev": 0}))

    def test_escaped_credential_echo_in_decoded_json_never_reaches_host_audit(self):
        credential = "review-inert-secret"
        provider = OpenAICompatibleProvider("http://localhost:9000/v1", "MiniCPM-V-4.7-1B")
        provider._api_key = credential
        records = [
            {"action": "request-human", "node_id": "f-001-1", "state_rev": 0, "params": {"reason": credential}},
            {"nested": [{credential: "value"}]},
            {"nested": ["prefix " + credential + " suffix"]},
        ]
        for record in records:
            serialized = json.dumps(record).replace(credential, "".join("\\u%04x" % ord(char) for char in credential))
            response = {"choices": [{"message": {"content": serialized}}]}
            with self.subTest(record=record), patch("docforensics.vlm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                self.assertIsNone(provider.plan_action({"state_rev": 0}))
            self.assertEqual(provider.last_trace["reason"], "credential_in_response")
            self.assertEqual(provider.last_trace["raw_candidate_response"], "[redacted credential response]")
            self.assertNotIn(credential, json.dumps(provider.last_trace))
            self.assertNotIn("\\u0072", provider.last_trace["raw_candidate_response"])
        content = json.dumps(records[0]).replace(credential, "".join("\\u%04x" % ord(char) for char in credential))
        response = {"choices": [{"message": {"content": content}}]}
        host = self.make_host(budget=PlannerBudget(max_steps=1))
        host.provider = provider
        with patch("docforensics.vlm.urllib.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            _, report = host.run()
        self.assertEqual(report["executed"], 0)
        self.assertNotIn(credential, json.dumps(self.events))
        self.assertNotIn(credential, json.dumps(report))

    def test_provider_late_return_never_starts_candidate_checker(self):
        clock, observed, events = [0.0], [], []
        provider = ScriptedProvider()
        def late_repair(*args, **kwargs):
            clock[0] = 2.0
            return "x+1"
        provider.repair_formula = late_repair
        def factory(*args, **kwargs):
            return ConstrainedPlanner(*args, **kwargs, budget=PlannerBudget(seconds=1), clock=lambda: clock[0])
        def check(latex):
            observed.append((clock[0], latex))
            return {"status": "OK" if latex == "x+1" else "RETRY"}
        with patch.object(studio, "ConstrainedPlanner", side_effect=factory), patch.object(studio, "_verify_formula", side_effect=check):
            candidate, edits, report = studio._apply_planned_fixes("$x+$", [], provider=provider,
                                    emit=lambda action, **fields: events.append({"action": action, **fields}))
        self.assertEqual(observed, [(0.0, "x+")])
        self.assertEqual(candidate, "$x+$")
        self.assertFalse(edits)
        self.assertEqual(report["nodes"][0]["state"], "human")
        self.assertFalse(any(event["action"] == "CANDIDATE_ACCEPTED" for event in events))
        self.assertTrue(any(event.get("reason") == "planner_deadline_exhausted" for event in events))

    def test_checker_late_return_is_audited_without_accepting_edits(self):
        clock, events = [0.0], []
        def factory(*args, **kwargs):
            return ConstrainedPlanner(*args, **kwargs, budget=PlannerBudget(seconds=1), clock=lambda: clock[0])
        def check(latex):
            if latex == "x+1":
                clock[0] = 2.0
                return {"status": "OK"}
            return {"status": "RETRY"}
        with patch.object(studio, "ConstrainedPlanner", side_effect=factory), patch.object(studio, "_verify_formula", side_effect=check):
            candidate, edits, report = studio._apply_planned_fixes("$x+$", [], provider=ScriptedProvider(),
                                    emit=lambda action, **fields: events.append({"action": action, **fields}))
        self.assertEqual(candidate, "$x+$")
        self.assertFalse(edits)
        self.assertEqual(report["nodes"][0]["state"], "human")
        self.assertTrue(any(event["action"] == "CANDIDATE_CHECK" and event["check"]["status"] == "OK" for event in events))
        self.assertFalse(any(event["action"] == "CANDIDATE_ACCEPTED" for event in events))

    def test_generic_host_discards_late_callback_edits_and_stops_after_late_check(self):
        clock = [0.0]
        host = self.make_host(clock=lambda: clock[0], budget=PlannerBudget(seconds=1))
        host.execute({"action": "check-formula", "node_id": "f-001-1", "state_rev": 0, "params": {}})
        def late_repair(*args):
            clock[0] = 2.0
            return {"accepted": True, "edits": [{"after": "x+1"}], "check": {"status": "OK"}}
        host.repair = late_repair
        self.assertFalse(host.execute({"action": "propose-repair", "node_id": "f-001-1", "state_rev": 1, "params": {}}))
        self.assertFalse(host.edits)
        self.assertEqual(host.nodes[0]["state"], "human")
        clock[0] = 0.0
        host = self.make_host(clock=lambda: clock[0], budget=PlannerBudget(seconds=1))
        def late_check(*args):
            clock[0] = 2.0
            return {"status": "RETRY"}
        host.check = late_check
        host.run()
        host.repair.assert_not_called()
        self.assertEqual(host.nodes[0]["state"], "human")

    def test_product_job_persists_audits_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, clear=True), patch.object(studio, "_new_provider", return_value=ScriptedProvider(True)), \
                patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                patch.object(studio, "_verify_formula", side_effect=lambda latex: {"status": "OK" if latex == "x+1" else "RETRY"}), \
                TestClient(studio.app) as client, patch.object(studio.threading, "Thread") as thread:
            source = Path(directory) / "input.tex"
            source.write_text("Value $x+$")
            response = client.post("/api/studio/fix", params={"token": studio.TOKEN},
                                   json={"name": "input.tex", "content": source.read_text(), "planner_mode": True})
            self.assertEqual(response.status_code, 200)
            thread.call_args.kwargs["target"](*thread.call_args.kwargs["args"])
            result = client.get("/api/studio/fixstatus", params={"token": studio.TOKEN, "id": response.json()["job"]}).json()["result"]
            self.assertEqual(result["fixed_content"], "Value $x+1$")
            self.assertEqual(source.read_text(), "Value $x+$")
            self.assertTrue(result["requires_review"])
            self.assertTrue(result["planner_mode"])
            self.assertEqual(result["planner"]["rejected"], 1)
            self.assertEqual(result["model_calls"], 0)  # Offline fixture is not inference.
            self.assertTrue(any(e["action"] == "PLANNER_REJECTED" for e in result["trace"]))
            self.assertEqual(studio._read_job(result["job_id"])["result"], result)

    def test_job_never_runs_unchosen_checks_after_budget_rejection(self):
        provider = ScriptedProvider()
        provider.plan_action = lambda snapshot, **kwargs: {"action": "run-code", "node_id": "f-001-1", "state_rev": 0, "params": {}}
        job_id = "9" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None, "planner_mode": True}}, clear=True), \
                patch.object(studio, "_new_provider", return_value=provider), \
                patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                patch.object(studio, "_verify_formula", side_effect=AssertionError("unchosen checker must not run")) as check:
            studio._studio_job("input.tex", "$x+$", job_id)
            result = studio._read_job(job_id)["result"]
        check.assert_not_called()
        self.assertEqual(result["fixed_content"], "$x+$")
        self.assertEqual(result["planner"]["rejected"], 12)
        self.assertEqual(result["problems_after"][0]["line"], 1)
        self.assertEqual(result["problems_after"][0]["status"], "NEEDS_HUMAN")

    def test_defaults_off_and_rejects_truthy_strings(self):
        with TestClient(studio.app) as client, patch.object(studio, "_save_job"), \
                patch.object(studio.threading, "Thread"), patch.dict(studio._jobs, clear=True):
            for value in ("on", 1, None):
                self.assertEqual(client.post("/api/studio/fix", params={"token": studio.TOKEN},
                                            json={"name": "input.tex", "content": "x", "planner_mode": value}).status_code, 400)
            response = client.post("/api/studio/fix", params={"token": studio.TOKEN}, json={"name": "input.tex", "content": "x"})
            self.assertFalse(studio._jobs[response.json()["job"]]["planner_mode"])

    def test_duplicate_formulas_use_bound_offsets_and_control_text_is_rejected(self):
        provider = ScriptedProvider()
        with patch.object(studio, "_verify_formula", side_effect=lambda value: {"status": "OK" if value == "x+1" else "RETRY"}):
            candidate, edits, _ = studio._apply_planned_fixes("$x+$ and $x+$", [], provider=provider,
                                                            emit=lambda *args, **kwargs: None)
        self.assertEqual(candidate, "$x+1$ and $x+1$")
        self.assertEqual(len(edits), 2)
        provider.repair_formula = lambda *args, **kwargs: "x+1\n\\input{secret}"
        with patch.object(studio, "_verify_formula", return_value={"status": "RETRY"}) as checker:
            candidate, edits, report = studio._apply_planned_fixes("$x+$", [], provider=provider,
                                                                  emit=lambda *args, **kwargs: None)
        self.assertEqual(candidate, "$x+$")
        self.assertFalse(edits)
        self.assertEqual(report["nodes"][0]["state"], "human")
        checker.assert_called_once_with("x+")

    def test_simple_table_uses_host_decimal_candidate_with_no_repair_model(self):
        source = "\\begin{tabular}{lr}\nItem & Value \\\\\nA & 2 \\\\\nTotal & 3 \\\\\n\\end{tabular}\n"
        provider = ScriptedProvider()
        provider.repair_formula = Mock(side_effect=AssertionError("formula model is forbidden"))
        events = []
        fixed, edits, report = studio._apply_planned_fixes(source, [], provider=provider,
                                emit=lambda action, **fields: events.append({"action": action, **fields}))
        self.assertIn("Total & 2", fixed)
        self.assertEqual(len(edits), 1)
        self.assertEqual(report["nodes"][0]["state"], "candidate")
        provider.repair_formula.assert_not_called()
        self.assertFalse(studio._table_problems(fixed))


if __name__ == "__main__":
    unittest.main()
