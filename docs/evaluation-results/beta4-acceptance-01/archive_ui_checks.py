"""Archive the completed, agent-driven UI decisions and exports without session secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--state-dir', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
session = json.loads((args.state_dir / 'session.json').read_text())
token = urllib.parse.parse_qs(urllib.parse.urlsplit(session['url']).query)['token'][0]
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(path):
    url = session['base_url'] + path + ('&' if '?' in path else '?') + urllib.parse.urlencode({'token': token})
    with opener.open(url, timeout=20) as response:
        wire = response.read()
    body = json.loads(wire)
    public = json.loads(json.dumps(body).replace(str(args.state_dir), '${STUDIO_STATE}'))
    return public, hashlib.sha256(wire).hexdigest()
jobs, _ = get('/api/studio/jobs')
selected = [job for job in jobs['jobs'] if job['name'] == 'beta4-reviewed.tex']
assert len(selected) == 2
counts, decisions = [], []
for job in selected:
    data, wire_sha = get('/api/studio/fixstatus?id=' + job['id'])
    assert data['done'] and not data['error']
    assert data['result']['model_calls'] == 0
    assert len(data['result']['edits']) == 1
    decisions.append(data['review']['decision'])
    counts.append(data['result']['model_calls'])
    data['transport_evidence'] = {'wire_response_sha256': wire_sha, 'local_path_prefixes_redacted': True}
    (args.output / ('job-' + job['id'] + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
assert sorted(decisions) == ['accept', 'reject']
file, wire_sha = get('/api/studio/file?name=beta4-reviewed.tex')
final_tex = (args.output / 'final-reviewed.tex').read_text()
assert file['content'] == final_tex
assert re.search(r'total\s*&\s*19', final_tex)
assert not re.search(r'total\s*&\s*20', final_tex)
pdf = args.output / 'final-reviewed.pdf'
text = subprocess.check_output(['pdftotext', str(pdf), '-'], text=True)
assert all(value in text for value in ['Alpha', '12', 'Beta', '7', 'total', '19'])
summary = {'kind': 'real_ui_agent_automation_not_independent_human_review',
    'observations': {'ocr_dialog_requires_explicit_create': True, 'user_documents_before_create': [],
       'raw_candidate_compile_ok': False, 'agent_syntax_review_compile_ok': True,
       'syntax_review_numeric_edits': 0, 'rejected_total_preserved': '20',
       'accepted_repair_total': '19', 'saved_and_reloaded': True,
       'pdf_and_tex_downloaded_via_ui': True},
    'automation_note': 'Initial rejection assertion ran before async completion; final check waited for the completed review hint and passed.',
    'decision_actor': 'agent exercising UI on original synthetic source; not a named human',
    'job_decisions': decisions, 'job_model_http_requests': counts,
    'final_source_sha256': hashlib.sha256(final_tex.encode()).hexdigest(),
    'final_pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'file_response_wire_sha256': wire_sha,
    'printed_source_total': '20', 'arithmetic_sum': '19',
    'note': 'Changing 20 to 19 is an explicit accepted arithmetic repair, not OCR fidelity or source copying.'}
(args.output / 'ui-checks.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
(args.output / 'final-pdf-text.txt').write_text(text)
print(json.dumps({'decisions': decisions, 'repair_model_http_requests': counts, 'exports_verified': True}))
