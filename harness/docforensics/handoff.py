"""Versioned single-formula Math consumer. Source files are never written here."""
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

CHECKPOINT = "MiniCPM-V-4.7-1B"
MAX_DOCUMENT_BYTES = 262144
MAX_FORMULA_CHARS = 32768
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_FIELDS = frozenset({"name", "content", "revision", "source_range", "requested_action", "transfer_id"})
CORE_BINDINGS = ("schema_version", "transfer_id", "document_sha256", "input_sha256", "source_range",
                 "formula_id", "expected_revision", "original_latex", "checkpoint")
REVIEW_BINDINGS = frozenset({"input_hash", "parent_revision", "candidate_hash", "current_revision"})
_locks, _locks_guard = {}, threading.Lock()


class HandoffError(Exception):
    def __init__(self, reason, status=400):
        self.reason, self.status = reason, status
        super().__init__(reason)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_handoff_field")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("invalid_handoff_constant")


def _int(value, minimum=0):
    return type(value) is int and value >= minimum


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _transfer_id(value):
    try:
        valid = isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise HandoffError("invalid_transfer_id")
    return value


def build_envelope(body):
    if not isinstance(body, dict) or set(body) != REQUEST_FIELDS:
        raise HandoffError("invalid_handoff_request")
    transfer_id = _transfer_id(body["transfer_id"])
    name, content, revision, source_range = (body[k] for k in ("name", "content", "revision", "source_range"))
    if not isinstance(name, str) or not re.fullmatch(r"[\w.-]+\.tex", name):
        raise HandoffError("invalid_document_name")
    if not isinstance(content, str) or not _int(revision, 1):
        raise HandoffError("invalid_document_revision")
    try:
        raw = content.encode("utf-8")
    except UnicodeEncodeError:
        raise HandoffError("invalid_document_encoding") from None
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise HandoffError("document_too_large", 413)
    if (not isinstance(source_range, dict) or set(source_range) != {"start", "end", "encoding"}
            or not _int(source_range["start"]) or not _int(source_range["end"])
            or source_range["encoding"] != "unicode-codepoints"
            or not 0 <= source_range["start"] < source_range["end"] <= len(content)):
        raise HandoffError("invalid_source_range")
    start, end = source_range["start"], source_range["end"]
    # Only an existing, complete dollar-delimited inline body may be transferred.
    spans, offset = [], 0
    for line in content.splitlines(keepends=True):
        spans.extend((offset + match.start(1), offset + match.end(1))
                     for match in re.finditer(r"(?<!\\)\$(.+?)(?<!\\)\$", line))
        offset += len(line)
    if (start, end) not in spans:
        raise HandoffError("range_is_not_one_inline_formula")
    original = content[start:end]
    if not original.strip() or len(original) > MAX_FORMULA_CHARS or any(ord(c) < 32 or ord(c) == 127 for c in original):
        raise HandoffError("invalid_original_formula")
    action = body["requested_action"]
    if action not in ("repair", "complete"):
        raise HandoffError("unsupported_handoff_action")
    formula_id = "formula-" + sha256(canonical({"name": name, "range": source_range, "input": sha256(original)}))[:24]
    return {"schema_version": 1, "transfer_id": transfer_id, "document_sha256": sha256(content),
            "input_sha256": sha256(original), "source_range": dict(source_range), "formula_id": formula_id,
            "expected_revision": revision, "original_latex": original, "requested_action": action,
            "allowed_scope": "syntax_repair" if action == "repair" else "completion_prefix",
            "checkpoint": CHECKPOINT, "budget": {"max_steps": 3, "max_seconds": 90, "max_tokens": 2048},
            "requires_review": True, "evidence": []}


def validate_response(envelope, response):
    allowed = set(envelope) | {"status", "candidate", "candidate_sha256", "parent_revision", "candidate_revision",
                               "diff", "inference_fingerprint", "review"}
    if not isinstance(response, dict) or set(response) - allowed:
        raise HandoffError("invalid_handoff_response", 502)
    for field in CORE_BINDINGS:
        if field not in response or type(response[field]) is not type(envelope[field]) or canonical(response[field]) != canonical(envelope[field]):
            raise HandoffError("handoff_binding_mismatch", 502)
    for field in ("requested_action", "allowed_scope", "budget", "requires_review"):
        if field in response and (type(response[field]) is not type(envelope[field]) or canonical(response[field]) != canonical(envelope[field])):
            raise HandoffError("handoff_binding_mismatch", 502)
    candidate = response.get("candidate")
    try:
        candidate_valid_utf8 = isinstance(candidate, str) and bool(candidate.encode("utf-8"))
    except UnicodeEncodeError:
        candidate_valid_utf8 = False
    if (not candidate_valid_utf8 or response.get("status") != "review_required" or not isinstance(candidate, str)
            or not candidate.strip() or len(candidate) > MAX_FORMULA_CHARS
            or any(ord(c) < 32 or ord(c) == 127 for c in candidate)
            or re.search(r"(?<!\\)\$", candidate)
            or not _hash(response.get("candidate_sha256")) or sha256(candidate) != response["candidate_sha256"]):
        raise HandoffError("invalid_handoff_candidate", 502)
    if envelope["requested_action"] == "complete" and not candidate.startswith(envelope["original_latex"]):
        raise HandoffError("completion_prefix_changed", 502)
    if ("parent_revision" not in response or (response["parent_revision"] is not None and not _int(response["parent_revision"]))
            or not _int(response.get("candidate_revision"), 1)):
        raise HandoffError("invalid_math_revision", 502)
    for field in ("diff", "evidence", "inference_fingerprint"):
        if not isinstance(response.get(field), dict):
            raise HandoffError("invalid_handoff_evidence", 502)
    if any(not isinstance(response["evidence"].get(k), dict) for k in ("mutation_scope", "cas_transition")):
        raise HandoffError("invalid_handoff_evidence", 502)
    review = response.get("review")
    expected = {"input_hash": envelope["input_sha256"], "parent_revision": response["parent_revision"],
                "candidate_hash": response["candidate_sha256"], "current_revision": response["candidate_revision"]}
    validate_review(review, expected, status="PENDING")
    return response


