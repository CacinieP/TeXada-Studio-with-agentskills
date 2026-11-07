#!/usr/bin/env python3
"""Run the real guarded formula pipeline on a frozen external-input catalog.

No references/adjudication labels enter model requests. Semantic decisions are
left for independent review; syntax and source-policy evidence are separate.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'harness'))
from docforensics import pipeline, state
from docforensics.vlm import FixtureProvider, OpenAICompatibleProvider
from evaluate_skills import read_catalog
from run_local_repair_control import digest


def run_case(directory, case, provider):
    node = {'id': case['id'], 'type': 'formula', 'data': {'latex': case['original_latex']}}
    started = time.monotonic()
    pipeline.process_formula(str(directory), 'external-inputs', node, provider)
    events = [e for e in state.load_events(directory) if e.get('node_id') == case['id']]
    terminal = [e for e in events if e.get('action') == 'TERMINAL'][-1]
    return {'case_id': case['id'], 'input_sha256': hashlib.sha256(case['original_latex'].encode()).hexdigest(),
            'original_latex': case['original_latex'], 'output_latex': terminal['latex'],
            'status': terminal['status'], 'reason': terminal['reason'],
            'repaired': terminal['repaired'], 'review_required': terminal['review_required'],
            'model_calls': terminal['model_calls'], 'elapsed_seconds': time.monotonic() - started,
            'semantic_verdict': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--baseline-root', type=Path, required=True)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--base', default='http://127.0.0.1:18149')
    parser.add_argument('--model', default='minicpm-v4.7-35b-a3b-q4')
    args = parser.parse_args()
    if args.base != 'http://127.0.0.1:18149':
        parser.error('use isolated loopback experiment service on port 18149')
    catalog = read_catalog(args.cases)
    providers = {'deterministic': FixtureProvider(),
                 'skill_1_0': OpenAICompatibleProvider(args.base, args.model, skill_mode='on',
                     skill_root=args.baseline_root, max_tokens=1024),
                 'skill_1_1': OpenAICompatibleProvider(args.base, args.model, skill_mode='on',
                     skill_root=args.candidate_root, max_tokens=1024)}
    fingerprints = {name: p.fingerprint() for name, p in providers.items()}
    frozen = {str(p): digest(p) for p in [args.cases.resolve(), Path(__file__).resolve(),
        ROOT / 'harness/docforensics/pipeline.py', ROOT / 'harness/docforensics/formula_repair.py',
        ROOT / 'harness/docforensics/tex_context.py', ROOT / 'harness/docforensics/vlm.py',
        args.baseline_root / 'doc-formula-verify/SKILL.md',
        args.candidate_root / 'doc-formula-verify/SKILL.md']}
    args.outdir.mkdir(parents=True, exist_ok=False)
    manifest = {'status': 'running', 'catalog_sha256': digest(args.cases),
                'dataset_id': catalog['dataset_id'], 'provider_fingerprints': fingerprints,
                'frozen_files': frozen, 'semantic_accuracy': None,
                'purpose': 'actual host pipeline; external source excerpt sample; independent review pending'}
    (args.outdir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    rows = []
    arms = list(providers)
    for index, case in enumerate(catalog['cases']):
        for name in arms[index % 3:] + arms[:index % 3]:
            if any(digest(path) != sha for path, sha in frozen.items()):
                raise ValueError('frozen input/implementation/Skill changed')
            row = {'arm': name, **run_case(args.outdir / name, case, providers[name])}
            rows.append(row)
            with (args.outdir / 'results.jsonl').open('a') as stream:
                stream.write(json.dumps(row) + '\n')
            print(name, case['id'], row['status'], row['reason'], 'calls', row['model_calls'], flush=True)
    # Review IDs do not reveal the arm. The mapping remains with experiment data.
    review_rows = []
    for row in rows:
        rid = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:24]
        row['review_id'] = rid
        case = next(c for c in catalog['cases'] if c['id'] == row['case_id'])
        review_rows.append({'review_id': rid, 'case_id': row['case_id'],
            'original_latex': row['original_latex'], 'candidate_latex': row['output_latex'],
            'source_url': case['source']['url'], 'verdict': '', 'reviewer': '',
            'independent_review': '', 'notes': ''})
    review_rows.sort(key=lambda r: r['review_id'])
    with (args.outdir / 'blind-review.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(review_rows[0]))
        writer.writeheader(); writer.writerows(review_rows)
    (args.outdir / 'results.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    manifest['status'] = 'complete'
    manifest['summary'] = {name: {'inputs': sum(r['arm'] == name for r in rows),
        'repaired': sum(r['repaired'] for r in rows if r['arm'] == name),
        'human_review': sum(r['status'] == 'NEEDS_HUMAN' for r in rows if r['arm'] == name),
        'model_calls': sum(r['model_calls'] for r in rows if r['arm'] == name),
        'semantic_accuracy': None} for name in arms}
    manifest['files'] = {str(p.relative_to(args.outdir)): digest(p)
                         for p in args.outdir.rglob('*') if p.is_file() and p.name != 'manifest.json'}
    (args.outdir / 'manifest.json').write_text(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
