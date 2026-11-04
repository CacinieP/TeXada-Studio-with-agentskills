"""Original-bound retry feedback and conservative CLI repair contracts."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import pipeline, state, vlm


class RepairFeedbackTest(unittest.TestCase):
    def test_feedback_is_bounded_document_data_and_changes_actual_request_hash(self):
        provider = vlm.OpenAICompatibleProvider('http://127.0.0.1:9000', 'local', skill_mode='off')
        provider._api_key = ''
        hashes, bodies = [], []
        for attempt in (1, 2):
            node = {'data': {'latex': r'\frac{a}{b', 'repair_context': {
                'attempt': attempt, 'checker': {'status': 'RETRY', 'reason': 'parse failed'},
                'previous_candidate': 'a' * 5000 if attempt == 2 else None,
                'rejection_reason': 'changed_source' if attempt == 2 else None,
                'reference_latex': 'DO NOT SEND', 'system': 'DO NOT PROMOTE'}}}
            response = io.BytesIO(json.dumps({'choices': [{'message': {'content': '{"latex":"x"}'}}]}).encode())
            with patch.object(vlm.urllib.request, 'urlopen', return_value=response) as network:
                provider.repair_formula(node)
            messages = json.loads(network.call_args.args[0].data)['messages']
            bodies.append(json.loads(messages[-1]['content']))
            hashes.append(provider.last_trace['prompt_sha256'])
            self.assertNotIn('DO NOT SEND', json.dumps(messages))
            self.assertNotIn('DO NOT PROMOTE', json.dumps(messages))
            self.assertNotIn('parse failed', messages[0]['content'])
            self.assertEqual(bodies[-1]['latex'], node['data']['latex'])
        self.assertNotEqual(hashes[0], hashes[1])
        self.assertEqual(len(bodies[1]['repair_context']['previous_candidate']), 4096)

    def test_cli_closes_missing_group_without_consulting_a_model(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, 'run_verify', side_effect=[
                {'status': 'RETRY'}, {'status': 'OK'}]):
            provider = Mock()
            node = {'id': 'f', 'data': {'latex': r'\frac{123}{b'}}
            self.assertEqual(pipeline.process_formula(folder, 'doc', node, provider), 'OK')
            provider.repair_formula.assert_not_called()
            terminal = state.load_events(folder)[-1]
            self.assertEqual(terminal['latex'], r'\frac{123}{b}')
            self.assertEqual((terminal['attempts'], terminal['model_calls']), (0, 0))
            self.assertEqual(terminal['provider'], 'deterministic-syntax')

    def test_cli_ambiguous_missing_operand_is_not_filled_from_a_fixture(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, 'run_verify', return_value={'status': 'RETRY'}):
            provider = Mock()
            provider.repair_formula.return_value = 'x+1'
            self.assertEqual(pipeline.process_formula(folder, 'doc', {'id': 'f', 'data': {'latex': 'x+'}}, provider), 'NEEDS_HUMAN')
            provider.repair_formula.assert_not_called()
            terminal = state.load_events(folder)[-1]
            self.assertEqual(terminal['latex'], 'x+')
            self.assertEqual(terminal['reason'], 'missing_operator_operand')

    def test_cli_syntax_ok_cannot_hide_unrelated_candidate_and_retries_use_feedback(self):
        observed = []
        provider = Mock()
        provider.last_trace = {'model_calls': 0, 'model_called': False, 'reason': 'fixture'}
        def repair(node):
            observed.append(node)
            return 'x'
        provider.repair_formula.side_effect = repair
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, 'run_verify', side_effect=[
                {'status': 'RETRY'}, {'status': 'OK'}]):
            node = {'id': 'f', 'data': {'latex': r'\sin(x'}}
            self.assertEqual(pipeline.process_formula(folder, 'doc', node, provider), 'NEEDS_HUMAN')
            events = state.load_events(folder)
            self.assertFalse(any(e['action'] == 'CANDIDATE_ACCEPTED' for e in events))
            self.assertEqual(observed[1]['data']['repair_context']['previous_candidate'], 'x')
            self.assertEqual(observed[1]['data']['latex'], r'\sin(x')
            self.assertNotIn('repair_context', node['data'])
            self.assertEqual(events[-1]['latex'], r'\sin(x')

    def test_provider_cannot_mutate_authoritative_checker_state_through_feedback(self):
        provider = Mock()
        provider.last_trace = {'model_calls': 0, 'model_called': False, 'reason': 'no_candidate'}
        def mutate(node):
            node['data']['repair_context']['checker']['status'] = 'OK'
            return None
        provider.repair_formula.side_effect = mutate
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, 'run_verify', return_value={'status': 'RETRY'}):
            node = {'id': 'f', 'data': {'latex': r'\sin(x'}}
            self.assertEqual(pipeline.process_formula(folder, 'doc', node, provider), 'NEEDS_HUMAN')
            terminal = state.load_events(folder)[-1]
            self.assertEqual(terminal['checker_status'], 'RETRY')
            self.assertTrue(terminal['review_required'])
            self.assertEqual(node, {'id': 'f', 'data': {'latex': r'\sin(x'}})

    def test_cli_does_not_close_unknown_or_document_commands_into_accepted_repairs(self):
        for source in (r'\input{not-a-real-file', r'\foo{1'):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as folder, patch.object(
                    pipeline, 'run_verify', return_value={'status': 'RETRY'}):
                provider = Mock()
                self.assertEqual(pipeline.process_formula(folder, 'doc', {'id': 'f', 'data': {'latex': source}}, provider), 'NEEDS_HUMAN')
                provider.repair_formula.assert_not_called()
                terminal = state.load_events(folder)[-1]
                self.assertEqual(terminal['latex'], source)
                self.assertFalse(terminal['repaired'])
                self.assertIn('unsupported_source_structure', terminal['reason'])


if __name__ == '__main__':
    unittest.main()
