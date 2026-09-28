"""Persistent Studio evidence and explicit model/Skill accounting, without inference."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from test_static_assets import studio


class Provider:
    def __init__(self):
        self.last_trace = {}
        self.calls = 0

    def fingerprint(self):
        return {"kind": "test", "skill_mode": "on", "skill_sha256": "a" * 64}

    def repair_formula(self, node):
        self.calls += 1
        self.last_trace = {"model_calls": 1, "model_called": True, "skill_loaded": True,
                           "skill_sha256": "a" * 64, "reason": "candidate", "provider": "mock"}
        return "x+" if self.calls == 1 else "x+1"


class TraceTest(unittest.TestCase):
    def test_invalid_text_never_creates_a_background_job(self):
        bodies = [{"name": "plain.tex", "content": value} for value in (None, 42, [], {}, True, "\ud800")]
        bodies += [{"name": value, "content": "text"} for value in (None, 42, [], {})]
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, clear=True), patch.object(studio.threading, "Thread") as thread, \
                TestClient(studio.app) as client:
            for body in bodies:
                with self.subTest(body=repr(body)):
                    response = client.post("/api/studio/fix", params={"token": studio.TOKEN},
                                           content=json.dumps(body), headers={"Content-Type": "application/json"})
                    self.assertEqual(response.status_code, 400)
            thread.assert_not_called()
            self.assertEqual(studio._jobs, {})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_job_acceptance_is_saved_before_worker_start(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, clear=True), patch.object(studio.threading, "Thread") as thread, \
                TestClient(studio.app) as client:
            response = client.post("/api/studio/fix", params={"token": studio.TOKEN},
                                   json={"name": "plain.tex", "content": "text"})
            self.assertEqual(response.status_code, 200)
            job_id = response.json()["job"]
            saved = json.loads((Path(directory) / "jobs" / job_id / "job.json").read_text())
            self.assertFalse(saved["done"])
            self.assertIsNone(saved["result"])
            thread.return_value.start.assert_called_once()

    def test_direct_worker_encoding_failure_is_terminal_and_persisted(self):
        job_id = "d" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None}}, clear=True), \
                patch.object(studio, "_studio_compile") as compile_document:
            studio._studio_job("plain.tex", "\ud800", job_id)
            compile_document.assert_not_called()
            self.assertTrue(studio._jobs[job_id]["done"])
            loaded = studio._read_job(job_id)
            self.assertIn("UnicodeEncodeError", loaded["error"])
            self.assertEqual(loaded["trace"][-1]["action"], "JOB_ERROR")
            self.assertIsNone(loaded["trace"][-1]["input_sha256"])

    def test_rejected_then_accepted_candidate_are_both_preserved(self):
        events = []
        provider = Provider()
        emit = lambda action, **fields: events.append({"action": action, **fields})
        with patch.object(studio, "_verify_formula", side_effect=[
                {"status": "RETRY", "reason": "original"},
                {"status": "RETRY", "reason": "rejected"}, {"status": "OK"}]):
            candidate, edits = studio._apply_fixes("Value $x+$", [], provider=provider, emit=emit)
        self.assertEqual(candidate, "Value $x+1$")
        self.assertEqual(len(edits), 1)
        rejected = [e for e in events if e["action"] == "CANDIDATE_REJECTED"]
        self.assertEqual(rejected[0]["candidate"], "x+")
        self.assertEqual(rejected[0]["check"]["reason"], "rejected")
        self.assertEqual([e["candidate"] for e in events if e["action"] == "PROVIDER_RESULT"], ["x+", "x+1"])
        self.assertEqual(sum(e["provider_trace"]["model_calls"] for e in events if e["action"] == "PROVIDER_RESULT"), 2)

    def test_rule_only_job_survives_memory_loss_without_claiming_model_call(self):
        job_id = "b" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.object(studio, "_new_provider", return_value=Provider()), \
                patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None}}, clear=True):
            studio._studio_job("plain.tex", "plain text", job_id)
            job = studio._jobs.pop(job_id)
            self.assertTrue(job["done"])
            self.assertIsNone(job["result"]["model"])
            self.assertEqual(job["result"]["model_calls"], 0)
            rows = [json.loads(line) for line in (Path(directory) / "jobs" / job_id / "events.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["action"], "JOB_START")
            self.assertEqual(rows[-1]["action"], "JOB_END")
            self.assertEqual([e["seq"] for e in rows], list(range(1, len(rows) + 1)))
            with TestClient(studio.app) as client:
                self.assertEqual(client.get("/api/studio/fixstatus", params={"id": job_id}).status_code, 401)
                response = client.get("/api/studio/fixstatus", params={"id": job_id, "token": studio.TOKEN})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["result"], job["result"])

    def test_incomplete_job_is_interrupted_not_silently_resumed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory):
            job_id = "c" * 32
            studio._save_job(job_id, {"done": False, "log": [], "result": None})
            loaded = studio._read_job(job_id)
            self.assertTrue(loaded["done"])
            self.assertIn("中断", loaded["error"])
            self.assertIsNone(loaded["result"])

    def test_same_name_jobs_keep_separate_compile_artifacts(self):
        ids = ("d" * 32, "e" * 32)
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.object(studio, "_new_provider", return_value=Provider()), \
                patch.dict(studio._jobs, clear=True):
            def compile_document(content, name, tag):
                artifact = Path(directory) / name / tag
                artifact.mkdir(parents=True)
                (artifact / "source.tex").write_text(content)
                return {"ok": True, "png": f"/api/studio/preview/{name}/{tag}"}

            with patch.object(studio, "_studio_compile", side_effect=compile_document) as compile_mock:
                for job_id, content in zip(ids, ("first document", "second document")):
                    studio._jobs[job_id] = {"done": False, "log": [], "result": None}
                    studio._studio_job("same.tex", content, job_id)
                tags = [call.args[2] for call in compile_mock.call_args_list]
                self.assertEqual(tags, ["before-" + ids[0], "after-" + ids[0],
                                        "before-" + ids[1], "after-" + ids[1]])
            studio._jobs.clear()
            first = studio._read_job(ids[0])["result"]
            self.assertIn(ids[0], first["compile_before"]["png"])
            self.assertEqual((Path(directory) / "same.tex" / ("before-" + ids[0]) / "source.tex").read_text(),
                             "first document")
            self.assertNotEqual(first["original_sha256"], studio._read_job(ids[1])["result"]["original_sha256"])

    def test_interruption_recovers_last_started_request_and_log_after_partial_event(self):
        job_id = "f" * 32
        provider = Provider()
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.object(studio, "_new_provider", return_value=provider), \
                patch.object(studio, "_studio_compile", return_value={"ok": True, "png": None}), \
                patch.object(studio, "_verify_formula", return_value={"status": "RETRY"}), \
                patch.object(provider, "repair_formula", side_effect=KeyboardInterrupt()), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None}}, clear=True):
            with self.assertRaises(KeyboardInterrupt):
                studio._studio_job("plain.tex", "Value $x+$", job_id)
            self.assertFalse(studio._jobs.pop(job_id)["done"])
            with (Path(directory) / "jobs" / job_id / "events.jsonl").open("a") as stream:
                stream.write('{"unfinished":')
            with TestClient(studio.app) as client:
                loaded = client.get("/api/studio/fixstatus", params={"id": job_id, "token": studio.TOKEN}).json()
            self.assertTrue(loaded["done"])
            self.assertIn("中断", loaded["error"])
            self.assertIsNone(loaded["result"])
            self.assertEqual(loaded["trace"][-1]["action"], "PROVIDER_START")
            self.assertFalse(any(event["action"] == "PROVIDER_RESULT" for event in loaded["trace"]))
            self.assertTrue(any("第 1 次" in line for line in loaded["log"]))

    def test_malformed_persisted_job_cannot_break_status_endpoint(self):
        job_id = "a" * 32
        records = [{}, {"done": "yes", "log": []}, {"done": True, "log": None},
                   {"done": True, "log": [42]}, {"done": True, "log": [], "result": []}]
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.dict(studio._jobs, clear=True), TestClient(studio.app) as client:
            for record in records:
                with self.subTest(record=record):
                    studio._save_job(job_id, record)
                    response = client.get("/api/studio/fixstatus", params={"id": job_id, "token": studio.TOKEN})
                    self.assertEqual(response.status_code, 404)

    def test_worker_error_excludes_dependency_error_text(self):
        job_id = "a" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(studio, "STUDIO_STATE", directory), \
                patch.object(studio, "_new_provider", side_effect=RuntimeError("http://secret-token@private")), \
                patch.dict(studio._jobs, {job_id: {"done": False, "log": [], "result": None}}, clear=True):
            studio._studio_job("plain.tex", "text", job_id)
            saved = studio._read_job(job_id)
            self.assertTrue(saved["done"])
            self.assertIn("RuntimeError", saved["error"])
            self.assertNotIn("secret-token", json.dumps(saved))

    def test_job_path_cannot_escape_state(self):
        with TestClient(studio.app) as client:
            result = client.get("/api/studio/fixstatus", params={"id": "../../outside", "token": studio.TOKEN})
        self.assertEqual(result.status_code, 400)


if __name__ == "__main__":
    unittest.main()
