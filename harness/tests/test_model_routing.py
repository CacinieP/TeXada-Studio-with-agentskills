"""Per-task model routing defaults (#23): REPAIR_MODEL wins over VLM_MODEL.

Offline-only; the OCR line's OCR_MODEL is read separately by doc-ocr-extract.
"""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docforensics.__main__ import DEFAULT_REPAIR_MODEL, repair_model_default  # noqa: E402


class RepairModelDefaultTest(unittest.TestCase):
    def test_repair_model_takes_priority_over_vlm_model(self):
        self.assertEqual(repair_model_default({"REPAIR_MODEL": "m-a", "VLM_MODEL": "m-b"}), "m-a")
        self.assertEqual(repair_model_default({"VLM_MODEL": "m-b"}), "m-b")
        self.assertEqual(repair_model_default({}), DEFAULT_REPAIR_MODEL)

    def test_blank_values_fall_through_like_unset(self):
        self.assertEqual(repair_model_default({"REPAIR_MODEL": "", "VLM_MODEL": "m-b"}), "m-b")
        self.assertEqual(repair_model_default({"REPAIR_MODEL": "   ", "VLM_MODEL": "m-b"}), "m-b")
        self.assertEqual(repair_model_default({"REPAIR_MODEL": "  m-c  "}), "m-c")
        self.assertEqual(repair_model_default({"REPAIR_MODEL": None}), DEFAULT_REPAIR_MODEL)

    def test_non_string_env_values_are_ignored(self):
        self.assertEqual(repair_model_default({"REPAIR_MODEL": 42, "VLM_MODEL": "m-b"}), "m-b")


if __name__ == "__main__":
    unittest.main()