def validate_review(review, binding, *, status, review_id=None):
    if (not isinstance(review, dict) or not isinstance(review.get("id"), str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", review["id"])
            or (review_id is not None and review["id"] != review_id) or review.get("status") != status
            or not isinstance(review.get("binding"), dict) or set(review["binding"]) != REVIEW_BINDINGS):
        raise HandoffError("invalid_review_response", 502)
    for key, value in binding.items():
        if type(review["binding"][key]) is not type(value) or review["binding"][key] != value:
            raise HandoffError("review_binding_mismatch", 502)
        if key in review and (type(review[key]) is not type(value) or review[key] != value):
            raise HandoffError("review_binding_mismatch", 502)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FormulaHandoffClient:
    def __init__(self, state_dir, *, endpoint=None, enabled=None):
        self.enabled = os.environ.get("TEXADA_MATH_HANDOFF_ENABLED", "0") == "1" if enabled is None else enabled
        self.endpoint = (endpoint or os.environ.get("TEXADA_MATH_ENDPOINT", "http://127.0.0.1:18732")).rstrip("/")
        parts = urllib.parse.urlsplit(self.endpoint)
        try:
            parts.port
        except ValueError:
            raise HandoffError("invalid_math_endpoint", 503) from None
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment):
            raise HandoffError("invalid_math_endpoint", 503)
        handlers = [_NoRedirect()]
        if parts.hostname in {"localhost", "127.0.0.1", "::1"}:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)
        self.state_dir = Path(state_dir) / "handoffs"
        self.endpoint_sha256 = sha256(self.endpoint)

    def _guard(self):
        if not self.enabled:
            raise HandoffError("math_handoff_disabled", 409)

    def _path(self, transfer_id):
        return self.state_dir / (_transfer_id(transfer_id) + ".json")

    def _lock(self, transfer_id):
        identity = str(self._path(transfer_id).absolute())
        with _locks_guard:
            return _locks.setdefault(identity, threading.Lock())

    def _read(self, transfer_id):
        path = self._path(transfer_id)
        try:
            with path.open("rb") as handle:
                raw = handle.read(2 * 1024 * 1024 + 1)
        except FileNotFoundError:
            return None
        if len(raw) > 2 * 1024 * 1024:
            raise HandoffError("invalid_saved_transfer", 409)
        try:
            record = json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)
            if (not isinstance(record, dict) or type(record.get("schema_version")) is not int or record["schema_version"] != 1
                    or record.get("decision") not in (None, "accept", "reject")
                    or record.get("decision_intent") not in (None, "accept", "reject")):
                raise ValueError()
            expected = build_envelope(record["request"])
            if record["envelope"] != expected or record["digest"] != sha256(canonical(expected)):
                raise ValueError()
            if record["endpoint_sha256"] != self.endpoint_sha256:
                raise HandoffError("math_endpoint_changed", 409)
            if record.get("response") is not None:
                validate_response(expected, record["response"])
            if record.get("decision_response") is not None:
                validate_review(record["decision_response"], record["response"]["review"]["binding"],
                                status="ACCEPTED" if record["decision"] == "accept" else "REJECTED",
                                review_id=record["response"]["review"]["id"])
            return record
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            raise HandoffError("invalid_saved_transfer", 409) from None

    def _write(self, transfer_id, record):
        path = self._path(transfer_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(canonical(record))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)

    def _post(self, path, payload):
        request = urllib.request.Request(self.endpoint + path, data=canonical(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self.opener.open(request, timeout=95) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if 300 <= exc.code < 400:
                raise HandoffError("math_redirect_refused", 502) from None
            raise HandoffError("math_request_rejected", 409 if exc.code == 409 else 502) from None
        except (TimeoutError, urllib.error.URLError) as exc:
            timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
            raise HandoffError("math_timeout" if timed_out else "math_unavailable", 504 if timed_out else 503) from None
        except OSError:
            raise HandoffError("math_unavailable", 503) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise HandoffError("math_response_too_large", 502)
        try:
            return json.loads(raw, object_pairs_hook=_unique, parse_constant=_invalid_constant)
        except (ValueError, UnicodeDecodeError):
            raise HandoffError("invalid_math_json", 502) from None

    def propose(self, body):
        self._guard()
        envelope = build_envelope(body)
        transfer_id, digest = envelope["transfer_id"], sha256(canonical(envelope))
        with self._lock(transfer_id):
            record = self._read(transfer_id)
            if record is not None and record["digest"] != digest:
                raise HandoffError("transfer_id_conflict", 409)
            if record is not None and record.get("failure"):
                raise HandoffError("failed_transfer_requires_new_id", 409)
            if record is None:
                record = {"schema_version": 1, "digest": digest, "endpoint_sha256": self.endpoint_sha256,
                          "request": json.loads(canonical(body)), "envelope": envelope, "response": None, "decision": None, "decision_response": None}
                self._write(transfer_id, record)
            if record["response"] is None:
                try:
                    record["response"] = validate_response(envelope, self._post("/api/handoff/formula", envelope))
                except HandoffError as exc:
                    record["failure"] = exc.reason
                    self._write(transfer_id, record)
                    raise
                self._write(transfer_id, record)
            return self._proposal(record)

    def _proposal(self, record):
        envelope, response, request = record["envelope"], record["response"], record["request"]
        source = request["content"]
        start, end = (envelope["source_range"][k] for k in ("start", "end"))
        if sha256(source) != envelope["document_sha256"] or source[start:end] != envelope["original_latex"]:
            raise HandoffError("stale_transfer_source", 409)
        candidate = source[:start] + response["candidate"] + source[end:]
        fingerprint = response["inference_fingerprint"]
        calls = fingerprint.get("calls")
        model_calls = len(calls) if fingerprint.get("status") == "RECORDED" and isinstance(calls, list) else None
        return {"fixed_content": candidate, "original_sha256": envelope["document_sha256"],
                "candidate_sha256": sha256(candidate), "source_revision": envelope["expected_revision"],
                "handoff_transfer_id": envelope["transfer_id"], "handoff": response,
                "requires_review": True, "adoption_status": record.get("decision_response", {}).get("status") if record.get("decision_response") else "PENDING",
                "configured_model": CHECKPOINT, "model": CHECKPOINT if model_calls else None, "model_calls": model_calls, "provider": "configured-Math-Agent",
                "skill_mode": "handoff", "elapsed_seconds": None, "problems_after": [],
                "compile_before": {"ok": False, "status": "NOT_CHECKED", "png": None},
                "compile_after": {"ok": False, "status": "NOT_CHECKED", "png": None},
                "edits": [{"line": source[:start].count("\n") + 1, "before": envelope["original_latex"],
                           "after": response["candidate"], "skill": "Math-Agent-single-formula"}],
                "scope": "单公式候选交接；没有 OCR 或数学语义验证；编译未执行", "trace": [{"action": "HANDOFF_RESULT", "handoff": response}]}

    def decide(self, transfer_id, body):
        self._guard()
        if not isinstance(body, dict) or set(body) != {"decision", "name", "content", "revision"} or not isinstance(body["decision"], str) or body["decision"] not in {"accept", "reject"}:
            raise HandoffError("invalid_review_decision")
        with self._lock(transfer_id):
            record = self._read(transfer_id)
            if record is None or record.get("response") is None:
                raise HandoffError("unknown_transfer", 404)
            request, envelope, response = record["request"], record["envelope"], record["response"]
            if (not isinstance(body["content"], str) or type(body["revision"]) is not int
                    or body["name"] != request["name"] or body["content"] != request["content"]
                    or sha256(body["content"]) != envelope["document_sha256"] or body["revision"] != envelope["expected_revision"]):
                raise HandoffError("stale_transfer_source", 409)
            if record.get("decision_intent") is not None and record["decision_intent"] != body["decision"]:
                raise HandoffError("review_decision_intent_conflict", 409)
            if record["decision"] is not None and record["decision"] != body["decision"]:
                raise HandoffError("review_already_decided", 409)
            binding = response["review"]["binding"]
            if record["decision_response"] is None:
                record["decision_intent"] = body["decision"]
                self._write(transfer_id, record)
                payload = {"decision": body["decision"], "binding": binding}
                review_id = response["review"]["id"]
                decision_response = self._post("/api/reviews/" + urllib.parse.quote(review_id, safe="") + "/decision", payload)
                validate_review(decision_response, binding, status="ACCEPTED" if body["decision"] == "accept" else "REJECTED", review_id=review_id)
                record.update(decision=body["decision"], decision_response=decision_response)
                self._write(transfer_id, record)
            proposal = self._proposal(record)
            return {"transfer_id": transfer_id, "decision": body["decision"], "review": record["decision_response"],
                    "original_sha256": envelope["document_sha256"], "candidate_sha256": proposal["candidate_sha256"],
                    "source_revision": envelope["expected_revision"]}
