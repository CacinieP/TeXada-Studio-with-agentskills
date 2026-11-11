"""Only actual stapler network failures may be retried; permanent errors propagate."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staple_bundle


class StapleTest(unittest.TestCase):
    def run_codes(self, codes):
        with patch.object(staple_bundle.subprocess, 'run', side_effect=[SimpleNamespace(returncode=c) for c in codes]) as run, \
                patch.object(staple_bundle.time, 'sleep') as sleep:
            code = staple_bundle.staple_and_validate(Path('/tmp/Example With Spaces.app'))
        return code, [call.args[0][2] for call in run.call_args_list], sleep.call_count

    def test_success_staples_then_validates(self):
        self.assertEqual(self.run_codes([0, 0]), (0, ['staple', 'validate'], 0))

    def test_transient_network_retries_cover_both_operations(self):
        self.assertEqual(self.run_codes([68, 0, 68, 0]),
                         (0, ['staple', 'staple', 'validate', 'validate'], 2))

    def test_permanent_error_does_not_retry_or_validate(self):
        self.assertEqual(self.run_codes([65]), (65, ['staple'], 0))

    def test_exhausted_network_retry_is_still_a_failure(self):
        self.assertEqual(self.run_codes([68, 68, 68]), (68, ['staple', 'staple', 'staple'], 2))


if __name__ == '__main__':
    unittest.main()
