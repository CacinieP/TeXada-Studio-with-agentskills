import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluate_external_formulas import run_case
from docforensics.vlm import FixtureProvider


class ExternalPipelineTests(unittest.TestCase):
    def test_blocked_source_never_invokes_a_model(self):
        provider = FixtureProvider()
        with tempfile.TemporaryDirectory() as directory, \
                patch('docforensics.pipeline.run_verify', return_value={'status': 'RETRY', 'reason': 'test parse failure'}), \
                patch.object(provider, 'repair_formula', side_effect=AssertionError('must not call provider')):
            row = run_case(Path(directory), {'id': 'missing-operand', 'original_latex': 'x+'}, provider)
        self.assertEqual(row['status'], 'NEEDS_HUMAN')
        self.assertEqual(row['output_latex'], 'x+')
        self.assertEqual(row['model_calls'], 0)
        self.assertIsNone(row['semantic_verdict'])

    def test_reference_and_adjudication_fields_are_not_projected_to_pipeline_node(self):
        with tempfile.TemporaryDirectory() as directory:
            def process(run_dir, doc, node, provider):
                self.assertEqual(node, {'id': 'case', 'type': 'formula', 'data': {'latex': 'x'}})
                from docforensics import state
                state.append(run_dir, node_id='case', action='TERMINAL', latex='x', status='OK',
                             reason='', repaired=False, review_required=False, model_calls=0)
            with patch('docforensics.pipeline.process_formula', side_effect=process):
                run_case(Path(directory), {'id': 'case', 'original_latex': 'x',
                    'reference_latex': 'secret-reference', 'source_category': 'secret-label'}, FixtureProvider())


if __name__ == '__main__':
    unittest.main()
