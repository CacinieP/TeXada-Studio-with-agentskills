"""Formula transfer boundaries must follow TeX lexical context, without I/O."""

import copy
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics.handoff import build_envelope, HandoffError, sha256, validate_response


def request(content, original="x+"):
    start = content.index(original)
    return {"name": "input.tex", "content": content, "revision": 1,
            "source_range": {"start": start, "end": start + len(original), "encoding": "unicode-codepoints"},
            "requested_action": "repair", "transfer_id": str(uuid.uuid4())}


def response(envelope, candidate):
    binding = {"input_hash": envelope["input_sha256"], "parent_revision": None,
               "candidate_hash": sha256(candidate), "current_revision": 1}
    return {**copy.deepcopy(envelope), "status": "review_required", "candidate": candidate,
            "candidate_sha256": sha256(candidate), "parent_revision": None, "candidate_revision": 1,
            "diff": {}, "evidence": {"mutation_scope": {}, "cas_transition": {}},
            "inference_fingerprint": {}, "review": {"id": "review-1", "status": "pending", "binding": binding}}


class HandoffContextTests(unittest.TestCase):
    def test_comment_raw_literal_and_definition_cannot_supply_transfer_range(self):
        documents = ["% $x+$", r"\verb|$x+$|", r"\begin{verbatim}$x+$\end{verbatim}",
                     r"\begin{lstlisting}$x+$\end{lstlisting}", r"\newcommand{\example}{$x+$}",
                     r"\def\example{$x+$}", r"\catcode`\$=12 $x+$"]
        for document in documents:
            with self.subTest(document=document), self.assertRaisesRegex(HandoffError, "range_is_not_one_inline_formula"):
                build_envelope(request(document))

    def test_only_complete_dollar_inline_body_is_transferred(self):
        for document in (r"$$x+$$", r"\(x+\)", r"\[x+\]", r"\begin{equation}x+\end{equation}", "$x+"):
            with self.subTest(document=document), self.assertRaisesRegex(HandoffError, "range_is_not_one_inline_formula"):
                build_envelope(request(document))
        self.assertEqual(build_envelope(request("😀 $x+$"))["original_latex"], "x+")

    def test_even_backslashes_do_not_escape_an_opening_dollar(self):
        document = r"\\$x+$"
        self.assertEqual(build_envelope(request(document))["original_latex"], "x+")

    def test_dollar_after_even_backslashes_cannot_escape_candidate_body(self):
        envelope = build_envelope(request("$x+$"))
        for candidate in ("x+$", r"x+\\$ outside", r"x+\\\\$ outside"):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(HandoffError, "invalid_handoff_candidate"):
                validate_response(envelope, response(envelope, candidate))
        for candidate in (r"x+\$", r"x+\\\$"):
            with self.subTest(candidate=candidate):
                self.assertEqual(validate_response(envelope, response(envelope, candidate))["candidate"], candidate)

    def test_candidate_cannot_hide_or_escape_the_existing_closing_delimiter(self):
        envelope = build_envelope(request("$x+$"))
        for candidate in ("x+\\", "x+% hidden closing delimiter", r"x+\\% hidden closing delimiter"):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(HandoffError, "invalid_handoff_candidate"):
                validate_response(envelope, response(envelope, candidate))
        for candidate in (r"x+\\", r"x+\%"):
            with self.subTest(candidate=candidate):
                self.assertEqual(validate_response(envelope, response(envelope, candidate))["candidate"], candidate)


if __name__ == "__main__":
    unittest.main()
