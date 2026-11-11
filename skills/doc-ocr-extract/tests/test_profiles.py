"""Official MiniCPM-OCR decoding is explicit; generic requests stay unchanged."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr_extract
from test_ocr_extract import PNG_1X1, endpoint, openai_body, ollama_body


class ProfileTest(unittest.TestCase):
    def test_openai_official_sampling_without_vllm_fields(self):
        captured = {}
        def open_request(request, timeout=None):
            captured.update(json.loads(request.data))
            return endpoint(openai_body('text'))
        with patch('urllib.request.urlopen', side_effect=open_request):
            status, _, result = ocr_extract.extract(PNG_1X1, model='minicpm-ocr', base='http://127.0.0.1:9',
                prompt=ocr_extract.MINICPM_PROMPT, profile='minicpm-ocr')
        self.assertEqual(status, 'OK')
        for key, value in ocr_extract.MINICPM_SAMPLING.items():
            self.assertEqual(captured[key], value)
        self.assertNotIn('chat_template_kwargs', captured)
        self.assertNotIn('mm_processor_kwargs', captured)
        self.assertEqual(captured['max_tokens'], 4096)
        self.assertEqual(captured['messages'][0]['content'][0]['type'], 'image_url')
        self.assertEqual(result['request_profile'], 'minicpm-ocr')

    def test_native_profile_uses_options_and_disables_thinking(self):
        captured = {}
        def open_request(request, timeout=None):
            captured.update(json.loads(request.data))
            return endpoint(ollama_body('text'))
        with patch('urllib.request.urlopen', side_effect=open_request):
            ocr_extract.extract(PNG_1X1, model='minicpm-ocr', base='http://127.0.0.1:9',
                prompt=ocr_extract.MINICPM_PROMPT, profile='minicpm-ocr', transport='ollama')
        self.assertEqual(captured['options'], {**ocr_extract.MINICPM_SAMPLING, 'num_predict': 4096})
        self.assertFalse(captured['think'])
        self.assertNotIn('top_k', captured)

    def test_cli_prompt_selection_and_explicit_task_prompt(self):
        for extra, expected in [([], ocr_extract.DEFAULT_PROMPT),
                (['--profile', 'minicpm-ocr'], ocr_extract.MINICPM_PROMPT),
                (['--profile', 'minicpm-ocr', '--prompt', 'Formula Recognition:'], 'Formula Recognition:')]:
            with self.subTest(extra=extra), patch.object(sys, 'argv', ['ocr_extract.py', 'fixture.png', *extra]), \
                    patch.object(ocr_extract, 'run_record', return_value=0) as run:
                self.assertEqual(ocr_extract.main(), 0)
                self.assertEqual(run.call_args.kwargs['prompt'], expected)

    def test_unknown_profile_is_environment_error_without_network(self):
        with patch('urllib.request.urlopen') as run:
            status, reason, _ = ocr_extract.extract(PNG_1X1, model='m', base='http://127.0.0.1:9',
                                                   prompt='p', profile='unknown')
        self.assertEqual((status, reason), ('NEEDS_ENV', 'bad_profile'))
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
