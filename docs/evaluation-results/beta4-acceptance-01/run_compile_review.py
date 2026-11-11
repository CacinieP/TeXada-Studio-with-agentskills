"""Compile the actual UI candidate before and after explicit agent syntax review.

Session authorization stays local and is never written to evidence. No model
request is made; preview compilation and PDF download use the real Studio API.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser()
parser.add_argument('--state-dir', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
STATE = args.state_dir
OUTPUT = args.output
OUTPUT.mkdir(parents=True, exist_ok=False)
record_path = next((STATE / 'imports').glob('*/candidate.json'))
record = json.loads(record_path.read_text())
raw = record['content']
changes = []
kept = []
for number, line in enumerate(raw.splitlines(), 1):
    if line.strip() in ('<table>', '}'):
        changes.append({'line': number, 'removed': line, 'reason': 'model-added wrapper/unmatched brace absent from source'})
    else:
        kept.append(line)
assert len(changes) == 2
corrected = '\n'.join(kept) + '\n'
(OUTPUT / 'raw-candidate.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
(OUTPUT / 'raw-candidate.tex').write_text(raw)
(OUTPUT / 'agent-reviewed.tex').write_text(corrected)
(OUTPUT / 'syntax-review.json').write_text(json.dumps({'reviewer': 'agent-source-comparison-not-independent-human',
    'changes': changes, 'numeric_edits': 0, 'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
    'reviewed_sha256': hashlib.sha256(corrected.encode()).hexdigest(),
    'diff': ''.join(difflib.unified_diff(raw.splitlines(True), corrected.splitlines(True), fromfile='raw-candidate', tofile='agent-reviewed'))},
    ensure_ascii=False, indent=2) + '\n')
session = json.loads((STATE / 'session.json').read_text())
parts = urllib.parse.urlsplit(session['url'])
token = urllib.parse.parse_qs(parts.query)['token'][0]
base = session['base_url']
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(path, body=None):
    url = base + path + ('&' if '?' in path else '?') + urllib.parse.urlencode({'token': token})
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    with opener.open(req, timeout=130) as response:
        return response.read()
results = []
for label, text in [('raw', raw), ('agent-reviewed', corrected)]:
    wire = request('/api/studio/preview', {'name': 'beta4-' + label + '.tex', 'content': text})
    result = json.loads(wire)
    public = json.loads(json.dumps(result).replace(str(STATE), '${STUDIO_STATE}').replace(str(ROOT), '${REPO}'))
    public['transport_evidence'] = {'wire_response_sha256': hashlib.sha256(wire).hexdigest(),
                                    'path_redaction': 'local state/repository prefixes only'}
    (OUTPUT / (label + '-compile.json')).write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
    results.append({'stage': label, 'compile_ok': result['compile_ok'], 'preview_ok': result.get('preview_ok', False)})
    if result['compile_ok']:
        pdf = request(result['pdf'])
        (OUTPUT / (label + '.pdf')).write_bytes(pdf)
        assert pdf.startswith(b'%PDF-')
assert results[0]['compile_ok'] is False
assert results[1]['compile_ok'] is True
(OUTPUT / 'compile-checks.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
