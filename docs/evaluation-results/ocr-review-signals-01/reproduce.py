"""Reproduce protocol-fixture extraction -> review bundle; no sockets/models.

Use a fresh output directory. Provider bodies and counters are simulated, not
measurements. Accept decisions identify a synthetic test operator, not a person.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'skills/doc-ocr-extract/scripts'))
import ocr_extract
import ocr_to_layout


def openai(text, finish='stop'):
    return {'choices': [{'message': {'content': text}, 'finish_reason': finish}],
            'usage': {'completion_tokens': 9}}


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=False)
    missing = openai('unconfirmed')
    del missing['choices'][0]['finish_reason']
    refusal = openai(None)
    refusal['choices'][0]['message']['refusal'] = 'fixture refusal'
    cases = [
        ('openai_complete', 'openai', openai('$x+1$')),
        ('ollama_complete', 'ollama', {'message': {'content': '$x+1$'}, 'done': True, 'eval_count': 7}),
        ('length', 'openai', openai('partial fraction', 'length')),
        ('unfinished', 'ollama', {'message': {'content': 'partial'}, 'done': False}),
        ('non_text', 'openai', openai('first\n[Non-text]')),
        ('replacement', 'openai', openai('first\nvalue \ufffd')),
        ('missing_completion', 'openai', missing),
        ('excerpt_only', 'openai', openai('x' * 2048)),
        ('control', 'openai', openai('a\x0bb')),
        ('refusal', 'openai', refusal),
    ]
    source = ROOT / 'samples/ocr/source-regions-01/source.png'
    results = []
    for name, transport, body in cases:
        case = output / name
        case.mkdir()
        (case / 'provider-fixture.json').write_text(json.dumps(body, ensure_ascii=False, indent=2) + '\n')
        stream = io.StringIO()
        def fake_open(request, timeout=None):
            return io.BytesIO(json.dumps(body).encode())
        with patch('urllib.request.urlopen', side_effect=fake_open), contextlib.redirect_stdout(stream):
            extract_exit = ocr_extract.run_record({'id': name, 'image_path': str(source)},
                 model='fixture-not-real-ocr', base='http://127.0.0.1:9', prompt='protocol fixture only',
                 transport=transport)
        record = json.loads(stream.getvalue())
        record_path = case / 'record.json'
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        lines = record.get('lines', record.get('candidate_lines', []))
        review = {'record_sha256': ocr_to_layout.record_digest(record),
                  'reviewer': 'synthetic-protocol-test-operator',
                  'decisions': [{'start_line': i, 'end_line': i, 'action': 'accept', 'type': 'text'}
                                for i in range(1, len(lines) + 1)]}
        review_path = case / 'decisions.json'
        review_path.write_text(json.dumps(review, indent=2) + '\n')
        with contextlib.redirect_stdout(io.StringIO()):
            convert_exit = ocr_to_layout.main([str(record_path), '--review', str(review_path),
                '--doc', 'protocol-' + name, '--output-dir', str(case / 'bundle')])
        complete = name in ('openai_complete', 'ollama_complete', 'excerpt_only')
        assert extract_exit == convert_exit == (0 if complete else 1)
        assert (case / 'bundle/layout.json').exists() is complete
        results.append({'case': name, 'transport': transport, 'extract_exit': extract_exit,
                        'convert_exit': convert_exit, 'layout_created': complete,
                        'reason': record['reason'], 'output_complete': record['output_complete']})
    manifest = {'kind': 'offline_provider_protocol_fixtures_not_model_measurements',
                'baseline_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                'python': platform.python_version(), 'model_requests': 0,
                'source_image': 'samples/ocr/source-regions-01/source.png',
                'source_image_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'results': results,
                'implementation_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in [Path(ocr_extract.__file__), Path(ocr_to_layout.__file__)]}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('10 protocol cases: 3 complete candidates, 7 blocked; zero model/network requests.')


if __name__ == '__main__':
    main()
