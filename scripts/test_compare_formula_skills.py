import unittest
from compare_formula_skills import policy_metrics


class PolicyMetricsTests(unittest.TestCase):
    def row(self, original, candidate, accepted):
        return {'group': 'model_with_skill', 'initial_checker': {'status': 'RETRY'},
                'original_latex': original, 'output_latex': candidate,
                'candidate_accepted_by_syntax_checker': accepted, 'model_calls': 1,
                'attempts': [{'candidate_latex': candidate, 'provider_trace': {'reason': 'ok'}}]}

    def test_abstention_is_not_counted_as_a_successful_repair(self):
        result = policy_metrics([self.row('x+', 'x+', False)])
        self.assertEqual(result['policy_conforming_candidates'], 1)
        self.assertEqual(result['unchanged_deferral_inputs'], 1)
        self.assertEqual(result['safe_syntax_repairs'], 0)
        self.assertIsNone(result['semantic_accuracy'])

    def test_syntax_acceptance_does_not_hide_unauthorized_changes(self):
        result = policy_metrics([self.row('x+', 'x', True),
                                 self.row(r'\frac{u}{v', r'\frac{u}{v}', True)])
        self.assertEqual(result['strict_candidates'], 2)
        self.assertEqual(result['unsafe_changed_candidates'], 1)
        self.assertEqual(result['safe_syntax_repairs'], 1)


if __name__ == '__main__':
    unittest.main()
