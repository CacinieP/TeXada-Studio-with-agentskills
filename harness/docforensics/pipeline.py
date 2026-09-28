"""三态流水线：节点遍历、质检分发、修复循环、断点续跑。

三态协议：OK（通过）/ RETRY（可修复，自动重试 ≤2 次）/ NEEDS_HUMAN（进报告，不阻塞）。
所有决策追加写入 state.jsonl；仅输入与运行上下文哈希一致的终态可续跑跳过。
"""

import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import subprocess
import sys

from . import state
from .vlm import FixtureProvider, OllamaProvider

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VERIFY = os.path.join(REPO, "skills", "doc-formula-verify", "scripts", "verify.py")
AUDIT = os.path.join(REPO, "skills", "doc-table-audit", "scripts", "audit_table.py")

MAX_RETRIES = 2
TRANSIENT_PROVIDER_FAILURES = {
    "timeout", "network_error", "http_error", "provider_error", "provider_exception",
    "bad_response_json", "bad_response_shape", "empty_response", "bad_candidate_json",
    "bad_candidate_type", "empty_candidate", "candidate_too_large", "response_too_large",
}


def load_provider(args):
    if args.vlm:
        return OllamaProvider(base=args.vlm, model=args.vlm_model,
                              skill_mode=getattr(args, "skill_mode", "on"),
                              seed=getattr(args, "seed", 0),
                              max_tokens=getattr(args, "max_tokens", 300))
    return FixtureProvider(args.fixture_repairs)


def run_verify(latex):
    if not isinstance(latex, str):
        return {"status": "NEEDS_HUMAN", "reason": "bad_input: latex must be a string"}
    try:
        p = subprocess.run([sys.executable, VERIFY, latex], capture_output=True, text=True, timeout=30)
        result = json.loads(p.stdout.strip().splitlines()[-1])
        expected_exits = {"OK": 0, "RETRY": 0, "NEEDS_HUMAN": 1, "NEEDS_ENV": 2}
        if not isinstance(result, dict) or result.get("status") not in expected_exits:
            raise ValueError("invalid verifier status")
        if p.returncode != expected_exits[result["status"]]:
            raise ValueError("invalid verifier exit code")
        return result
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, AttributeError, TypeError) as exc:
        return {"status": "NEEDS_ENV", "reason": f"verify.py unavailable: {type(exc).__name__}"}


def run_audit(rec):
    try:
        p = subprocess.run([sys.executable, AUDIT], input=json.dumps(rec),
                           capture_output=True, text=True, timeout=30)
        result = json.loads(p.stdout.strip().splitlines()[-1])
        if not isinstance(result, dict) or result.get("status") not in ("OK", "RETRY", "NEEDS_HUMAN"):
            raise ValueError("invalid audit status")
        # audit_table.py uses exit 1 for a normal NEEDS_HUMAN result.
        allowed_exits = (0, 1) if result["status"] == "NEEDS_HUMAN" else (0,)
        if p.returncode not in allowed_exits:
            raise ValueError("invalid audit exit code")
        return result
    except (OSError, subprocess.SubprocessError, ValueError, IndexError, AttributeError, TypeError) as exc:
        return {"status": "NEEDS_HUMAN", "reason": "checker_error",
                "detail": f"audit unavailable: {type(exc).__name__}"}



