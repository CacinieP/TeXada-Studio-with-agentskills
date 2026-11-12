"""Source-image evidence survives temporary PDF rendering and detects drift."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_runtime import LocalRuntime, LocalRuntimeError
from test_local_runtime import PNG


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.runtime=LocalRuntime(self.root)
        self.image={'name':'formula.png','mime_type':'image/png','data_base64':base64.b64encode(PNG).decode()}

    def import_image(self):
        with patch.object(self.runtime,'_transcribe',return_value={'text':'$x^2$'}):
            return self.runtime.import_document(self.image)

    def test_image_reuses_original_bytes_and_read_does_not_call_model(self):
        result=self.import_image();directory=self.root/'imports'/result['id']
        self.assertEqual(set(p.name for p in directory.iterdir()),{'source.png','candidate.json'})
        self.assertEqual(result['pages'][0]['image_file'],'source.png')
        with patch.object(self.runtime,'_transcribe',side_effect=AssertionError('model called')):
            evidence=self.runtime.get_page_evidence(result['id'],1)
        self.assertEqual(evidence['data'],PNG)
        self.assertEqual(evidence['sha256'],hashlib.sha256(PNG).hexdigest())
        self.assertTrue(result['requires_review'])
        self.assertEqual((directory/'source.png').stat().st_mode & 0o777,0o600)

    def test_pdf_pages_survive_their_temporary_directory(self):
        temporary_directories=[]
        def render(data,page_start,max_pages,directory):
            temporary_directories.append(directory)
            (directory/'transient.png').write_bytes(PNG)
            return [{'page':3,'data':PNG,'mime_type':'image/png','width':1,'height':1},
                    {'page':4,'data':PNG,'mime_type':'image/png','width':1,'height':1}],9
        body={'name':'scan.pdf','mime_type':'application/pdf','data_base64':base64.b64encode(b'%PDF-1.4\n%%EOF').decode(),'page_start':3,'max_pages':2}
        with patch.object(self.runtime,'_render_pdf',side_effect=render),patch.object(self.runtime,'_transcribe',return_value={'text':'$x$'}):
            result=self.runtime.import_document(body)
        self.assertFalse(temporary_directories[0].exists())
        self.assertEqual([p['image_file'] for p in result['pages']],['pages/page-000003.png','pages/page-000004.png'])
        self.assertEqual(self.runtime.get_page_evidence(result['id'],3)['data'],PNG)
        self.assertEqual(self.runtime.get_page_evidence(result['id'],4)['data'],PNG)
        with self.assertRaises(LocalRuntimeError) as error:self.runtime.get_page_evidence(result['id'],2)
        self.assertEqual(error.exception.code,'source_page_not_found')

    def test_failed_publish_leaves_no_partial_import_or_staging_directory(self):
        with patch.object(self.runtime,'_transcribe',return_value={'text':'$x$'}),patch('local_runtime.os.rename',side_effect=OSError('disk failure')):
            with self.assertRaises(LocalRuntimeError) as error:self.runtime.import_document(self.image)
        self.assertEqual(error.exception.code,'import_evidence_write_failed')
        self.assertEqual(list((self.root/'imports').iterdir()),[])

    def test_changed_source_bytes_are_rejected(self):
        result=self.import_image();path=self.root/'imports'/result['id']/'source.png'
        path.write_bytes(PNG+b'changed')
        with self.assertRaises(LocalRuntimeError) as error:self.runtime.get_page_evidence(result['id'],1)
        self.assertEqual(error.exception.code,'source_evidence_changed')

    def test_paths_and_symlinks_cannot_redirect_source_reads(self):
        result=self.import_image();directory=self.root/'imports'/result['id']
        outside=self.root/'outside.png';outside.write_bytes(PNG)
        source=directory/'source.png';source.unlink();source.symlink_to(outside)
        with self.assertRaises(LocalRuntimeError) as error:self.runtime.get_page_evidence(result['id'],1)
        self.assertEqual(error.exception.code,'invalid_import_evidence')
        source.unlink();source.write_bytes(PNG)
        manifest=directory/'candidate.json';record=json.loads(manifest.read_text());record['pages'][0]['image_file']='../outside.png';manifest.write_text(json.dumps(record))
        with self.assertRaises(LocalRuntimeError) as error:self.runtime.get_page_evidence(result['id'],1)
        self.assertEqual(error.exception.code,'invalid_import_evidence')
        for import_id,page in [('../outside',1),(result['id'],True),(result['id'],0)]:
            with self.assertRaises(LocalRuntimeError):self.runtime.get_page_evidence(import_id,page)


if __name__=='__main__':unittest.main()
