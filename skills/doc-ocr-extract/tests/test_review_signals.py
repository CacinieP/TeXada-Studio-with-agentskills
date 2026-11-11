"""Objective OCR review signals, never confidence or model-quality measurements."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr_extract
import ocr_to_layout
import test_ocr_extract as extract_fixtures
from test_ocr_extract import PNG_1X1, endpoint, openai_body, ollama_body


class ReviewSignalTest(unittest.TestCase):
    call = extract_fixtures.ExtractTest.call

    def test_openai_length_retains_partial_text_only_as_diagnostics(self):
        body = openai_body('first line\npartial frac')
        body['choices'][0]['finish_reason'] = 'length'
        status, reason, payload, _ = self.call(body=body)
        self.assertEqual((status, reason), ('NEEDS_HUMAN', 'incomplete_output'))
        self.assertFalse(payload['output_complete'])
        self.assertNotIn('lines', payload)
        self.assertEqual(payload['candidate_lines'], ['first line', 'partial frac'])
        self.assertEqual(payload['finish_reason'], 'length')

    def test_native_length_or_unfinished_response_is_not_a_success(self):
        for extra in ({'done_reason': 'length'}, {'done': False}):
            body = {**ollama_body('partial'), **extra}
            status, reason, payload, _ = self.call(body=body, transport='ollama')
            self.assertEqual((status, reason), ('NEEDS_HUMAN', 'incomplete_output'))
            self.assertFalse(payload['output_complete'])

    def test_missing_or_unrecognized_completion_requires_review(self):
        for transport, body in [('openai', openai_body('text')), ('ollama', ollama_body('text'))]:
            if transport == 'openai':
                del body['choices'][0]['finish_reason']
            else:
                del body['done']
            status, reason, payload, _ = self.call(body=body, transport=transport)
            self.assertEqual((status, reason), ('NEEDS_HUMAN', 'completion_unconfirmed'))
            self.assertIsNone(payload['output_complete'])
        body = openai_body('tool output')
        body['choices'][0]['finish_reason'] = 'tool_calls'
        self.assertEqual(self.call(body=body)[1], 'completion_unconfirmed')

    def test_refusal_and_content_filter_are_explicit_review_reasons(self):
        body = openai_body(None)
        body['choices'][0]['message']['refusal'] = 'not transcribed'
        self.assertEqual(self.call(body=body)[:2], ('NEEDS_HUMAN', 'refused_output'))
        body = openai_body('filtered')
        body['choices'][0]['finish_reason'] = 'content_filter'
        self.assertEqual(self.call(body=body)[:2], ('NEEDS_HUMAN', 'refused_output'))

    def test_non_text_sentinels_are_not_promoted_or_silently_removed(self):
        for text in ('[Non-text]', '[NO TEXT]', 'real line\n[Non-text]'):
            status, reason, payload, _ = self.call(text=text)
            self.assertEqual((status, reason), ('NEEDS_HUMAN', 'non_text_marker'))
            marker = payload['review_items'][0]
            self.assertEqual(marker['scope'], 'line')
            self.assertEqual(marker['line'], 2 if text.startswith('real') else 1)
            self.assertNotIn('lines', payload)
            self.assertEqual(payload['candidate_lines'], text.splitlines())
        # An ordinary sentence is not a protocol sentinel.
        self.assertEqual(self.call(text='Label [Non-text] is printed literally')[0], 'OK')

    def test_replacement_glyph_marks_its_line_without_inventing_a_score(self):
        status, reason, payload, _ = self.call(text='first\namount \ufffd')
        self.assertEqual((status, reason), ('NEEDS_HUMAN', 'replacement_character'))
        self.assertEqual(payload['review_items'][0]['line'], 2)
        self.assertNotIn('confidence', json.dumps(payload))

    def test_controls_are_checked_before_splitlines_can_erase_them(self):
        for char in ('\x00', '\x0b', '\x0c', '\x7f'):
            status, reason, payload, _ = self.call(text='a' + char + 'b')
            self.assertEqual((status, reason), ('NEEDS_HUMAN', 'control_character'))
            self.assertNotIn('lines', payload)
        self.assertEqual(self.call(text='item\tamount\r\nA\t1')[0], 'OK')

    def test_excerpt_truncation_is_not_generation_truncation(self):
        status, reason, payload, _ = self.call(text='x' * 2048)
        self.assertEqual((status, reason), ('OK', ''))
        self.assertTrue(payload['response_truncated'])
        self.assertTrue(payload['output_complete'])
        self.assertEqual(payload['review_items'], [])
        self.assertEqual(len(payload['lines'][0]), 2048)

    def test_text_caps_keep_bounded_diagnostics_not_partial_success_lines(self):
        with patch.object(ocr_extract, 'MAX_LINES', 2), patch.object(ocr_extract, 'MAX_LINE_CHARS', 4):
            status, reason, payload, _ = self.call(text='12345\nb\nc')
        self.assertEqual((status, reason), ('NEEDS_HUMAN', 'text_limits_exceeded'))
        self.assertEqual(payload['candidate_lines'], ['1234', 'b'])
        self.assertTrue(payload['candidate_lines_truncated'])
        self.assertNotIn('lines', payload)

    def test_malformed_shape_is_bounded_and_optional_usage_cannot_crash_parser(self):
        for body in ([], False, {'choices': []}, {'choices': [{'message': []}]},
                     {'choices': [{'message': {'content': 'x'}, 'finish_reason': {}}]}):
            self.assertEqual(self.call(body=body)[:2], ('NEEDS_ENV', 'bad_response_shape'))
        for usage in ('wrong', [], True, {'completion_tokens': True}, {'completion_tokens': -1}):
            body = openai_body('good text')
            body['usage'] = usage
            status, _, payload, _ = self.call(body=body)
            self.assertEqual(status, 'OK')
            self.assertIsNone(payload['eval_count'])
        self.assertEqual(self.call(body={'message': []}, transport='ollama')[:2],
                         ('NEEDS_ENV', 'bad_response_shape'))

    def test_converter_preserves_causes_and_cannot_acknowledge_partial_output_into_layout(self):
        body = openai_body('partial')
        body['choices'][0]['finish_reason'] = 'length'
        status, reason, payload, _ = self.call(body=body)
        record = {'status': status, 'reason': reason, **payload}
        review = {'record_sha256': ocr_to_layout.record_digest(record), 'reviewer': 'fixture',
                  'acknowledge_signals': True,
                  'decisions': [{'start_line': 1, 'end_line': 1, 'action': 'accept', 'type': 'text'}]}
        result = ocr_to_layout.convert(record, review, doc='partial')
        self.assertIsNone(result['layout'])
        self.assertEqual(result['review_items'][0]['ocr_reason'], 'incomplete_output')
        self.assertEqual(result['diagnostic_excerpt'], 'partial')
        self.assertFalse(result['diagnostic_excerpt_truncated'])
        self.assertIn('incomplete_output', [item['reason'] for item in result['review_items']])

    def test_success_label_does_not_override_review_signals_or_incomplete_metadata(self):
        base = {'status': 'OK', 'lines': ['x+1']}
        for extra in ({'output_complete': False}, {'output_complete': None},
                      {'candidate_lines_truncated': True}, {'output_complete': True, 'finish_reason': 'length'},
                      {'review_items': [{'scope': 'line', 'reason': 'replacement_character', 'line': 1}]}):
            record = {**base, **extra}
            review = {'record_sha256': ocr_to_layout.record_digest(record), 'reviewer': 'fixture',
                      'decisions': [{'start_line': 1, 'end_line': 1, 'action': 'accept', 'type': 'formula'}]}
            result = ocr_to_layout.convert(record, review, doc='blocked')
            self.assertIsNone(result['layout'])
            self.assertEqual(result['review_items'][0]['reason'], 'ocr_review_required')

    def test_legacy_complete_text_with_excerpt_flag_remains_reviewable(self):
        record = {'status': 'OK', 'lines': ['x+1'], 'response_truncated': True}
        review = {'record_sha256': ocr_to_layout.record_digest(record), 'reviewer': 'fixture',
                  'decisions': [{'start_line': 1, 'end_line': 1, 'action': 'accept', 'type': 'formula'}]}
        self.assertEqual(ocr_to_layout.convert(record, review, doc='legacy')['status'], 'OK')

    def test_invalid_review_signal_metadata_is_rejected_and_extra_scores_are_not_forwarded(self):
        for items in ('not-list', [None], [{'reason': 'x', 'scope': 'line', 'line': True}],
                      [{'reason': 'x', 'scope': 'unknown'}]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                ocr_to_layout.convert({'status': 'OK', 'review_items': items}, doc='bad')
        record = {'status': 'NEEDS_HUMAN', 'review_items': [{'reason': 'no_text', 'confidence': 0.1}]}
        self.assertNotIn('confidence', json.dumps(ocr_to_layout.convert(record, doc='blocked')))
        with self.assertRaises(ValueError):
            ocr_to_layout.convert({'status': 'OK', 'output_complete': 1}, doc='bad')

    def test_record_to_review_bundle_keeps_line_cause_and_never_writes_layout(self):
        import base64
        output = io.StringIO()
        with patch('urllib.request.urlopen', return_value=endpoint(openai_body('first\n[Non-text]'))), \
                contextlib.redirect_stdout(output):
            code = ocr_extract.run_record({'id': 'fixture', 'image': base64.b64encode(PNG_1X1).decode()},
                                         model='fixture-not-real-ocr', base='http://127.0.0.1:9', prompt='fixture')
        self.assertEqual(code, 1)
        record = json.loads(output.getvalue())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'record.json'
            path.write_text(json.dumps(record))
            bundle = Path(temp) / 'review'
            with contextlib.redirect_stdout(io.StringIO()):
                result = ocr_to_layout.main([str(path), '--doc', 'fixture', '--output-dir', str(bundle)])
            self.assertEqual(result, 1)
            self.assertFalse((bundle / 'layout.json').exists())
            items = json.loads((bundle / 'review.json').read_text())['review_items']
            self.assertEqual(items[0]['ocr_reason'], 'non_text_marker')
            self.assertEqual(items[1]['line'], 2)
            self.assertEqual(items[1]['text'], '[Non-text]')


if __name__ == '__main__':
    unittest.main()
