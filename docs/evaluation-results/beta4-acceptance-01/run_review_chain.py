"""Real OCR archive -> explicit delimiter-only review -> real harness/resume.

Coordinates come from the authored PDF's reference text geometry, not an OCR
region detector or an independent person. This script makes no model requests.
"""
import argparse
import contextlib
import copy
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'skills/doc-ocr-extract/scripts'))
sys.path.insert(0, str(ROOT / 'harness'))
import ocr_to_layout
from docforensics import __main__ as cli, state
from docforensics.vlm import FixtureProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--record', type=Path, default=ROOT / 'docs/evaluation-results/beta4-acceptance-01/cli-ocr/record.json')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'samples/ocr/beta4-acceptance'
    raw_path = args.record
    raw = json.loads(raw_path.read_text())
    assert raw['status'] == 'OK' and len(raw['lines']) == 13
    assert raw['lines'][7:11] == ['Item Units', 'Alpha 12', 'Beta 7', 'total 20']
    _, image = ocr_to_layout.read_source_image(source / 'page.png')
    geometry = ET.parse(source / 'geometry.xhtml').getroot()
    page = next(e for e in geometry.iter() if e.tag.endswith('page'))
    sx, sy = image['width'] / float(page.attrib['width']), image['height'] / float(page.attrib['height'])
    lines = [e for e in page.iter() if e.tag.endswith('line')]
    def text(line):
        return ' '.join(e.text or '' for e in line)
    def find(value):
        return next(line for line in lines if text(line) == value)
    def bounds(items, padding=2):
        return [max(0, math.floor((min(float(e.attrib['xMin']) for e in items) - padding) * sx)),
                max(0, math.floor((min(float(e.attrib['yMin']) for e in items) - padding) * sy)),
                min(image['width'], math.ceil((max(float(e.attrib['xMax']) for e in items) + padding) * sx)),
                min(image['height'], math.ceil((max(float(e.attrib['yMax']) for e in items) + padding) * sy))]
    def between(first, last):
        low, high = float(find(first).attrib['yMax']), float(find(last).attrib['yMin'])
        return [line for line in lines if float(line.attrib['yMin']) > low and float(line.attrib['yMax']) < high]
    decisions = []
    for number in (1, 2, 3, 5, 7, 12, 13):
        decisions.append({'start_line': number, 'end_line': number, 'action': 'accept', 'type': 'text',
                          'bbox': bounds([find(raw['lines'][number - 1])])})
    decisions += [
        {'start_line': 4, 'end_line': 4, 'action': 'accept', 'type': 'formula',
         'bbox': bounds(between('Formula A', 'Formula B'))},
        {'start_line': 6, 'end_line': 6, 'action': 'accept', 'type': 'formula',
         'bbox': bounds(between('Formula B', 'Reference table'))},
        {'start_line': 8, 'end_line': 11, 'action': 'accept', 'type': 'table', 'separator': 'pipe',
         'bbox': bounds(between('Reference table', 'Printed values are source data.'), padding=8)}]
    review = {'record_sha256': ocr_to_layout.record_digest(raw),
              'source_image_sha256': image['sha256'], 'reviewer': 'agent-source-comparison-not-independent-human',
              'coordinate_origin': 'authored PDF reference geometry; not OCR detection',
              'decisions': sorted(decisions, key=lambda d: d['start_line'])}
    def save(name, data):
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    save('raw-review-plan.json', review)
    blocked = ocr_to_layout.convert(raw, review, doc='beta4-source', source_image=image)
    assert blocked['layout'] is None
    save('raw-table-blocked.json', blocked)
    normalized = copy.deepcopy(raw)
    normalized['id'] += '-agent-delimiter-review'
    normalized['record_kind'] = 'agent-reviewed-format-normalization-not-model-output'
    normalized['normalization'] = {'original_record_sha256': ocr_to_layout.record_digest(raw),
        'operator': review['reviewer'], 'changes': []}
    for index, after in zip(range(7, 11), ['Item|Units', 'Alpha|12', 'Beta|7', 'total|20']):
        normalized['normalization']['changes'].append({'line': index + 1, 'before': raw['lines'][index],
            'after': after, 'reason': 'explicit delimiter only; printed values unchanged'})
        normalized['lines'][index] = after
    save('reviewed-record.json', normalized)
    review['record_sha256'] = ocr_to_layout.record_digest(normalized)
    save('review-plan.json', review)
    with contextlib.redirect_stdout(io.StringIO()):
        assert ocr_to_layout.main([str(args.output / 'reviewed-record.json'), '--review', str(args.output / 'review-plan.json'),
            '--source-image', str(source / 'page.png'), '--doc', 'beta4-source',
            '--output-dir', str(args.output / 'reviewed')]) == 0
    run_dir = args.output / 'host-run'
    command = [sys.executable, '-m', 'docforensics', 'run', str(args.output / 'reviewed'), '--state', str(run_dir)]
    env = {**os.environ, 'PYTHONPATH': str(ROOT / 'harness')}
    results = []
    for label in ('first', 'resume', 'changed-image'):
        image_path = args.output / 'reviewed/source.png'
        original = image_path.read_bytes()
        if label == 'changed-image':
            image_path.write_bytes(original + b'changed-source-test')
        try:
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        finally:
            if label == 'changed-image':
                image_path.write_bytes(original)
        assert run.returncode == (2 if label == 'changed-image' else 0)
        results.append({'case': label, 'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr})
    save('cli-results.json', results)
    events = state.load_events(run_dir)
    assert sum(e['action'] == 'SKIP' for e in events) == 10
    assert sum(e.get('model_calls', 0) or 0 for e in events if e['action'] == 'PROVIDER_RESULT') == 0
    good_run = next(e['run_id'] for e in reversed(events) if e['action'] == 'RUN_END')
    cli.write_run_report(str(run_dir), FixtureProvider(), events, good_run)
    save('checks.json', {'kind': 'agent_source_comparison_not_independent_human',
        'printed_table_total': '20', 'arithmetic_sum': '19', 'printed_total_preserved': True,
        'raw_layout_blocked': True, 'normalization': 'delimiters only; zero numeric changes',
        'reference_geometry_source': 'authored PDF / pdftotext', 'resume_skips': 10,
        'changed_image_exit': 2, 'harness_model_http_requests': 0,
        'terminals': [{k: e.get(k) for k in ('node_id', 'status', 'checker_reason', 'validated', 'latex')}
                      for e in events if e['action'] == 'TERMINAL']})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
