"""Audit archived responses and run the real CLI with competing model env vars.

Run from repository root after reproduce.py. No additional inference is intended:
the host should use deterministic closing-brace repair and preserve the ambiguous
and valid inputs. This is an agent/machine audit, not independent human review.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
if (BASE / 'host-run').exists():
    raise SystemExit('Use a fresh evidence directory; refusing to overwrite/reuse host-run.')
sys.path.insert(0, str(ROOT / 'harness'))
spec = importlib.util.spec_from_file_location('formula_checker', ROOT / 'skills/doc-formula-verify/scripts/verify.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
results = json.loads((BASE / 'run/results.json').read_text())
checks = []
for row in results:
    status, reason = checker.check(row['candidate'])
    checks.append({'id': row['id'], 'candidate_status': status, 'reason': reason,
                   'source_policy': row['source_policy'],
                   'reference_match': row['reference_match']})
    assert row['trace']['skill_loaded'] and row['trace']['model_calls'] == 1
    assert row['trace']['reason'] == 'ok'
assert [r['candidate_status'] for r in checks] == ['OK', 'RETRY', 'OK']
assert all(row['source_policy']['allowed'] for row in checks)
(BASE / 'audit.json').write_text(json.dumps({'review_type': 'agent_and_machine_not_independent_human',
    'checks': checks, 'additional_repairs_over_deterministic': 0}, ensure_ascii=False, indent=2) + '\n')
input_dir = BASE / 'input'
input_dir.mkdir(exist_ok=True)
(input_dir / 'layout.json').write_text(json.dumps({'doc': 'minicpm5-routing-probe',
    'source': 'original synthetic text; no image/OCR claim',
    'nodes': [{'id': r['id'], 'type': 'formula', 'page': 1, 'data': {'latex': r['input']}} for r in results]},
    ensure_ascii=False, indent=2) + '\n')
env = {**os.environ, 'PYTHONPATH': str(ROOT / 'harness'), 'REPAIR_MODEL': 'minicpm5-2b:latest',
       'VLM_MODEL': 'deliberately-not-selected', 'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost'}
env.pop('VLM_API_KEY', None)
relative = BASE.relative_to(ROOT)
command = [sys.executable, '-m', 'docforensics', 'run', str(relative / 'input'),
           '--state', str(relative / 'host-run'), '--vlm', 'http://127.0.0.1:11434/v1',
           '--skill-mode', 'on', '--max-tokens', '1024']
run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
(BASE / 'cli-stdout.txt').write_text(run.stdout + run.stderr)
assert run.returncode == 0, run.stdout + run.stderr
print(run.stdout)
