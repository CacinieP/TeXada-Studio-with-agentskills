#!/usr/bin/env python3
"""Audit syntax-accepted research outputs against current source-preservation rules.

This is a deterministic policy audit, never an independent semantic review.
It does not rewrite the original research evidence or change product defaults.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
from docforensics.formula_repair import assess_candidate, repair_blocker


def audit(rows):
    result = {}
    details = []
    for group in ('model_without_skill', 'model_with_skill'):
        selected = [r for r in rows if r['group'] == group and r['initial_checker']['status'] == 'RETRY']
        accepted = [r for r in selected if r['candidate_accepted_by_syntax_checker']]
        rejected = Counter()
        allowed = 0
        for row in accepted:
            original = row['original_latex']
            blocker = repair_blocker(original)
            scope = assess_candidate(original, row['output_latex'])
            safe = blocker is None and scope['allowed']
            allowed += safe
            reason = blocker or scope['reason']
            if not safe:
                rejected[reason] += 1
            details.append({'case_id': row['case_id'], 'group': group,
                            'original_latex': original, 'output_latex': row['output_latex'],
                            'source_preservation_allowed': safe, 'reason': reason})
        result[group] = {'repair_inputs': len(selected), 'syntax_accepted': len(accepted),
                         'source_preservation_allowed': allowed,
                         'syntax_accepted_but_blocked': len(accepted) - allowed,
                         'blocked_reasons': dict(rejected), 'semantic_accuracy': None}
    return {'summary': result, 'accepted_output_policy_audit': details,
            'review_kind': 'deterministic source-preservation policy; not independent semantic review'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    # Reuse evidence checks rather than admitting fixture/incomplete/tampered runs.
    from run_local_repair_control import summarize
    summarize(args.run_dir)
    source = args.run_dir / 'results.jsonl'
    result = audit([json.loads(line) for line in source.read_text().splitlines()])
    result['results_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    result['policy_sha256'] = {name: hashlib.sha256((ROOT / 'harness/docforensics' / name).read_bytes()).hexdigest()
                               for name in ('formula_repair.py', 'tex_context.py')}
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2)


if __name__ == '__main__':
    main()
