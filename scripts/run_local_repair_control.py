#!/usr/bin/env python3
"""Sequential, loopback-only formula experiments; never switches model defaults."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


def summarize(run):
    """Validate completed model evidence before computing descriptive metrics."""
    run = Path(run)
    manifest = json.loads((run / 'manifest.json').read_text())
    if (manifest.get('status') != 'complete' or manifest.get('mode') != 'model'
            or manifest.get('code_changed_during_run')
            or manifest.get('catalog_changed_during_run')
            or manifest.get('controlled_configuration_verified') is not True):
        raise ValueError('requires unchanged, complete, controlled real-model run')
    for name in ('results.jsonl', 'blind-review.csv', 'report.md'):
        if digest(run / name) != manifest['files'][name]:
            raise ValueError('evidence hash mismatch: ' + name)
    rows = [json.loads(line) for line in (run / 'results.jsonl').read_text().splitlines()]
    result = {}
    for group in ('model_without_skill', 'model_with_skill'):
        model_rows = [r for r in rows if r['group'] == group]
        eligible = [r for r in model_rows if r['initial_checker']['status'] == 'RETRY']
        attempts = [a for r in eligible for a in r['attempts']]
        traces = [a['provider_trace'] for a in attempts]
        calls = sum(t.get('model_calls', 0) for t in traces)
        reasons = Counter(t.get('reason', 'missing') for t in traces)
        result[group] = {
            'repair_inputs': len(eligible), 'http_attempts': calls,
            'initial_ok_skipped': sum(r['initial_checker']['status'] == 'OK' for r in model_rows),
            'strict_contract_candidates': reasons['ok'],
            'strict_contract_rate_all_http_attempts': reasons['ok'] / calls if calls else None,
            'checker_accepted_inputs': sum(r['candidate_accepted_by_syntax_checker'] for r in eligible),
            'checker_rate_all_retry_inputs': sum(r['candidate_accepted_by_syntax_checker'] for r in eligible) / len(eligible) if eligible else None,
            'failure_reasons': dict(reasons),
            'finish_reasons': dict(Counter(str(t.get('finish_reason')) for t in traces)),
            'reasoning_characters': sum(t.get('reasoning_characters', 0) for t in traces),
            'repair_seconds_p50': percentile([r['elapsed_seconds'] for r in eligible], .5),
            'repair_seconds_p95': percentile([r['elapsed_seconds'] for r in eligible], .95),
            'repair_seconds_p99': percentile([r['elapsed_seconds'] for r in eligible], .99),
            'semantic_accuracy': None,
            'default_switch_approved': False,
            'gate_status': 'pending independent semantic review, eligibility adjudication and larger sample'}
    return result


def run(args):
    endpoint = urlsplit(args.base)
    if (endpoint.scheme != 'http' or endpoint.hostname not in {'127.0.0.1', '::1', 'localhost'}
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
            or endpoint.path.rstrip('/') not in {'', '/v1'}):
        raise ValueError('use a loopback HTTP service root or /v1 endpoint')
    base = args.base.rstrip('/')
    models_url = base + ('/models' if endpoint.path.rstrip('/') == '/v1' else '/v1/models')
    with urlopen(models_url, timeout=5) as response:
        models = json.load(response)
    if args.model not in {m.get('id') for m in models.get('data', [])}:
        raise ValueError('requested alias is not advertised by local server')
    # Hash the full weight before running; record backend explicitly, never infer hardware.
    identity = {'model': args.model, 'model_sha256': digest(args.model_file),
                'model_bytes': args.model_file.stat().st_size,
                'backend_version': args.backend_version, 'base': base,
                'reasoning_configuration': args.reasoning_configuration,
                'hardware_note': args.hardware_note, 'phase': args.phase,
                'repeats': args.repeats, 'request_concurrency': 1,
                'cold_load_seconds': None, 'cold_load_status': 'measure separately from server startup logs',
                'ttft_seconds': None, 'ttft_status': 'not measured by nonstreaming runner',
                'schema_enforcement': 'requested only; validate backend implementation/logs separately',
                'semantic_accuracy': None, 'default_switch_approved': False}
    frozen = {str(p.relative_to(ROOT)): digest(p) for p in (
        Path(__file__), ROOT / 'scripts/evaluate_skills.py',
        ROOT / 'harness/docforensics/vlm.py',
        ROOT / 'samples/research/smoke_cases.json',
        ROOT / 'samples/research/active_calculus_cases.json')}
    args.outdir.mkdir(parents=True, exist_ok=False)
    (args.outdir / 'identity.json').write_text(json.dumps(identity, indent=2))
    cells = [(1024, 'text'), (4096, 'text')] if args.phase == 'budget' else [
        (args.budget, 'text'), (args.budget, 'json_schema')]
    summaries = []
    for repeat in range(args.repeats):
        # Alternate condition order to reduce consistent first-condition bias.
        for budget, fmt in cells[::1 if repeat % 2 == 0 else -1]:
            for catalog in ('smoke', 'active_calculus'):
                out = args.outdir / f'{repeat + 1}-{budget}-{fmt}-{catalog}'
                command = [sys.executable, str(ROOT / 'scripts/evaluate_skills.py'), 'run',
                           '--cases', str(ROOT / f'samples/research/{catalog}_cases.json'),
                           '--outdir', str(out), '--mode', 'model', '--base', base,
                           '--model', args.model, '--seed', '0', '--max-tokens', str(budget),
                           '--formula-response-format', fmt]
                completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                (args.outdir / (out.name + '-process.json')).write_text(json.dumps({
                    'exit_code': completed.returncode, 'stdout': completed.stdout,
                    'stderr': completed.stderr}, indent=2))
                # Preserve failures and stop; never silently drop a broken condition.
                metrics = summarize(out)
                summaries.append({'run': out.name, 'budget': budget, 'format': fmt,
                                  'repeat': repeat + 1, 'catalog': catalog, 'metrics': metrics})
                (args.outdir / 'summary.json').write_text(json.dumps(summaries, indent=2))
                print(out.name, 'exit', completed.returncode, flush=True)
                if completed.returncode:
                    raise ValueError('environment/process failure; evidence preserved, matrix stopped')
                if any(digest(ROOT / name) != sha for name, sha in frozen.items()):
                    raise ValueError('matrix implementation/catalog changed; do not compare runs')
    identity['frozen_files'] = frozen
    identity['status'] = 'complete'
    (args.outdir / 'identity.json').write_text(json.dumps(identity, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--model-file', required=True, type=Path)
    parser.add_argument('--backend-version', required=True)
    parser.add_argument('--reasoning-configuration', required=True)
    parser.add_argument('--hardware-note', default='unrecorded; not a hardware benchmark')
    parser.add_argument('--outdir', required=True, type=Path)
    parser.add_argument('--phase', choices=('budget', 'format'), required=True)
    parser.add_argument('--budget', choices=(1024, 4096), type=int, default=1024)
    parser.add_argument('--repeats', type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
