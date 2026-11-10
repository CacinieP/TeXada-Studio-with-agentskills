import unittest
from audit_repair_delivery import audit


class PolicyAuditTests(unittest.TestCase):
    def test_syntax_acceptance_does_not_authorize_dropping_an_operand(self):
        rows = [{'case_id': 'missing-operand', 'group': 'model_with_skill',
                 'initial_checker': {'status': 'RETRY'},
                 'candidate_accepted_by_syntax_checker': True,
                 'original_latex': 'x+1+', 'output_latex': 'x+1'},
                {'case_id': 'closing-brace', 'group': 'model_with_skill',
                 'initial_checker': {'status': 'RETRY'},
                 'candidate_accepted_by_syntax_checker': True,
                 'original_latex': r'\frac{x}{2', 'output_latex': r'\frac{x}{2}'}]
        result = audit(rows)['summary']['model_with_skill']
        self.assertEqual(result['syntax_accepted'], 2)
        self.assertEqual(result['source_preservation_allowed'], 1)
        self.assertEqual(result['blocked_reasons'], {'missing_operator_operand': 1})
        self.assertIsNone(result['semantic_accuracy'])


if __name__ == '__main__':
    unittest.main()
