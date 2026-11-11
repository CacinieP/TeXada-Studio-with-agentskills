"""Observe the real Studio LocalRuntime import with a separate local V4.7 model.

This delegates to the production request function without substituting responses.
Only original public validation images are used. No session token is archived.
"""
import argparse
import base64
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'webui'))
import local_runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    original = local_runtime.local_json_request
    def observed(url, payload=None, **kwargs):
        if payload is not None:
            (args.output / 'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        result = original(url, payload, **kwargs) if payload is not None else original(url, **kwargs)
        public = copy.deepcopy(result)
        for choice in public.get('choices', []):
            for key in ('reasoning', 'reasoning_content'):
                if key in choice.get('message', {}):
                    value = choice['message'].pop(key)
                    choice['message'][key + '_characters'] = len(value) if isinstance(value, str) else 0
        (args.output / 'response.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
        return result
    local_runtime.local_json_request = observed
    image = (ROOT / 'samples/ocr/beta4-acceptance/page.png').read_bytes()
    with tempfile.TemporaryDirectory() as state:
        runtime = local_runtime.LocalRuntime(state, base_url='http://127.0.0.1:18148/v1',
                                              model='minicpm-v4.7-1b-q4_k_m')
        try:
            record = runtime.import_document({'name': 'beta4-original.png', 'mime_type': 'image/png',
                                               'data_base64': base64.b64encode(image).decode()})
        except local_runtime.LocalRuntimeError as exc:
            error = {'code': exc.code, 'message': exc.message, 'kind': 'real_local_runtime_failure'}
            (args.output / 'failure.json').write_text(json.dumps(error, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(error, ensure_ascii=False))
            return 1
        (args.output / 'candidate.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
        assert record['requires_review'] is True
        print(json.dumps({'model': record['model'], 'requires_review': record['requires_review'],
                          'pages': len(record['pages']), 'content': record['content']}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
