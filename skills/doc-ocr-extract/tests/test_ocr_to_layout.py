"""Review binding, loss prevention and real harness resume; no OCR/model calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr_to_layout as converter


def record(lines=None):
    return {'id': 'synthetic-page', 'status': 'OK', 'model': 'fixture-not-real-ocr',
            'lines': lines or [r'$\frac{1}{2}$', 'Title', 'item|amount', 'A|1', 'B|2', 'total|3', 'a+b+']}


def decision(start, end, kind):
    return {'start_line': start, 'end_line': end, 'action': 'accept', 'type': kind,
            **({'separator': 'pipe'} if kind == 'table' else {})}


def review(source):
    return {'record_sha256': converter.record_digest(source), 'reviewer': 'synthetic-test-operator',
            'decisions': [decision(1, 1, 'formula'), decision(2, 2, 'text'),
                          decision(3, 6, 'table'), decision(7, 7, 'formula')]}


class LayoutTest(unittest.TestCase):
    def test_no_review_only_produces_pending_items(self):
        result = converter.convert(record(), doc='sample')
        self.assertIsNone(result['layout'])
        self.assertEqual(len(result['review_items']), 7)
        self.assertEqual(result['status'], 'NEEDS_HUMAN')

    def test_explicit_types_preserve_source_and_have_stable_ids(self):
        source = record()
        before = copy.deepcopy(source)
        result = converter.convert(source, review(source), doc='sample', page=2)
        self.assertEqual(source, before)
        self.assertEqual(result['status'], 'OK')
        nodes = result['layout']['nodes']
        self.assertEqual([n['type'] for n in nodes], ['formula', 'text', 'table', 'formula'])
        self.assertEqual(nodes[0]['data'], {'latex': r'\frac{1}{2}'})
        self.assertEqual(nodes[0]['ocr_source']['text'], [r'$\frac{1}{2}$'])
        self.assertEqual(nodes[2]['data']['rows'][-1], ['total', '3'])
        self.assertTrue(all(n['page'] == 2 for n in nodes))
        reversed_review = review(source)
        reversed_review['decisions'].reverse()
        self.assertEqual(result, converter.convert(source, reversed_review, doc='sample', page=2))

    def test_changed_content_or_metadata_invalidates_review(self):
        source = record()
        signed = review(source)
        for key, value in [('lines', ['different']), ('model', 'new-model'), ('id', 'new-page')]:
            changed = {**source, key: value}
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'stale_review'):
                converter.convert(changed, signed, doc='sample')

    def test_partial_review_never_emits_partial_layout(self):
        source = record()
        signed = review(source)
        signed['decisions'].pop()
        result = converter.convert(source, signed, doc='sample')
        self.assertIsNone(result['layout'])
        self.assertEqual(result['review_items'][0]['line'], 7)

    def test_reject_requires_reason_and_retains_excluded_source(self):
        source = record()
        signed = review(source)
        signed['decisions'][-1] = {'start_line': 7, 'end_line': 7, 'action': 'reject'}
        with self.assertRaisesRegex(ValueError, 'rejection_reason'):
            converter.convert(source, signed, doc='sample')
        signed['decisions'][-1]['reason'] = 'not part of this document'
        result = converter.convert(source, signed, doc='sample')
        self.assertEqual(result['status'], 'OK')
        self.assertEqual(len(result['layout']['nodes']), 3)
        self.assertEqual(result['rejected_lines'][0]['text'], ['a+b+'])

    def test_all_rejected_does_not_look_like_a_successful_document(self):
        source = record()
        signed = {**review(source), 'decisions': [{'start_line': 1, 'end_line': 7,
                  'action': 'reject', 'reason': 'unusable page'}]}
        self.assertIsNone(converter.convert(source, signed, doc='sample')['layout'])

    def test_overlapping_ranges_and_boolean_indices_fail(self):
        source = record()
        signed = review(source)
        signed['decisions'].append(decision(1, 1, 'text'))
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            converter.convert(source, signed, doc='sample')
        signed = review(source)
        signed['decisions'][0]['start_line'] = True
        with self.assertRaises(ValueError):
            converter.convert(source, signed, doc='sample')

    def test_no_heuristic_type_selection(self):
        source = record()
        signed = review(source)
        del signed['decisions'][0]['type']
        with self.assertRaisesRegex(ValueError, 'explicit_node_type'):
            converter.convert(source, signed, doc='sample')

    def test_ambiguous_or_nonrectangular_tables_return_review_items(self):
        for lines in [['x|y', '1|2|3'], ['x|y', '---|---'], ['x|y', r'a\|b|2'], ['xy', '12']]:
            source = record(lines)
            signed = {'record_sha256': converter.record_digest(source), 'reviewer': 'fixture',
                      'decisions': [decision(1, 2, 'table')]}
            result = converter.convert(source, signed, doc='sample')
            self.assertIsNone(result['layout'])
            self.assertEqual(len(result['review_items']), 1)

    def test_tab_table_and_formula_wrappers(self):
        self.assertEqual(converter._table(['x\ty', '1\t2'], 'tab'), [['x', 'y'], ['1', '2']])
        for value in [r'\[x+1\]', r'\(x+1\)', '$$x+1$$', '$x+1$', 'x+1']:
            self.assertEqual(converter._formula(value), 'x+1')

    def test_multiple_math_spans_are_not_stripped_as_one_formula(self):
        source = record(['$a$ + $b$'])
        signed = {'record_sha256': converter.record_digest(source), 'reviewer': 'fixture',
                  'decisions': [decision(1, 1, 'formula')]}
        result = converter.convert(source, signed, doc='sample')
        self.assertIsNone(result['layout'])
        self.assertEqual(result['review_items'][0]['reason'], 'multiple_math_spans_require_review')

    def test_bad_status_is_review_not_layout(self):
        for status in ('NEEDS_ENV', 'NEEDS_HUMAN', None):
            result = converter.convert({'status': status}, doc='sample')
            self.assertIsNone(result['layout'])
            self.assertEqual(result['review_items'][0]['reason'], 'ocr_not_ok')

    def test_invalid_document_ids_lines_and_page_are_rejected(self):
        for doc in ('../escape', '/absolute', '.', '..', ''):
            with self.assertRaises(ValueError):
                converter.convert(record(), doc=doc)
        for lines in ([4], ['a\nb'], ['a\x00b'], [''], ['x'] * (converter.MAX_LINES + 1)):
            with self.assertRaises(ValueError):
                converter.convert(record(lines), doc='sample')
        with self.assertRaises(ValueError):
            converter.convert(record(), doc='sample', page=True)

    def test_cli_preserves_existing_output_and_rejects_ambiguous_json(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'ocr.json'
            source.write_text(json.dumps(record()))
            output = base / 'draft'
            args = [str(source), '--doc', 'sample', '--output-dir', str(output)]
            self.assertEqual(converter.main(args), 1)
            self.assertFalse((output / 'layout.json').exists())
            sentinel = (output / 'review.json').read_bytes()
            self.assertEqual(converter.main(args), 2)
            self.assertEqual((output / 'review.json').read_bytes(), sentinel)
            source.write_text('{"status":"OK","status":"NEEDS_ENV"}')
            self.assertEqual(converter.main([str(source), '--doc', 'sample', '--output-dir', str(base / 'bad')]), 2)
            self.assertFalse((base / 'bad').exists())

    def test_real_cli_checks_and_resumes_reviewed_sample(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = record()
            sample = base / 'sample'
            record_path, review_path = base / 'ocr.json', base / 'decisions.json'
            record_path.write_text(json.dumps(source))
            review_path.write_text(json.dumps(review(source)))
            self.assertEqual(converter.main([str(record_path), '--review', str(review_path),
                             '--doc', 'reviewed-ocr', '--output-dir', str(sample)]), 0)
            state = base / 'state'
            env = {**os.environ, 'PYTHONPATH': str(ROOT / 'harness')}
            command = [sys.executable, '-m', 'docforensics', 'run', str(sample), '--state', str(state)]
            first = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn('OK=3 NEEDS_HUMAN=1', first.stdout)
            second = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(second.returncode, 0, second.stderr)
            events = [json.loads(line) for line in (state / 'state.jsonl').read_text().splitlines()]
            skips = [e for e in events if e['action'] == 'SKIP']
            self.assertEqual(len(skips), 4)
            text = next(e for e in events if e['action'] == 'TERMINAL' and e['node_id'] == 'ocr-0002-0002')
            self.assertFalse(text['validated'])
            self.assertFalse(any(e['action'] == 'PROVIDER_START' for e in events))


if __name__ == '__main__':
    unittest.main()
