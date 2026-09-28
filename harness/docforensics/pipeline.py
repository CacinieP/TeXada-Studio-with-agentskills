"""三态流水线：节点遍历、质检分发、修复循环、断点续跑。

三态协议：OK（通过）/ RETRY（可修复，自动重试 ≤2 次）/ NEEDS_HUMAN（进报告，不阻塞）。
所有决策追加写入 state.jsonl；重跑时已有终态的节点直接跳过（幂等）。
"""

import json
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


def load_provider(args):
    if args.vlm:
        return OllamaProvider(base=args.vlm, model=args.vlm_model)
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
        return {"status": "NEEDS_ENV", "reason": f"verify.py unavailable: {type(exc).__name__}: {exc}"}


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
                "detail": f"audit unavailable: {type(exc).__name__}: {exc}"}


def _evidence(run_dir, node):
    """把原始 crop 复制进 state/crops/ 作为证据；缺 crop 记 None（报告会点名）。"""
    crop = (node.get("data") or {}).get("crop")
    if crop and os.path.exists(crop):
        dst = os.path.join(run_dir, "crops", os.path.basename(crop))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(crop, dst)
        return os.path.relpath(dst, run_dir)
    return None


def process_formula(run_dir, doc, node, provider):
    nid = node["id"]
    original = (node.get("data") or {}).get("latex", "")
    r = run_verify(original)
    attempts = 0
    repaired = None
    while r.get("status") == "RETRY" and attempts < MAX_RETRIES:
        attempts += 1
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-formula-verify",
                     action="RETRY", attempt=attempts, reason=r.get("reason", ""))
        fixed = provider.repair_formula(node)
        if not fixed:
            break
        repaired = fixed
        r = run_verify(fixed)

    if r.get("status") == "OK" and repaired is not None:
        status = "OK"
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-formula-verify", status="OK",
                     repaired=True, original=original, latex=repaired,
                     evidence=_evidence(run_dir, node), provider=provider.name, attempts=attempts)
    elif r.get("status") == "OK":
        status = "OK"
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-formula-verify", status="OK",
                     repaired=False, latex=original, attempts=attempts)
    else:
        status = "NEEDS_HUMAN"
        reason = ("env: " + str(r.get("reason", ""))) if r.get("status") == "NEEDS_ENV" else r.get("reason", "")
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-formula-verify", status="NEEDS_HUMAN",
                     repaired=False, latex=original, reason=reason, attempts=attempts)
    return status


def process_table(run_dir, doc, node, provider):
    nid = node["id"]
    rec = {"id": nid, "rows": node["data"].get("rows"), "expected": node["data"].get("expected", {})}
    r = run_audit(rec)
    attempts = 0
    repaired = None
    while r.get("status") == "RETRY" and attempts < MAX_RETRIES:
        attempts += 1
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-table-audit",
                     action="RETRY", attempt=attempts, reason=r.get("reason", ""))
        rows = provider.repair_table(node)
        if not rows:
            break
        repaired = rows
        r = run_audit({"id": nid, "rows": rows, "expected": node["data"].get("expected", {})})

    if r.get("status") == "OK" and repaired is not None:
        status = "OK"
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-table-audit", status="OK",
                     repaired=True, evidence=_evidence(run_dir, node),
                     original_rows=rec["rows"], candidate_rows=repaired,
                     provider=provider.name, attempts=attempts)
    elif r.get("status") == "OK":
        status = "OK"
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-table-audit", status="OK",
                     repaired=False, attempts=attempts)
    else:
        status = "NEEDS_HUMAN"
        state.append(run_dir, doc=doc, node_id=nid, skill="doc-table-audit", status="NEEDS_HUMAN",
                     repaired=False, reason=r.get("reason", ""), detail=r.get("detail", ""), attempts=attempts)
    return status


def run(sample_path, run_dir, provider):
    """跑一个样本目录（layout.json），返回 (doc, 状态计数)。"""
    with open(os.path.join(sample_path, "layout.json")) as f:
        layout = json.load(f)
    doc = layout.get("doc") or os.path.basename(sample_path.rstrip("/"))
    events = state.load_events(run_dir)
    counts = {"OK": 0, "NEEDS_HUMAN": 0}
    state.append(run_dir, doc=doc, action="PARSE", nodes=len(layout["nodes"]),
                 source=layout.get("source", ""))
    for node in layout["nodes"]:
        nid = node["id"]
        done = state.terminal_state(events, doc, nid)
        if done:
            counts[done] += 1
            state.append(run_dir, doc=doc, node_id=nid, action="SKIP", reason="resume")
            continue
        ntype = node["type"]
        if ntype == "formula":
            st = process_formula(run_dir, doc, node, provider)
        elif ntype == "table":
            st = process_table(run_dir, doc, node, provider)
        else:
            st = "OK"
            state.append(run_dir, doc=doc, node_id=nid, skill="pass-through", status="OK", type=ntype)
        counts[st if st in counts else "NEEDS_HUMAN"] += 1
    return doc, counts