def _file_sha256(path):
    try:
        with open(path, "rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()
    except (OSError, TypeError):
        return "unavailable"


def _provider_context(provider):
    """Only a provider-declared fingerprint can authorize cross-run reuse.

    Unknown custom providers get a nonce instead of incorrectly treating their
    uninspected configuration as equivalent. Neither fingerprint nor endpoint
    is written in clear text to the journal.
    """
    fingerprint = getattr(provider, "fingerprint", None)
    if callable(fingerprint):
        try:
            value = fingerprint()
            if not isinstance(value, dict):
                raise ValueError("fingerprint must be an object")
            state.canonical_sha256(value)
            return {"provider_class": type(provider).__name__, "fingerprint": value}
        except Exception:
            pass
    return {"provider_class": type(provider).__name__, "unverified": state.new_run_id()}


def node_identity(node, provider, kind=None):
    """Return hashes of canonical input and the full known execution context."""
    data = node.get("data") or {}
    crop = data.get("crop") if isinstance(data, dict) else None
    identity = {"node": node}
    if crop:
        identity["crop_sha256"] = _file_sha256(crop)
    versions = {}
    for distribution in ("sympy", "antlr4-python3-runtime"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "unavailable"
    kind = kind or node.get("type")
    checker = VERIFY if kind == "formula" else AUDIT if kind == "table" else None
    context = {
        "schema_version": state.SCHEMA_VERSION,
        "checker_sha256": _file_sha256(checker) if checker else None,
        "pipeline_sha256": _file_sha256(__file__),
        "state_sha256": _file_sha256(state.__file__),
        "python": list(sys.version_info[:3]), "dependencies": versions,
        "max_retries": MAX_RETRIES, "provider": _provider_context(provider),
    }
    return state.canonical_sha256(identity), state.canonical_sha256(context)


def _event_context(node, provider, doc, run_id, input_sha256, context_sha256, kind=None):
    if not input_sha256 or not context_sha256:
        input_sha256, context_sha256 = node_identity(node, provider, kind=kind)
    return {"run_id": run_id or state.new_run_id(), "doc": doc, "node_id": node["id"],
            "input_sha256": input_sha256, "context_sha256": context_sha256}


def _evidence(run_dir, node):
    """Copy evidence under a content hash; journal paths are run-relative."""
    data = node.get("data") or {}
    crop = data.get("crop") if isinstance(data, dict) else None
    if isinstance(crop, str) and os.path.isfile(crop):
        filename = _file_sha256(crop) + os.path.splitext(crop)[1]
        dst = os.path.join(run_dir, "crops", filename)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.abspath(crop) != os.path.abspath(dst):
            shutil.copy(crop, dst)
        return os.path.relpath(dst, run_dir)
    return None


def _provider_name(provider):
    # Provider classes supply constant display names; never stringify objects.
    name = getattr(type(provider), "name", None)
    return name if isinstance(name, str) else type(provider).__name__


def _trace_metadata(provider):
    """Whitelist public trace fields; never log raw error objects or URLs."""
    raw = getattr(provider, "last_trace", None)
    if not isinstance(raw, dict):
        return {"model_calls": 0, "model_calls_known": False}
    trace = {}
    calls = raw.get("model_calls")
    known = isinstance(calls, int) and not isinstance(calls, bool) and calls >= 0
    trace["model_calls"] = calls if known else 0
    trace["model_calls_known"] = known
    trace["model_called"] = bool(calls) if known else False
    for key in ("reason", "skill_id", "skill_name", "skill_sha256", "prompt_sha256"):
        value = raw.get(key)
        # These fields are protocol identifiers/hashes, never free-form errors.
        if (isinstance(value, str) and len(value) <= 160
                and all(char.isalnum() or char in "_.:- " for char in value)):
            trace[key] = value
    for key in ("skill_loaded", "response_truncated"):
        if isinstance(raw.get(key), bool):
            trace[key] = raw[key]
    if raw.get("skill_mode") in ("on", "off"):
        trace["skill_mode"] = raw["skill_mode"]
    elapsed = raw.get("elapsed_seconds")
    if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) and math.isfinite(elapsed) and elapsed >= 0:
        trace["elapsed_seconds"] = elapsed
    usage = raw.get("usage")
    if isinstance(usage, dict):
        trace["usage"] = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                          if isinstance(usage.get(key), int) and not isinstance(usage[key], bool) and usage[key] >= 0}
    content = raw.get("raw_candidate_response")
    if isinstance(content, str):
        trace["raw_candidate_response"] = content[:8192]
        trace["response_truncated"] = bool(trace.get("response_truncated")) or len(content) > 8192
    return trace


def _invoke_provider(run_dir, common, provider, node, kind, attempt, previous):
    state.append(run_dir, **common, action="PROVIDER_START", attempt=attempt,
                 checker_status=previous.get("status"), checker_reason=previous.get("reason", ""),
                 provider=_provider_name(provider))
    error = None
    try:
        candidate = getattr(provider, "repair_" + kind)(node)
        # Invalid provider objects are a rejected result, not a broken journal.
        state.canonical_sha256(candidate)
    except Exception as exc:
        # Exception messages can contain endpoints or credentials.
        candidate = None
        error = type(exc).__name__
    trace = _trace_metadata(provider)
    if error:
        trace["reason"] = "provider_exception"
        trace["error_type"] = error
    if candidate is None:
        trace.setdefault("reason", "no_candidate")
    state.append(run_dir, **common, action="PROVIDER_RESULT", attempt=attempt,
                 candidate=candidate, **trace)
    return candidate, trace


def _record_check(run_dir, common, result, stage, attempt, **content):
    state.append(run_dir, **common, action="CHECK", stage=stage, attempt=attempt,
                 checker_status=result.get("status"), checker_reason=result.get("reason", ""),
                 checker_detail=result.get("detail", ""), **content)


