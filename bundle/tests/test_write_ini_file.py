import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tests.utils import args_to_bilby_ini


class TestWriteIniFile(TestCase):
    def setUp(self):
        # Make the _bundledb stub importable so core.submit can be imported
        misc_dir = str(Path(__file__).parent / "misc")
        sys.path.append(misc_dir)
        self.addCleanup(sys.path.remove, misc_dir)

    def test_write_ini_file_round_trip(self):
        # Build args the same way submit() does, then write the complete ini file
        # and verify it can be re-parsed back to equivalent args
        ini = args_to_bilby_ini(
            {
                "label": "test-write-ini",
                "detectors": ["H1"],
                "trigger-time": "12345678",
                "injection-numbers": [],
            }
        ).decode("utf-8")

        from core.submit import bilby_ini_to_args, write_ini_file

        args = bilby_ini_to_args(ini)

        with TemporaryDirectory() as td:
            args.outdir = td

            args, inputs = write_ini_file(args, td)

            # The complete ini file should be written into the working directory
            complete_ini = os.path.join(td, "test-write-ini_config_complete.ini")
            self.assertTrue(os.path.exists(complete_ini))

            # The returned MainInput should point at the complete ini file
            self.assertEqual(
                inputs.complete_ini_file, "./test-write-ini_config_complete.ini"
            )

            # Round-trip: re-parse the written ini and check the key args survive
            with open(complete_ini) as f:
                reparsed = bilby_ini_to_args(f.read())

            self.assertEqual(reparsed.label, "test-write-ini")
            self.assertEqual(reparsed.detectors, ["'H1'"])
            self.assertEqual(reparsed.trigger_time, "12345678")
            self.assertEqual(reparsed.outdir, td)
