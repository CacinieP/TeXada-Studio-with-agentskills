"""Real loopback HTTP consumer contracts; no model/compiler/private documents."""
import copy
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

from fastapi.testclient import TestClient
from test_static_assets import studio
from docforensics.handoff import FormulaHandoffClient, HandoffError, build_envelope, canonical, sha256, validate_response


def request_body(content="😀 prefix $x+$ suffix", *, action="repair"):
    start = content.index("x+")
    return {"name": "input.tex", "content": content, "revision": 7,
            "source_range": {"start": start, "end": start + 2, "encoding": "unicode-codepoints"},
            "requested_action": action, "transfer_id": str(uuid.uuid4())}


def response_for(envelope):
    candidate = envelope["original_latex"] + "1"
    binding = {"input_hash": envelope["input_sha256"], "parent_revision": None,
               "candidate_hash": sha256(candidate), "current_revision": 1}
    return {**envelope, "status": "review_required", "candidate": candidate,
            "candidate_sha256": sha256(candidate), "parent_revision": None, "candidate_revision": 1,
            "diff": {"before": envelope["original_latex"], "after": candidate},
            "evidence": {"mutation_scope": {"status": "PASS"}, "cas_transition": {"status": "SHADOW"}},
            "inference_fingerprint": {"status": "NOT_CHECKED", "fixture": True},
            "review": {"id": "review-fixture-1", "status": "PENDING", "binding": binding, **binding}}


