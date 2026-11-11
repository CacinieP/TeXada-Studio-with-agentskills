"""Portable OCR region reports, exact event binding and local-only SVG assets."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics import __main__ as cli, pipeline, source_report, state

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'docs/evaluation-results/ocr-source-regions-01/reviewed'
NS = {'svg': source_report.SVG}


class SourceReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.sample, self.run_dir = self.base / 'sample', self.base / 'run'
        shutil.copytree(FIXTURE, self.sample)
        self.provider = pipeline.FixtureProvider()

    def run_pipeline(self, run_id):
        with patch.object(pipeline, 'run_verify', return_value={'status': 'OK'}):
            return pipeline.run(str(self.sample), str(self.run_dir), self.provider, run_id=run_id)

    def report(self, run_id):
        events = state.load_events(self.run_dir)
        return Path(cli.write_run_report(str(self.run_dir), self.provider, events, run_id)).read_text()

    def payload(self):
        return next(e['source_region'] for e in state.load_events(self.run_dir) if e['action'] == 'SOURCE_REGION')

    def test_source_is_archived_for_unchanged_formula_and_previews_match_box(self):
        self.run_pipeline('one')
        payload = self.payload()
        original = (self.sample / 'source.png').read_bytes()
        self.assertEqual((self.run_dir / payload['image_path']).read_bytes(), original)
        report = self.report('one')
        self.assertIn('来源图与区域（操作者标注）', report)
        self.assertIn('不是候选修订', report)
        self.assertIn('$x+1$', report)
        self.assertIn('范围和来源哈希通过校验不代表区域内容已核验', report)
        assets = source_report.report_assets(self.run_dir, payload)
        for key in ('image', 'annotated', 'zoom'):
            self.assertIn(assets[key], report)
        root = ET.parse(self.run_dir / assets['annotated']).getroot()
        image = root.find('svg:image', NS)
        self.assertEqual(image.get('href'), payload['image_sha256'] + '.png')
        self.assertEqual((self.run_dir / assets['annotated']).parent / image.get('href'),
                         self.run_dir / assets['image'])
        rect = root.find('svg:rect', NS)
        self.assertEqual([rect.get(key) for key in ('x', 'y', 'width', 'height')], ['3', '5', '27', '9'])
        zoom = ET.parse(self.run_dir / assets['zoom']).getroot()
        self.assertEqual(zoom.get('viewBox'), '3 5 27 9')
        self.assertIsNone(root.find('svg:script', NS))

    def test_resume_and_offline_report_do_not_need_original_sample(self):
        self.run_pipeline('one')
        self.run_pipeline('two')
        events = state.load_events(self.run_dir)
        current = [e for e in events if e.get('run_id') == 'two']
        source = next(e for e in current if e['action'] == 'SOURCE_REGION')
        skip = next(e for e in current if e['action'] == 'SKIP')
        self.assertEqual(source['input_sha256'], skip['input_sha256'])
        self.assertEqual(source['context_sha256'], skip['context_sha256'])
        self.assertEqual(source['revision'], skip['revision'])
        shutil.rmtree(self.sample)
        report = self.report('two')
        self.assertIn('复用 1', report)
        self.assertIn('请求尝试：0', report)
        self.assertIn('区域放大图', report)
        self.assertNotIn('未生成预览', report)
        # A report directory may be moved intact; links remain run-relative.
        moved = self.base / 'moved'
        shutil.move(self.run_dir, moved)
        payload = source['source_region']
        self.assertTrue((moved / source_report.report_assets(moved, payload)['image']).is_file())

    def test_missing_or_changed_snapshot_never_produces_a_positive_preview(self):
        self.run_pipeline('one')
        image = self.run_dir / self.payload()['image_path']
        for mode in ('missing', 'changed'):
            if image.exists():
                image.unlink()
            if mode == 'changed':
                image.write_bytes(b'wrong bytes')
            report = self.report('one')
            self.assertIn('未生成预览', report)
            self.assertNotIn('![来源原图]', report)
            self.assertNotIn('[带框标注图]', report)

    def test_rerun_restores_changed_snapshot_and_svg_cache(self):
        self.run_pipeline('one')
        payload = self.payload()
        assets = source_report.report_assets(self.run_dir, payload)
        (self.run_dir / assets['image']).write_bytes(b'wrong image')
        (self.run_dir / assets['annotated']).write_text('<script>wrong</script>')
        self.run_pipeline('two')
        self.report('two')
        self.assertEqual(hashlib.sha256((self.run_dir / assets['image']).read_bytes()).hexdigest(),
                         payload['image_sha256'])
        self.assertIsNotNone(ET.parse(self.run_dir / assets['annotated']).getroot().find('svg:image', NS))

    def test_untrusted_journal_paths_and_regions_do_not_escape_asset_directory(self):
        self.run_pipeline('one')
        payload = self.payload()
        for changed in ({'image_path': '../outside.png'}, {'image_sha256': 'https://example.test/a'},
                        {'bbox': [0, 0, 99, 99]}, {'width': True}, {'width': 80}, {'bbox': [False, 1, 2, 3]}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                source_report.report_assets(self.run_dir, {**payload, **changed})
        self.assertFalse((self.base / 'outside.png').exists())

    def test_wrong_event_identity_does_not_attach_unrelated_image(self):
        self.run_pipeline('one')
        events = state.load_events(self.run_dir)
        source = next(e for e in events if e['action'] == 'SOURCE_REGION')
        cases = [(field, 'unrelated') for field in ('input_sha256', 'context_sha256', 'node_id', 'doc', 'run_id')]
        cases.append(('run_id', None))
        for field, value in cases:
            changed = copy.deepcopy(events)
            next(e for e in changed if e['action'] == 'SOURCE_REGION')[field] = value
            report = Path(cli.write_run_report(str(self.run_dir), self.provider, changed, 'one')).read_text()
            terminal_section = report.split('检查终态：OK', 1)[1].split('### 节点', 1)[0].split('\n## ', 1)[0]
            with self.subTest(field=field):
                self.assertNotIn('![来源原图]', terminal_section)
        self.assertIn('source_region', json.dumps(source))

    def test_unfinished_node_keeps_source_without_claiming_terminal_success(self):
        self.run_pipeline('one')
        events = [e for e in state.load_events(self.run_dir) if e['action'] != 'TERMINAL']
        report = Path(cli.write_run_report(str(self.run_dir), self.provider, events, 'one')).read_text()
        self.assertIn('未完成 1', report)
        self.assertIn('区域放大图', report)
        self.assertNotIn('检查终态：OK', report)

    def test_fenced_source_text_cannot_inject_markdown_or_svg(self):
        self.run_pipeline('one')
        events = state.load_events(self.run_dir)
        payload = next(e['source_region'] for e in events if e['action'] == 'SOURCE_REGION')
        payload['source_text'] = ['```\n<script>alert(1)</script>']
        payload['reviewer'] = '[fake](https://example.test)'
        report = Path(cli.write_run_report(str(self.run_dir), self.provider, events, 'one')).read_text()
        self.assertIn('````text\n```\n<script>', report)
        for svg in (self.run_dir / 'sources').glob('*.svg'):
            text = svg.read_text()
            self.assertNotIn('<script>', text)
            self.assertNotIn('https://example.test', text)

    def test_shared_page_is_copied_once_and_different_boxes_get_distinct_previews(self):
        path = self.sample / 'layout.json'
        layout = json.loads(path.read_text())
        node = copy.deepcopy(layout['nodes'][0])
        node['id'] = 'second-region'
        node['ocr_source']['region']['bbox'] = [4, 6, 29, 13]
        layout['nodes'].append(node)
        path.write_text(json.dumps(layout))
        self.run_pipeline('one')
        report = self.report('one')
        self.assertEqual(report.count('![来源原图]'), 1)
        self.assertEqual(len(list((self.run_dir / 'sources').glob('*.png'))), 1)
        self.assertEqual(len(list((self.run_dir / 'sources').glob('*-annotated.svg'))), 2)

    def test_original_snapshot_checks_source_again_before_copying(self):
        layout = json.loads((self.sample / 'layout.json').read_text())
        (self.sample / 'source.png').write_bytes(b'changed after preflight')
        with self.assertRaises(ValueError):
            source_report.snapshot(self.run_dir, self.sample, layout['source_image'])


if __name__ == '__main__':
    unittest.main()
