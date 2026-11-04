"""Local Studio product contracts, using temporary storage and no inference.

These tests exercise the HTTP boundary and persistence, not a second imitation
of the document store. Compilers and model providers are replaced only where
external execution would otherwise be required.
"""

from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from test_static_assets import studio


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LocalProductTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        self.state = self.root / "state"
        self.documents = self.state / "documents"
        self.samples = self.root / "samples"
        self.samples.mkdir()
        (self.samples / "sample.tex").write_text("Sample $x$", encoding="utf-8")
        for key, value in (("STUDIO_STATE", str(self.state)),
                           ("STUDIO_DOCS", str(self.documents)), ("SAMPLE_DOCS", str(self.samples))):
            self.stack.enter_context(patch.object(studio, key, value))
        self.stack.enter_context(patch.dict(studio._jobs, clear=True))
        self.stack.enter_context(patch.dict(os.environ, {
            "TEXADA_LOCAL_MODE": "1", "VLM_BASE_URL": "http://127.0.0.1:9/v1",
            "VLM_MODEL": "local-product-test",
        }))
        self.client = self.stack.enter_context(TestClient(studio.app))
        self.auth = {"token": studio.TOKEN}

    def post(self, route, body):
        # json.dumps permits escaped invalid Unicode to reach the API validator.
        return self.client.post("/api/studio/" + route, params=self.auth,
                                content=json.dumps(body), headers={"Content-Type": "application/json"})

    def get(self, route, **params):
        return self.client.get("/api/studio/" + route, params={**self.auth, **params})

    def create(self, name="notes.tex", content="Original $x$"):
        response = self.post("create", {"name": name, "content": content})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def candidate(self, job_id="a" * 32, original="Original $x+$", candidate="Original $x+1$"):
        result = {"fixed_content": candidate, "original_sha256": digest(original),
                  "candidate_sha256": digest(candidate), "requires_review": True}
        job = {"name": "notes.tex", "created_at": 100.0, "done": True,
               "log": ["candidate ready"], "result": result}
        studio._save_job(job_id, job)
        studio._jobs[job_id] = job
        return job_id, original, candidate

    def decision(self, job_id, original, candidate, decision="accept", **changes):
        body = {"name": "notes.tex", "content": original,
                "candidate_sha256": digest(candidate), "decision": decision}
        body.update(changes)
        return self.post(f"jobs/{job_id}/decision", body)

    def test_create_edit_save_reload_rename_and_recoverable_delete(self):
        created = self.create("研究 笔记.tex", "第一版 🙂 $x$")
        self.assertEqual(created["origin"], "local")
        self.assertEqual(created["sha256"], digest(created["content"]))
        loaded = self.get("file", name=created["name"]).json()
        self.assertEqual(loaded["content"], created["content"])

        saved = self.post("save", {"name": created["name"], "content": "第二版 $y$",
                                   "expected_sha256": loaded["sha256"]})
        self.assertEqual(saved.status_code, 200, saved.text)
        # A fresh DocumentStore and a fresh HTTP client see actual disk content.
        self.assertEqual(studio._documents().read(created["name"])["content"], "第二版 $y$")
        with TestClient(studio.app) as reloaded:
            response = reloaded.get("/api/studio/file", params={**self.auth, "name": created["name"]})
            self.assertEqual(response.json()["sha256"], digest("第二版 $y$"))
        archived = list((self.documents / ".history").rglob("*.tex"))
        self.assertEqual([path.read_text() for path in archived], [created["content"]])

        renamed = self.post("rename", {"name": created["name"], "new_name": "renamed.tex",
                                       "expected_sha256": saved.json()["sha256"]})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(self.get("file", name=created["name"]).status_code, 404)
        self.assertEqual(self.get("file", name="renamed.tex").json()["content"], "第二版 $y$")
        deleted = self.post("delete", {"name": "renamed.tex", "expected_sha256": renamed.json()["sha256"]})
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertTrue(deleted.json()["recoverable"])
        self.assertEqual(self.get("file", name="renamed.tex").status_code, 404)
        self.assertEqual([path.read_text() for path in (self.documents / ".trash").glob("*.tex")], ["第二版 $y$"])

    def test_existing_local_upload_and_create_never_silently_overwrite(self):
        original = self.create()
        for operation in ("upload", "create", "save"):
            with self.subTest(operation=operation):
                response = self.post(operation, {"name": original["name"], "content": "replacement"})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.get("file", name=original["name"]).json()["content"], original["content"])
        response = self.post("upload", {"name": original["name"], "content": "explicit replacement",
                                       "expected_sha256": original["sha256"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "explicit replacement")

    def test_stale_version_blocks_save_rename_and_delete(self):
        original = self.create()
        current = self.post("save", {"name": original["name"], "content": "newer",
                                     "expected_sha256": original["sha256"]}).json()
        for operation, extra in (("save", {"content": "lost update"}),
                                  ("rename", {"new_name": "moved.tex"}), ("delete", {})):
            with self.subTest(operation=operation):
                response = self.post(operation, {"name": original["name"],
                                                "expected_sha256": original["sha256"], **extra})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(self.get("file", name=original["name"]).json()["sha256"], current["sha256"])
        self.assertEqual(self.get("file", name="moved.tex").status_code, 404)

    def test_sample_copy_on_write_and_local_delete_preserve_bundled_sample(self):
        sample = self.get("file", name="sample.tex").json()
        self.assertEqual(sample["origin"], "sample")
        for operation, extra in (("delete", {}), ("rename", {"new_name": "renamed.tex"})):
            self.assertEqual(self.post(operation, {"name": sample["name"],
                                                   "expected_sha256": sample["sha256"], **extra}).status_code, 409)
        copied = self.post("save", {"name": sample["name"], "content": "My local sample",
                                    "expected_sha256": sample["sha256"]})
        self.assertEqual(copied.status_code, 200)
        self.assertEqual(copied.json()["origin"], "local")
        self.assertEqual((self.samples / "sample.tex").read_text(), sample["content"])
        deleted = self.post("delete", {"name": sample["name"], "expected_sha256": copied.json()["sha256"]})
        self.assertEqual(deleted.status_code, 200)
        reappeared = self.get("file", name="sample.tex").json()
        self.assertEqual(reappeared["origin"], "sample")
        self.assertEqual(reappeared["content"], sample["content"])

    def test_uploading_over_sample_creates_local_copy_and_listing_has_metadata(self):
        response = self.post("upload", {"name": "sample.tex", "content": "local upload"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["origin"], "local")
        listing = self.get("files").json()
        self.assertEqual(listing["files"], ["sample.tex"])
        self.assertEqual(listing["documents"][0]["sha256"], digest("local upload"))
        self.assertNotIn("content", listing["documents"][0])
        self.assertEqual((self.samples / "sample.tex").read_text(), "Sample $x$")

    def test_rename_collision_leaves_both_documents_intact(self):
        first = self.create("first.tex", "first")
        self.create("second.tex", "second")
        response = self.post("rename", {"name": first["name"], "new_name": "second.tex",
                                        "expected_sha256": first["sha256"]})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.get("file", name="first.tex").json()["content"], "first")
        self.assertEqual(self.get("file", name="second.tex").json()["content"], "second")

    def test_invalid_names_and_content_are_rejected_without_writes(self):
        for name in ("../escape.tex", r"folder\escape.tex", ".hidden.tex", "notes.txt", "a..tex", None, [], 42):
            with self.subTest(name=name):
                self.assertEqual(self.post("create", {"name": name, "content": "x"}).status_code, 400)
        for content in (None, [], {}, 42, True, "bad\x00text", "\ud800"):
            for operation in ("create", "upload", "save", "preview", "fix"):
                with self.subTest(content=repr(content), operation=operation):
                    self.assertEqual(self.post(operation, {"name": "bad.tex", "content": content}).status_code, 400)
        self.assertFalse(self.documents.exists())
        self.assertEqual(studio._jobs, {})

    def test_oversized_utf8_is_rejected_consistently(self):
        # Count encoded bytes, not characters: this is just over 2 MiB.
        content = "汉" * ((2 * 1024 * 1024) // 3 + 1)
        for operation in ("create", "upload", "save", "preview", "fix", "analyze", "math"):
            with self.subTest(operation=operation):
                self.assertEqual(self.post(operation, {"name": "large.tex", "content": content}).status_code, 413)
        self.assertFalse(self.documents.exists())
        self.assertEqual(studio._jobs, {})

    def test_document_and_storage_root_symlinks_are_not_followed(self):
        outside = self.root / "outside"
        outside.mkdir()
        secret = outside / "private.tex"
        secret.write_text("outside document")
        self.documents.mkdir(parents=True)
        (self.documents / "link.tex").symlink_to(secret)
        for operation in ("file", "save", "delete", "rename"):
            with self.subTest(operation=operation):
                response = (self.get("file", name="link.tex") if operation == "file" else
                            self.post(operation, {"name": "link.tex", "content": "changed",
                                                  "expected_sha256": digest("outside document"), "new_name": "moved.tex"}))
                self.assertEqual(response.status_code, 400)
        self.assertNotIn("link.tex", self.get("files").json()["files"])
        self.assertEqual(secret.read_text(), "outside document")
        root_link = self.root / "document-link"
        root_link.symlink_to(outside, target_is_directory=True)
        with patch.object(studio, "STUDIO_DOCS", str(root_link)):
            self.assertEqual(self.post("create", {"name": "new.tex", "content": "x"}).status_code, 400)
        self.assertFalse((outside / "new.tex").exists())

    def test_history_symlink_is_rejected_before_backup_or_overwrite(self):
        original = self.create()
        outside = self.root / "outside-history"
        outside.mkdir()
        (self.documents / ".history").symlink_to(outside, target_is_directory=True)
        response = self.post("save", {"name": original["name"], "content": "new text",
                                      "expected_sha256": original["sha256"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.get("file", name=original["name"]).json()["content"], original["content"])

    def test_trash_symlink_is_rejected_before_moving_document(self):
        original = self.create()
        outside = self.root / "outside-trash"
        outside.mkdir()
        (self.documents / ".trash").symlink_to(outside, target_is_directory=True)
        response = self.post("delete", {"name": original["name"], "expected_sha256": original["sha256"]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(self.get("file", name=original["name"]).json()["content"], original["content"])

    def test_candidate_decisions_are_durable_idempotent_and_do_not_save_source(self):
        for index, choice in enumerate(("accept", "reject")):
            with self.subTest(choice=choice):
                job_id, original, candidate = self.candidate(job_id=str(index + 1) * 32)
                self.create("notes.tex" if index == 0 else "other.tex", original)
                response = self.decision(job_id, original, candidate, choice)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["decision"], choice)
                self.assertEqual(self.decision(job_id, original, candidate, choice).json(), response.json())
                self.assertEqual(self.decision(job_id, original, candidate,
                                               "reject" if choice == "accept" else "accept").status_code, 409)
                events = studio._read_job_events(job_id)
                self.assertEqual([event["action"] for event in events],
                                 ["USER_ACCEPTED" if choice == "accept" else "USER_REJECTED"])
                studio._jobs.pop(job_id)
                status = self.get("fixstatus", id=job_id).json()
                self.assertEqual(status["review"]["decision"], choice)
                row = next(row for row in self.get("jobs").json()["jobs"] if row["id"] == job_id)
                self.assertEqual(row["review"]["decision"], choice)
                self.assertTrue(row["has_candidate"])
                # Review adoption never substitutes for an explicit CAS save.
                self.assertEqual(self.get("file", name="notes.tex").json()["content"], original)

    def test_candidate_wrong_source_hash_name_or_candidate_cannot_be_reviewed(self):
        job_id, original, candidate = self.candidate()
        invalid = ({"content": original + " edited"}, {"name": "another.tex"},
                   {"candidate_sha256": "0" * 64})
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertEqual(self.decision(job_id, original, candidate, **changes).status_code, 409)
        self.assertEqual(self.decision(job_id, original, candidate, decision="maybe").status_code, 400)
        self.assertNotIn("review", studio._read_job(job_id))
        self.assertEqual(studio._read_job_events(job_id), [])

    def test_non_string_review_decisions_are_rejected_without_recording_review(self):
        job_id, original, candidate = self.candidate()
        for decision in ([], {}, None, True, 42):
            with self.subTest(decision=decision):
                self.assertEqual(self.decision(job_id, original, candidate, decision).status_code, 400)
        self.assertNotIn("review", studio._read_job(job_id))
        self.assertEqual(studio._read_job_events(job_id), [])

    def test_jobs_recover_interrupted_state_and_ignore_broken_records(self):
        job_id = "b" * 32
        studio._save_job(job_id, {"name": "notes.tex", "created_at": 1.0,
                                  "done": False, "log": ["started"], "result": None})
        broken = self.state / "jobs" / ("c" * 32)
        broken.mkdir()
        (broken / "job.json").write_text("not json")
        rows = self.get("jobs").json()["jobs"]
        self.assertEqual([row["id"] for row in rows], [job_id])
        self.assertTrue(rows[0]["done"])
        self.assertIn("中断", rows[0]["error"])
        self.assertFalse(rows[0]["has_candidate"])

    def test_malformed_history_metadata_does_not_break_history_or_review(self):
        valid_id, _, _ = self.candidate()
        studio._jobs.clear()  # Exercise recovery from disk, as after a restart.
        invalid = [{"created_at": value} for value in ("yesterday", None, True, float("nan"), float("inf"))]
        invalid += [{"review": value} for value in ([], {}, {"decision": []}, {"decision": "maybe"})]
        for index, changes in enumerate(invalid):
            job_id = f"{index + 1:032x}"
            studio._save_job(job_id, {"done": True, "log": [], "result": None,
                                      "created_at": 1.0, **changes})
        rows = self.get("jobs")
        self.assertEqual(rows.status_code, 200, rows.text)
        self.assertEqual([row["id"] for row in rows.json()["jobs"]], [valid_id])

    def test_incomplete_candidate_hashes_cannot_be_reviewed(self):
        original, candidate = "Original $x+$", "Original $x+1$"
        hashes = {"original_sha256": digest(original), "candidate_sha256": digest(candidate)}
        job_id = "f" * 32
        for missing in ("original_sha256", "candidate_sha256"):
            for include_request_hash in (False, True):
                with self.subTest(missing=missing, include_request_hash=include_request_hash):
                    studio._save_job(job_id, {"done": True, "log": [],
                                              "result": {key: value for key, value in hashes.items() if key != missing}})
                    body = {"name": "notes.tex", "content": original, "decision": "accept"}
                    if include_request_hash:
                        body["candidate_sha256"] = digest(candidate)
                    response = self.post(f"jobs/{job_id}/decision", body)
                    self.assertEqual(response.status_code, 409, response.text)
                    self.assertNotIn("review", studio._read_job(job_id))
                    self.assertEqual(studio._read_job_events(job_id), [])

        # A complete stored candidate still requires the caller's exact hash.
        studio._save_job(job_id, {"done": True, "log": [], "result": hashes})
        response = self.post(f"jobs/{job_id}/decision", {"name": "notes.tex", "content": original,
                                                       "decision": "accept"})
        self.assertEqual(response.status_code, 409, response.text)

    def test_cancel_is_persisted_and_takes_effect_before_compilation(self):
        with patch.object(studio.threading, "Thread"):
            response = self.post("fix", {"name": "notes.tex", "content": "plain"})
        self.assertEqual(response.status_code, 200)
        job_id = response.json()["job"]
        cancelled = self.post(f"jobs/{job_id}/cancel", {})
        self.assertTrue(cancelled.json()["cancel_requested"])
        stored = json.loads((self.state / "jobs" / job_id / "job.json").read_text())
        self.assertTrue(stored["cancel_requested"])
        provider = Mock()
        provider.fingerprint.return_value = {"kind": "test"}
        with patch.object(studio, "_new_provider", return_value=provider), \
                patch.object(studio, "_studio_compile") as compile_document:
            studio._studio_job("notes.tex", "plain", job_id)
        compile_document.assert_not_called()
        status = self.get("fixstatus", id=job_id).json()
        self.assertTrue(status["done"])
        self.assertIsNone(status["result"])
        self.assertIn("取消", status["error"])
        self.assertEqual(studio._read_job_events(job_id)[-1]["action"], "JOB_CANCELLED")

    def test_math_http_and_repair_skip_raw_contexts_and_preserve_display_wrappers(self):
        content = ("% $ignored+$\n" + r"\verb|$verbatim+$|" + "\n"
                   + r"\begin{align}x&=1\\y&=2\end{align}" + "\n\\[\nx+\n\\]\n")
        response = self.post("math", {"content": content})
        self.assertEqual(response.status_code, 200)
        nodes = response.json()["nodes"]
        self.assertEqual([node["kind"] for node in nodes], ["align", "display"])
        self.assertEqual([node["checkable"] for node in nodes], [False, True])
        provider = Mock()
        provider.repair_formula.return_value = "\nx+1\n"
        provider.last_trace = {"model_calls": 1}

        def verify(latex):
            return {"status": "RETRY" if latex.strip() == "x+" else "OK"}

        with patch.object(studio, "_verify_formula", side_effect=verify) as checker:
            analyzed = self.post("analyze", {"content": content})
            self.assertEqual(analyzed.status_code, 200)
            fixed, edits = studio._apply_fixes(content, [], provider=provider)
        self.assertEqual(fixed, content.replace("\\[\nx+\n\\]", "\\[\nx+1\n\\]"))
        self.assertEqual(len(edits), 1)
        provider.repair_formula.assert_called_once()
        self.assertEqual(provider.repair_formula.call_args.args[0]["data"]["latex"], "\nx+\n")
        self.assertEqual([call.args[0] for call in checker.call_args_list], ["\nx+\n", "\nx+\n", "\nx+1\n"])

    def test_printed_table_examples_and_macro_definitions_are_never_repaired(self):
        table = "\\begin{tabular}{lr}\nItem & Value \\\\\nA & 2 \\\\\nTotal & 99 \\\\\n\\end{tabular}\n"
        examples = ["\\begin{verbatim}\n" + table + "\\end{verbatim}\n",
                    "\\begin{lstlisting}\n" + table + "\\end{lstlisting}\n",
                    "\\newcommand{\\example}{" + table + "}\n",
                    "Example: \\verb|\\begin{tabular}{lr}|\nplain text\n"]
        for content in examples:
            with self.subTest(content=content), patch.object(studio, "_new_provider") as provider:
                self.assertEqual(studio._table_problems(content), [])
                candidate, edits = studio._apply_fixes(content, [])
                self.assertEqual(candidate, content)
                self.assertEqual(edits, [])
                provider.assert_not_called()

    def test_successful_pdf_remains_downloadable_when_preview_converter_is_missing(self):
        def run(command, **kwargs):
            if command[0] == studio.TECTONIC:
                self.assertIn("--only-cached", command)
                self.assertIn("--untrusted", command)
                (Path(kwargs["cwd"]) / "main.pdf").write_bytes(b"%PDF-1.7\nfixture")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[0] == "pdfinfo":
                return SimpleNamespace(returncode=0, stdout="Pages:          2\n", stderr="")
            if command[0] == "pdftoppm":
                raise FileNotFoundError("preview converter missing")
            self.fail("Unexpected external command")

        with patch.object(studio.subprocess, "run", side_effect=run):
            response = self.post("preview", {"name": "notes.tex", "content": "current source"})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            self.assertTrue(result["compile_ok"])
            self.assertFalse(result["preview_ok"])
            self.assertFalse(result["ok"])
            self.assertEqual(result["content_sha256"], digest("current source"))
            self.assertEqual(result["page_count"], 2)
            self.assertEqual(result["pages"], [])
            downloaded = self.client.get(result["pdf"], params=self.auth)
        self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(downloaded.content, b"%PDF-1.7\nfixture")
        self.assertIn("application/pdf", downloaded.headers["content-type"])

    def test_recompiling_unchanged_source_keeps_each_pdf_and_preview_immutable(self):
        generation = 0

        def run(command, **kwargs):
            nonlocal generation
            if command[0] == studio.TECTONIC:
                generation += 1
                (Path(kwargs["cwd"]) / "main.pdf").write_bytes(
                    b"%PDF-1.7\n" + f"generation-{generation}".encode())
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[0] == "pdfinfo":
                return SimpleNamespace(returncode=0, stdout="Pages: 2\n", stderr="")
            if command[0] == "pdftoppm":
                pdf = Path(command[-2]).read_bytes()
                Path(command[-1] + ".png").write_bytes(b"\x89PNG\r\n" + pdf)
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            self.fail("Unexpected external command")

        body = {"name": "notes.tex", "content": r"\today"}
        with patch.object(studio.subprocess, "run", side_effect=run):
            first = self.post("preview", body).json()
            first_image = self.client.get(first["pages"][0].split("?")[0], params=self.auth)
            second = self.post("preview", body).json()
            self.assertEqual(first["content_sha256"], second["content_sha256"])
            self.assertNotEqual(first["tag"], second["tag"])
            self.assertNotEqual(first["pdf"], second["pdf"])
            self.assertNotEqual(first["pages"], second["pages"])
            self.assertIn("max-age=3600", first_image.headers["cache-control"])

            # Even a page first requested after recompilation belongs to its PDF.
            for result, expected in ((first, b"generation-1"), (second, b"generation-2")):
                pdf = self.client.get(result["pdf"], params=self.auth)
                self.assertEqual(pdf.content, b"%PDF-1.7\n" + expected)
                for page in (1, 2):
                    image = self.client.get(result["pages"][page - 1].split("?")[0],
                                            params={**self.auth, "page": page})
                    self.assertEqual(image.status_code, 200)
                    self.assertEqual(image.content, b"\x89PNG\r\n%PDF-1.7\n" + expected)

    def test_local_settings_survive_new_runtime_and_config_does_not_probe(self):
        with patch.object(studio.LocalRuntime, "probe", side_effect=AssertionError("implicit model call")):
            first = self.get("config")
            self.assertEqual(first.status_code, 200)
            self.assertIsNone(first.json()["model_available"])
            saved = self.post("settings", {"base_url": "http://127.0.0.1:65432/v1", "model": "fixture-model"})
            self.assertEqual(saved.status_code, 200)
            reloaded = self.get("config").json()
        self.assertEqual(reloaded["base_url"], "http://127.0.0.1:65432/v1")
        self.assertEqual(reloaded["model"], "fixture-model")
        self.assertTrue(reloaded["local_mode"])
        self.assertTrue(reloaded["offline"])
        self.assertIn("tectonic", reloaded["tools"])
        self.assertEqual(set(json.loads((self.state / "local-runtime.json").read_text())), {"base_url", "model"})

    def test_import_returns_reviewable_candidate_without_creating_or_overwriting_document(self):
        original = self.create()
        candidate = {"name": "notes.tex", "content": "OCR candidate", "requires_review": True,
                     "pages": [{"page": 1}], "model": "fixture-local", "local_mode": True}
        runtime = Mock()
        runtime.import_document.return_value = candidate
        body = {"name": "scan.png", "mime_type": "image/png", "data_base64": "fixture", "max_pages": 1}
        with patch.object(studio, "_local_runtime", return_value=runtime):
            response = self.post("import", body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), candidate)
        runtime.import_document.assert_called_once_with(body)
        self.assertEqual(self.get("file", name=original["name"]).json()["content"], original["content"])

    def test_all_new_product_routes_require_authorization(self):
        for route in ("files", "file", "config", "jobs", "fixstatus"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get("/api/studio/" + route).status_code, 401)
        for route in ("create", "save", "upload", "rename", "delete", "settings", "import", "math",
                      "jobs/" + "a" * 32 + "/decision", "jobs/" + "a" * 32 + "/cancel"):
            with self.subTest(route=route):
                self.assertEqual(self.client.post("/api/studio/" + route, json={}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