class FakeMath:
    def __init__(self):
        self.requests = []
        self.transform = lambda data: data
        self.redirect = False
        self.raw_response = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append((self.path, payload))
                if owner.redirect:
                    self.send_response(302)
                    self.send_header("Location", "/redirect-target")
                    self.end_headers()
                    return
                if self.path == "/api/handoff/formula":
                    result = response_for(payload)
                elif self.path == "/api/reviews/review-fixture-1/decision":
                    result = {"id": "review-fixture-1", "status": "ACCEPTED" if payload["decision"] == "accept" else "REJECTED",
                              "binding": payload["binding"], **payload["binding"]}
                else:
                    self.send_error(404)
                    return
                result = owner.transform(result)
                raw = owner.raw_response if owner.raw_response is not None else canonical(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = "http://127.0.0.1:" + str(self.server.server_port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.math = FakeMath()
        self.addCleanup(self.math.close)
        self.client = FormulaHandoffClient(self.temp.name, endpoint=self.math.endpoint, enabled=True)
        self.body = request_body()

    def test_real_wire_binds_unicode_range_and_builds_only_candidate_buffer(self):
        source = Path(self.temp.name) / "input.tex"
        source.write_text(self.body["content"])
        result = self.client.propose(self.body)
        self.assertEqual(result["fixed_content"], "😀 prefix $x+1$ suffix")
        self.assertEqual(source.read_text(), self.body["content"])
        self.assertTrue(result["requires_review"])
        path, payload = self.math.requests[0]
        self.assertEqual(path, "/api/handoff/formula")
        self.assertEqual(payload["source_range"], self.body["source_range"])
        self.assertEqual(payload["source_range"]["end"] - payload["source_range"]["start"], len(payload["original_latex"]))
        self.assertEqual(payload["checkpoint"], "MiniCPM-V-4.7-1B")
        self.assertEqual(payload["allowed_scope"], "syntax_repair")
        self.assertEqual(payload["budget"], {"max_steps": 3, "max_seconds": 90, "max_tokens": 2048})
        self.assertNotIn("content", payload)
        self.assertNotIn("endpoint", payload)
        self.assertEqual(result["original_sha256"], sha256(self.body["content"]))
        self.assertEqual(result["candidate_sha256"], sha256(result["fixed_content"]))

    def test_duplicate_and_restart_reuse_one_inference_and_conflicting_id_fails(self):
        first = self.client.propose(self.body)
        second_client = FormulaHandoffClient(self.temp.name, endpoint=self.math.endpoint, enabled=True)
        self.assertEqual(second_client.propose(self.body), first)
        self.assertEqual(len(self.math.requests), 1)
        modified = {**self.body, "requested_action": "complete"}
        with self.assertRaisesRegex(HandoffError, "transfer_id_conflict"):
            second_client.propose(modified)
        self.assertEqual(len(self.math.requests), 1)

    def test_concurrent_duplicates_share_execution(self):
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda _: self.client.propose(self.body), range(4)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(len(self.math.requests), 1)

    def test_request_schema_path_range_revision_and_url_injection_fail_before_network(self):
        cases = [None, {**self.body, "endpoint": "https://attacker.invalid"}, {**self.body, "api_key": "test-only"},
                 {**self.body, "revision": True}, {**self.body, "name": "../input.tex"}, {**self.body, "transfer_id": "../../evil"},
                 {**self.body, "requested_action": []}, {**self.body, "source_range": {"start": True, "end": 3, "encoding": "unicode-codepoints"}},
                 {**self.body, "source_range": {"start": 0, "end": 2, "encoding": "unicode-codepoints"}},
                 {**self.body, "source_range": {"start": 10, "end": 11, "encoding": "utf16"}}]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(HandoffError):
                self.client.propose(body)
        self.assertFalse(self.math.requests)

    def test_each_response_binding_and_review_tuple_is_checked(self):
        envelope = build_envelope(self.body)
        response = response_for(envelope)
        variants = []
        for field in ("document_sha256", "input_sha256", "candidate_sha256"):
            variants.append({**response, field: "0" * 64})
        variants += [{**response, "checkpoint": "other-model"}, {**response, "expected_revision": True},
                     {**response, "source_range": {**response["source_range"], "start": True}},
                     {**response, "status": "committed"}, {**response, "candidate": "x+1\ncommand"},
                     {**response, "candidate": "x+$ evil"}, {**response, "evidence": []},
                     {**response, "parent_revision": False}, {**response, "candidate_revision": 0}]
        for key, value in (("input_hash", "0" * 64), ("candidate_hash", "0" * 64), ("parent_revision", 1), ("current_revision", True)):
            changed = copy.deepcopy(response)
            changed["review"]["binding"][key] = value
            variants.append(changed)
        changed = copy.deepcopy(response)
        changed["review"]["current_revision"] = 9
        variants.append(changed)
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(HandoffError):
                validate_response(envelope, variant)
        self.assertEqual(validate_response(envelope, response), response)

    def test_nested_boolean_range_and_invalid_utf8_candidate_are_rejected(self):
        body = request_body("$x+$")
        envelope = build_envelope(body)
        response = response_for(envelope)
        response["source_range"] = {"start": True, "end": 3, "encoding": "unicode-codepoints"}
        with self.assertRaisesRegex(HandoffError, "handoff_binding_mismatch"):
            validate_response(envelope, response)
        response = response_for(envelope)
        response["candidate"] = "\ud800"
        with self.assertRaisesRegex(HandoffError, "invalid_handoff_candidate"):
            validate_response(envelope, response)

    def test_ambiguous_decision_timeout_pins_intent_for_idempotent_retry(self):
        self.client.propose(self.body)
        decision = {"decision": "accept", "name": self.body["name"], "content": self.body["content"], "revision": self.body["revision"]}
        with patch.object(self.client.opener, "open", side_effect=TimeoutError("private detail")):
            with self.assertRaisesRegex(HandoffError, "math_timeout"):
                self.client.decide(self.body["transfer_id"], decision)
        with self.assertRaisesRegex(HandoffError, "review_decision_intent_conflict"):
            self.client.decide(self.body["transfer_id"], {**decision, "decision": "reject"})
        result = self.client.decide(self.body["transfer_id"], decision)
        self.assertEqual(result["review"]["status"], "ACCEPTED")
        self.assertEqual(len(self.math.requests), 2)

    def test_completion_keeps_original_prefix_and_exact_scope(self):
        self.body["requested_action"] = "complete"
        result = self.client.propose(self.body)
        self.assertEqual(result["handoff"]["allowed_scope"], "completion_prefix")
        envelope = build_envelope(self.body)
        response = response_for(envelope)
        response.update(candidate="different", candidate_sha256=sha256("different"))
        with self.assertRaisesRegex(HandoffError, "completion_prefix_changed"):
            validate_response(envelope, response)

    def test_review_decision_uses_exact_binding_and_is_idempotent(self):
        proposal = self.client.propose(self.body)
        decision = {"decision": "accept", "name": self.body["name"], "content": self.body["content"], "revision": self.body["revision"]}
        result = self.client.decide(self.body["transfer_id"], decision)
        self.assertEqual(result["review"]["status"], "ACCEPTED")
        self.assertEqual(self.client.decide(self.body["transfer_id"], decision), result)
        self.assertEqual(len(self.math.requests), 2)
        self.assertEqual(self.math.requests[-1], ("/api/reviews/review-fixture-1/decision",
                         {"decision": "accept", "binding": proposal["handoff"]["review"]["binding"]}))
        with self.assertRaises(HandoffError):
            self.client.decide(self.body["transfer_id"], {**decision, "decision": "reject"})

    def test_stale_document_revision_or_file_never_sends_decision(self):
        self.client.propose(self.body)
        decision = {"decision": "accept", "name": self.body["name"], "content": self.body["content"], "revision": self.body["revision"]}
        for change in ({"content": "edited"}, {"revision": 8}, {"revision": True}, {"name": "other.tex"}, {"decision": []}):
            with self.subTest(change=change), self.assertRaises(HandoffError):
                self.client.decide(self.body["transfer_id"], {**decision, **change})
        self.assertEqual(len(self.math.requests), 1)

    def test_reject_never_creates_an_adopted_document(self):
        self.client.propose(self.body)
        result = self.client.decide(self.body["transfer_id"], {"decision": "reject", "name": self.body["name"],
                                   "content": self.body["content"], "revision": self.body["revision"]})
        self.assertEqual(result["review"]["status"], "REJECTED")
        self.assertEqual(set(Path(self.temp.name).iterdir()), {Path(self.temp.name) / "handoffs"})

    def test_redirect_is_never_followed_and_failed_id_never_reexecutes(self):
        self.math.redirect = True
        with self.assertRaisesRegex(HandoffError, "math_redirect_refused"):
            self.client.propose(self.body)
        self.assertEqual(len(self.math.requests), 1)
        with self.assertRaisesRegex(HandoffError, "failed_transfer_requires_new_id"):
            self.client.propose(self.body)
        self.assertEqual(len(self.math.requests), 1)

    def test_timeout_and_duplicate_json_preserve_source(self):
        with patch.object(self.client.opener, "open", side_effect=TimeoutError("private endpoint detail")):
            with self.assertRaisesRegex(HandoffError, "math_timeout"):
                self.client.propose(self.body)
        record = next((Path(self.temp.name) / "handoffs").glob("*.json")).read_text()
        self.assertNotIn("private endpoint detail", record)
        self.body["transfer_id"] = str(uuid.uuid4())
        self.math.raw_response = b'{"candidate":"x","candidate":"y"}'
        with self.assertRaisesRegex(HandoffError, "invalid_math_json"):
            self.client.propose(self.body)
        self.assertEqual(self.body["content"], "😀 prefix $x+$ suffix")

    def test_changed_endpoint_and_tampered_local_record_are_rejected(self):
        self.client.propose(self.body)
        other = FormulaHandoffClient(self.temp.name, endpoint="http://127.0.0.1:1", enabled=True)
        with self.assertRaisesRegex(HandoffError, "math_endpoint_changed"):
            other.propose(self.body)
        path = Path(self.temp.name) / "handoffs" / (self.body["transfer_id"] + ".json")
        record = json.loads(path.read_text())
        record["request"]["content"] += "edited"
        path.write_text(json.dumps(record))
        with self.assertRaises(HandoffError):
            self.client.propose(self.body)

    def test_api_real_wire_and_default_off(self):
        with patch.object(studio, "STUDIO_STATE", self.temp.name), TestClient(studio.app) as app:
            auth = {"token": studio.TOKEN}
            self.assertEqual(app.post("/api/studio/handoff", json=self.body).status_code, 401)
            with patch.dict("os.environ", {"TEXADA_MATH_HANDOFF_ENABLED": "0"}):
                self.assertFalse(app.get("/api/studio/handoff/config", params=auth).json()["enabled"])
                self.assertEqual(app.post("/api/studio/handoff", params=auth, json=self.body).status_code, 409)
            with patch.dict("os.environ", {"TEXADA_MATH_HANDOFF_ENABLED": "1", "TEXADA_MATH_ENDPOINT": self.math.endpoint}):
                proposal = app.post("/api/studio/handoff", params=auth, json=self.body)
                self.assertEqual(proposal.status_code, 200)
                result = app.post("/api/studio/handoff/" + self.body["transfer_id"] + "/decision", params=auth,
                                  json={"decision": "accept", "name": self.body["name"], "content": self.body["content"], "revision": self.body["revision"]})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["review"]["status"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
