"""Reproduce issue #23's bounded MiniCPM5 formula provider probe.

Run from the repository root with the project's Python environment. Outputs are
synthetic; reference answers are used only after inference. No model defaults
are modified. Raw reasoning is never persisted.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'harness'))
from docforensics.vlm import OpenAICompatibleProvider
from docforensics.formula_repair import assess_candidate

CASES = [
    ('closing-brace', r'\frac{a+b}{2', r'\frac{a+b}{2}'),
    ('missing-operand', 'a+b+', None),
    ('unchanged-control', 'a+b', 'a+b'),
]


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    os.environ.pop('VLM_API_KEY', None)
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    def local_json(path):
        with urllib.request.urlopen('http://127.0.0.1:11434' + path, timeout=5) as response:
            return json.load(response)
    tags = local_json('/api/tags')
    model = 'minicpm5-2b:latest'
    identity = next(item for item in tags['models'] if item['name'] == model)
    provider = OpenAICompatibleProvider('http://127.0.0.1:11434/v1', model,
                                       skill_mode='on', max_tokens=1024, seed=0)
    rows = []
    original_chat = provider._chat
    for name, latex, reference in CASES:
        capture = {}
        def chat(prompt, **kwargs):
            capture['messages'] = [{'role': 'system', 'content': provider._system_prompt()},
                                   {'role': 'user', 'content': prompt}]
            response = original_chat(prompt, **kwargs)
            safe = copy.deepcopy(response)
            for choice in safe.get('choices', []):
                for key in ('reasoning', 'reasoning_content'):
                    if key in choice.get('message', {}):
                        value = choice['message'].pop(key)
                        choice['message'][key + '_characters'] = len(value) if isinstance(value, str) else 0
            capture['response'] = safe
            return response
        provider._chat = chat
        candidate = provider.repair_formula({'id': name, 'data': {'latex': latex}}, timeout=30)
        row = {'id': name, 'input': latex, 'reference_after_inference': reference,
               'candidate': candidate, 'trace': copy.deepcopy(provider.last_trace),
               'transport': capture, 'source_policy': assess_candidate(latex, candidate) if candidate else None,
               'reference_match': candidate == reference if reference is not None else None}
        rows.append(row)
        (output / 'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'id': name, 'candidate': candidate, 'reason': row['trace']['reason'],
                          'usage': row['trace']['usage']}, ensure_ascii=False), flush=True)
    manifest = {'commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                'model_identity': identity, 'python': platform.python_version(), 'machine': platform.machine(),
                'provider': provider.fingerprint(), 'timeout_seconds': 30,
                'scope': 'direct provider probe, not host delivery or accuracy benchmark',
                'results_sha256': hashlib.sha256((output / 'results.json').read_bytes()).hexdigest()}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
