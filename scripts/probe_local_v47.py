#!/usr/bin/env python3
"""Explicit local model probe: run existing repair arms and one synthetic PNG OCR.

No default endpoint or model: identity and output directory must be supplied.
This is a deployment/contract probe, never an accuracy benchmark.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--model-file', type=Path, required=True)
    parser.add_argument('--projector', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir
    out.mkdir(parents=True, exist_ok=False)
    meta = {'schema_version': 1, 'model': args.model,
            'model_file': args.model_file.name, 'model_sha256': sha256(args.model_file),
            'model_bytes': args.model_file.stat().st_size,
            'projector_file': args.projector.name, 'projector_sha256': sha256(args.projector),
            'base': args.base, 'created_at_unix': time.time(),
            'protocol': 'OpenAI-compatible', 'max_tokens': 4096,
            'purpose': 'deployment and candidate contract probe, semantic accuracy unmeasured'}
    for route in ('health', 'v1/models'):
        try:
            meta[route] = get_json(args.base + '/' + route)
        except Exception as exc:
            meta[route] = {'error_type': type(exc).__name__}
    (out / 'identity.json').write_text(json.dumps(meta, indent=2))
    for catalog, folder in [('smoke_cases.json', 'repair-smoke'),
                            ('active_calculus_cases.json', 'repair-calculus')]:
        cmd = [sys.executable, str(ROOT / 'scripts/evaluate_skills.py'), 'run',
               '--cases', str(ROOT / 'samples/research' / catalog), '--outdir', str(out / folder),
               '--mode', 'model', '--base', args.base, '--model', args.model, '--max-tokens', '4096']
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        (out / (folder + '-process.json')).write_text(json.dumps(
            {'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}, indent=2))
        print(args.model, folder, 'exit', result.returncode, flush=True)
    spec = importlib.util.spec_from_file_location('probe_ocr', ROOT / 'skills/doc-ocr-extract/scripts/ocr_extract.py')
    ocr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ocr)
    image = ROOT / 'samples/ocr/inlines-01.png'
    status, reason, payload = ocr.extract(image.read_bytes(), model=args.model,
        base=args.base, prompt=ocr.DEFAULT_PROMPT, transport='openai', timeout=180)
    (out / 'ocr.json').write_text(json.dumps({'status': status, 'reason': reason,
        'source_sha256': sha256(image), 'review_status': 'pending', **payload}, ensure_ascii=False, indent=2))
    print(args.model, 'OCR', status, reason, flush=True)


if __name__ == '__main__':
    main()