def _process(run_dir, doc, node, provider, kind, run_id=None,
             input_sha256=None, context_sha256=None):
    common = _event_context(node, provider, doc, run_id, input_sha256, context_sha256, kind)
    common["skill"] = "doc-formula-verify" if kind == "formula" else "doc-table-audit"
    data = node.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    original = data.get("latex") if kind == "formula" else data.get("rows")
    def check(value):
        return run_verify(value) if kind == "formula" else run_audit({
            "id": node["id"], "rows": value, "expected": data.get("expected", {})})
    result = check(original)
    _record_check(run_dir, common, result, "original", 0, original=original)
    attempts, model_calls, model_calls_known = 0, 0, True
    repaired = None
    provider_reason = None
    while result.get("status") == "RETRY" and attempts < MAX_RETRIES:
        attempts += 1
        candidate, trace = _invoke_provider(run_dir, common, provider, node, kind, attempts, result)
        model_calls += trace["model_calls"]
        model_calls_known = model_calls_known and trace["model_calls_known"]
        if candidate is None:
            provider_reason = trace.get("reason", "no_candidate")
            state.append(run_dir, **common, action="CANDIDATE_REJECTED", attempt=attempts,
                         candidate=None, reason=provider_reason,
                         checker_status=result.get("status"), checker_reason=result.get("reason", ""))
            break
        result = check(candidate)
        _record_check(run_dir, common, result, "candidate", attempts, candidate=candidate)
        accepted = result.get("status") == "OK"
        state.append(run_dir, **common, action="CANDIDATE_ACCEPTED" if accepted else "CANDIDATE_REJECTED",
                     attempt=attempts, candidate=candidate, checker_status=result.get("status"),
                     checker_reason=result.get("reason", ""), checker_detail=result.get("detail", ""))
        if accepted:
            repaired = candidate

    status = "OK" if result.get("status") == "OK" else "NEEDS_HUMAN"
    reason = result.get("reason", "")
    if result.get("status") == "NEEDS_ENV":
        reason = "env: " + str(reason)
    transient = (result.get("status") == "NEEDS_ENV" or result.get("reason") == "checker_error"
                 or provider_reason in TRANSIENT_PROVIDER_FAILURES)
    fields = {"action": "TERMINAL", "status": status, "repaired": repaired is not None,
              "resumable": not transient,
              "attempts": attempts, "model_calls": model_calls, "model_calls_known": model_calls_known,
              "checker_status": result.get("status"), "checker_reason": result.get("reason", ""),
              "reason": reason, "detail": result.get("detail", ""),
              "provider": _provider_name(provider),
              "review_required": status == "NEEDS_HUMAN" or repaired is not None}
    if provider_reason:
        fields["provider_reason"] = provider_reason
    if kind == "formula":
        fields["latex"] = repaired if repaired is not None else original
        if repaired is not None:
            fields["original"] = original
    elif repaired is not None:
        fields.update(original_rows=original, candidate_rows=repaired)
    if repaired is not None:
        fields["evidence"] = _evidence(run_dir, node)
    state.append(run_dir, **common, **fields)
    return status


def process_formula(run_dir, doc, node, provider, run_id=None, input_sha256=None, context_sha256=None):
    return _process(run_dir, doc, node, provider, "formula", run_id, input_sha256, context_sha256)


def process_table(run_dir, doc, node, provider, run_id=None, input_sha256=None, context_sha256=None):
    return _process(run_dir, doc, node, provider, "table", run_id, input_sha256, context_sha256)


def run(sample_path, run_dir, provider, run_id=None):
    """Run one validated layout; a caller may share run_id across several documents."""
    with open(os.path.join(sample_path, "layout.json"), encoding="utf-8") as f:
        layout = json.load(f)
    if not isinstance(layout, dict) or not isinstance(layout.get("nodes"), list):
        raise ValueError("layout must be an object with a nodes array")
    doc = layout.get("doc") or os.path.basename(sample_path.rstrip("/"))
    if not isinstance(doc, str):
        raise ValueError("layout doc must be a string")
    seen = set()
    for node in layout["nodes"]:
        if (not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]
                or not isinstance(node.get("type"), str) or not node["type"]):
            raise ValueError("each node needs a non-empty string id and type")
        if node["id"] in seen:
            raise ValueError("duplicate node id in layout")
        seen.add(node["id"])
    run_id = run_id or state.new_run_id()
    events = state.load_events(run_dir)
    counts = {"OK": 0, "NEEDS_HUMAN": 0}
    state.append(run_dir, run_id=run_id, doc=doc, action="PARSE", nodes=len(layout["nodes"]))
    for node in layout["nodes"]:
        nid = node["id"]
        input_sha256, context_sha256 = node_identity(node, provider)
        common = {"run_id": run_id, "doc": doc, "node_id": nid,
                  "input_sha256": input_sha256, "context_sha256": context_sha256}
        done = state.terminal_event(events, doc, nid, input_sha256, context_sha256)
        if done:
            counts[done["status"]] += 1
            state.append(run_dir, **common, action="SKIP", reason="matching_input_and_context",
                         status=done["status"], reused_run_id=done.get("run_id"), model_calls=0)
            continue
        ntype = node["type"]
        if ntype == "formula":
            status = process_formula(run_dir, doc, node, provider, run_id, input_sha256, context_sha256)
        elif ntype == "table":
            status = process_table(run_dir, doc, node, provider, run_id, input_sha256, context_sha256)
        else:
            status = "OK"
            state.append(run_dir, **common, action="TERMINAL", skill="pass-through", status="OK",
                         type=ntype, validated=False, repaired=False, resumable=True, attempts=0, model_calls=0,
                         reason="unsupported_node_type_not_checked")
        counts[status] += 1
    state.append(run_dir, run_id=run_id, doc=doc, action="DOC_END", counts=counts)
    return doc, counts
