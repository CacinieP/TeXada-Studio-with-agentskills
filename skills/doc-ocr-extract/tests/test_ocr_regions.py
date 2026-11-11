"""Operator regions bind actual source bytes; no detector/model/quality claims."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr_to_layout as converter

ROOT = Path(__file__).resolve().parents[3]


def png(shade=255):
    def chunk(kind, payload):
        return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
    header = struct.pack('>IIBBBBB', 16, 16, 8, 0, 0, 0, 0)
    pixels = b''.join(b'\x00' + bytes([shade]) * 16 for _ in range(16))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')


class RegionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.image = self.base / 'page.png'
        self.image.write_bytes(png())
        self.image_bytes, self.metadata = converter.read_source_image(self.image)
        self.record = {'status': 'OK', 'lines': ['$x+1$'], 'id': 'geometry-fixture-not-real-ocr'}
        self.review = {'record_sha256': converter.record_digest(self.record),
                       'source_image_sha256': self.metadata['sha256'],
                       'reviewer': 'synthetic-geometry-test-operator',
                       'decisions': [{'start_line': 1, 'end_line': 1, 'action': 'accept',
                                      'type': 'formula', 'bbox': [0, 1, 16, 15]}]}

    def convert(self, review=None):
        return converter.convert(self.record, self.review if review is None else review,
                                 doc='region-fixture', source_image=self.metadata)

    def test_png_identity_and_region_are_preserved(self):
        result = self.convert()
        self.assertEqual(self.metadata['sha256'], hashlib.sha256(png()).hexdigest())
        self.assertEqual((self.metadata['width'], self.metadata['height']), (16, 16))
        region = result['layout']['nodes'][0]['ocr_source']['region']
        self.assertEqual(region['bbox'], [0, 1, 16, 15])
        self.assertEqual(region['annotation_source'], 'operator_provided')
        self.assertNotIn('crop', result['layout']['nodes'][0]['data'])
        self.assertEqual(result['layout']['source_image'], self.metadata)

    def test_missing_region_blocks_layout(self):
        review = copy.deepcopy(self.review)
        del review['decisions'][0]['bbox']
        result = self.convert(review)
        self.assertIsNone(result['layout'])
        self.assertEqual(result['review_items'][0]['reason'], 'source_region_required')

    def test_outside_empty_float_and_boolean_boxes_are_rejected(self):
        for bbox in ([0, 0, 17, 16], [-1, 0, 16, 16], [5, 0, 4, 2], [0, 0, 0, 1],
                     [False, 0, 16, 16], [0, 0, 1.5, 2], [0, 1, 2], '0,0,1,1'):
            review = copy.deepcopy(self.review)
            review['decisions'][0]['bbox'] = bbox
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                self.convert(review)

    def test_different_source_bytes_invalidate_review_even_at_same_dimensions(self):
        self.image.write_bytes(png(0))
        _, changed = converter.read_source_image(self.image)
        with self.assertRaisesRegex(ValueError, 'stale_source_image_review'):
            converter.convert(self.record, self.review, doc='fixture', source_image=changed)

    def test_regions_require_actual_source_metadata(self):
        with self.assertRaisesRegex(ValueError, 'source_image_required'):
            converter.convert(self.record, self.review, doc='fixture')
        review = copy.deepcopy(self.review)
        del review['source_image_sha256']
        with self.assertRaisesRegex(ValueError, 'source_image_required'):
            converter.convert(self.record, review, doc='fixture')

    def test_bad_png_header_or_crc_is_rejected(self):
        for data in (b'not an image', png()[:20], png()[:29] + b'xxxx' + png()[33:]):
            self.image.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'png_ihdr'):
                converter.read_source_image(self.image)

    def test_draft_copies_exact_source_and_exposes_image_digest(self):
        record_path = self.base / 'ocr.json'
        record_path.write_text(json.dumps(self.record))
        output = self.base / 'draft'
        self.assertEqual(converter.main([str(record_path), '--source-image', str(self.image),
                         '--doc', 'fixture', '--output-dir', str(output)]), 1)
        self.assertEqual((output / 'source.png').read_bytes(), self.image_bytes)
        template = json.loads((output / 'review-template.json').read_text())
        self.assertEqual(template['source_image_sha256'], self.metadata['sha256'])
        self.assertFalse((output / 'layout.json').exists())

    def test_real_harness_checks_image_before_resume_and_rejects_tampering(self):
        record_path, review_path = self.base / 'ocr.json', self.base / 'decisions.json'
        record_path.write_text(json.dumps(self.record))
        review_path.write_text(json.dumps(self.review))
        sample = self.base / 'sample'
        self.assertEqual(converter.main([str(record_path), '--review', str(review_path),
                         '--source-image', str(self.image), '--doc', 'region-fixture',
                         '--output-dir', str(sample)]), 0)
        state = self.base / 'state'
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'harness')}
        command = [sys.executable, '-m', 'docforensics', 'run', str(sample), '--state', str(state)]
        def run():
            return subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(run().returncode, 0)
        self.assertEqual(run().returncode, 0)
        (sample / 'source.png').write_bytes(png(0))
        self.assertEqual(run().returncode, 2)
        (sample / 'source.png').write_bytes(self.image_bytes)
        layout = json.loads((sample / 'layout.json').read_text())
        for mutate in ('wrong-dimensions', 'outside-box', 'no-image-metadata', 'bad-provenance'):
            changed = copy.deepcopy(layout)
            if mutate == 'wrong-dimensions':
                changed['source_image']['width'] = 32
            elif mutate == 'outside-box':
                changed['nodes'][0]['ocr_source']['region']['bbox'] = [0, 0, 99, 99]
            elif mutate == 'no-image-metadata':
                del changed['source_image']
            else:
                changed['nodes'][0]['ocr_source'] = 'bad'
            (sample / 'layout.json').write_text(json.dumps(changed))
            with self.subTest(mutate=mutate):
                self.assertEqual(run().returncode, 2)
        events = [json.loads(line) for line in (state / 'state.jsonl').read_text().splitlines()]
        self.assertEqual(len([e for e in events if e['action'] == 'SKIP']), 1)
        self.assertFalse(any(e['action'] == 'PROVIDER_START' for e in events))


if __name__ == '__main__':
    unittest.main()
