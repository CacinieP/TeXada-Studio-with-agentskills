"""Evidence accounting tests; no external model measurements."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from run_local_repair_control import summarize, percentile


class SummaryTests(unittest.TestCase):
    def fixture(self, directory):
        path = Path(directory)
        rows = []
        for group in ('model_without_skill', 'model_with_skill'):
            rows.extend([
                {'group': group, 'initial_checker': {'status': 'OK'}, 'attempts': [],
                 'candidate_accepted_by_syntax_checker': False, 'elapsed_seconds': .001},
                {'group': group, 'initial_checker': {'status': 'RETRY'},
                 'attempts': [{'provider_trace': {'reason': 'timeout', 'model_calls': 1}},
                              {'provider_trace': {'reason': 'ok', 'model_calls': 1}}],
                 'candidate_accepted_by_syntax_checker': True, 'elapsed_seconds': 4}])
        (path / 'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
        for name in ('report.md', 'blind-review.csv'):
            (path / name).write_text('test')
        manifest = {'status': 'complete', 'mode': 'model', 'controlled_configuration_verified': True,
                    'files': {name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                              for name in ('results.jsonl', 'report.md', 'blind-review.csv')}}
        (path / 'manifest.json').write_text(json.dumps(manifest))
        return path, manifest

    def test_skipped_controls_do_not_inflate_rates_or_hide_timeouts(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(directory)
            value = summarize(path)['model_with_skill']
            self.assertEqual(value['repair_inputs'], 1)
            self.assertEqual(value['strict_contract_rate_all_http_attempts'], .5)
            self.assertEqual(value['checker_rate_all_retry_inputs'], 1)
            self.assertEqual(value['failure_reasons']['timeout'], 1)
            self.assertEqual(value['repair_seconds_p95'], 4)
            self.assertIsNone(value['semantic_accuracy'])
            self.assertFalse(value['default_switch_approved'])

    def test_rejects_fixture_changed_code_and_tampered_evidence(self):
        for change in ({'mode': 'fixture'}, {'code_changed_during_run': True},
                       {'status': 'running'}, {'controlled_configuration_verified': False}):
            with tempfile.TemporaryDirectory() as directory:
                path, manifest = self.fixture(directory)
                manifest.update(change)
                (path / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    summarize(path)
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(directory)
            (path / 'results.jsonl').write_text('tampered')
            with self.assertRaises(ValueError):
                summarize(path)

    def test_percentile_uses_nearest_rank(self):
        self.assertIsNone(percentile([], .95))
        self.assertEqual(percentile([1, 2, 3], .95), 3)


if __name__ == '__main__':
    unittest.main()
