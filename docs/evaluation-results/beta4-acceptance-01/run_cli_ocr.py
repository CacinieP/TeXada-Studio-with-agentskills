"""Run the real dedicated OCR CLI with transparent local request capture.

No simulated responses. Images and headers are sent only to an explicit local
loopback server; server lifecycle remains under the operator's control.
"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'skills/doc-ocr-extract/scripts'))
import ocr_extract


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, default=ROOT / 'samples/ocr/beta4-acceptance/page.png')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', default='http://127.0.0.1:18499')
    args = parser.parse_args()
    parts = urllib.parse.urlsplit(args.base)
    if parts.scheme != 'http' or parts.hostname not in ('127.0.0.1', 'localhost', '::1') or parts.username or parts.query:
        raise SystemExit('Only a credential-free local loopback server is allowed.')
    args.output.mkdir(parents=True, exist_ok=False)
    urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))
    original = urllib.request.urlopen
    capture = {}
    class Response:
        def __init__(self, response):
            self.response = response
            self.data = b''
        def __enter__(self):
            self.response.__enter__()
            return self
        def read(self, amount):
            data = self.response.read(amount)
            self.data += data
            return data
        def __exit__(self, *exc):
            capture['response_wire_sha256'] = hashlib.sha256(self.data).hexdigest()
            if self.data:
                try:
                    body = json.loads(self.data)
                except (ValueError, UnicodeDecodeError):
                    body = {'capture_note': 'Non-JSON response; production parser handles the original bytes.'}
                if isinstance(body, dict):
                    choices = body.get('choices')
                    for choice in choices if isinstance(choices, list) else []:
                        if not isinstance(choice, dict) or not isinstance(choice.get('message'), dict):
                            continue
                        for key in ('reasoning', 'reasoning_content'):
                            if key in choice['message']:
                                value = choice['message'].pop(key)
                                choice['message'][key + '_characters'] = len(value) if isinstance(value, str) else 0
                (args.output / 'response.json').write_text(json.dumps(body, ensure_ascii=False, indent=2) + '\n')
            return self.response.__exit__(*exc)
    def observed(request, timeout=None):
        capture['request_wire_sha256'] = hashlib.sha256(request.data).hexdigest()
        (args.output / 'request.json').write_text(json.dumps(json.loads(request.data), ensure_ascii=False, indent=2) + '\n')
        return Response(original(request, timeout=timeout))
    urllib.request.urlopen = observed
    saved = sys.argv
    sys.argv = ['ocr_extract.py', str(args.image), '--base', args.base, '--model', 'minicpm-ocr',
                '--profile', 'minicpm-ocr', '--id', 'beta4-original-page']
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            code = ocr_extract.main()
    finally:
        sys.argv = saved
        urllib.request.urlopen = original
    record = json.loads(stdout.getvalue())
    (args.output / 'record.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'transport.json').write_text(json.dumps({**capture,
        'kind': 'real_local_network_not_fixture', 'source_image_sha256': hashlib.sha256(args.image.read_bytes()).hexdigest(),
        'exit_code': code, 'request_profile': 'minicpm-ocr',
        'implementation_sha256': hashlib.sha256(Path(ocr_extract.__file__).read_bytes()).hexdigest()}, indent=2) + '\n')
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
