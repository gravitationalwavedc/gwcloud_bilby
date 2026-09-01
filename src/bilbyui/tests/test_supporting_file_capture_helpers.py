import bilby_pipe

from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.ini_utils import bilby_ini_string_to_args
from bilbyui.views import _capture_supporting_files, _strip_supporting_file_args


def _args_from_ini(config):
    return bilby_ini_string_to_args(create_test_ini_string(config).encode("utf-8"))


class TestCaptureSupportingFiles(BilbyTestCase):
    def test_captures_all_supporting_files(self):
        args = _args_from_ini(
            {
                "detectors": "['H1']",
                "prior-file": "/custom/prior.json",
                "gps-file": "/tmp/gps.dat",
                "timeslide-file": "/tmp/timeslide.dat",
                "injection-file": "/tmp/injection.dat",
                "psd-dict": "{'H1': '/tmp/psd'}",
            }
        )

        result = _capture_supporting_files(args)

        self.assertEqual(
            result,
            ("/custom/prior.json", "/tmp/gps.dat", "/tmp/timeslide.dat", "/tmp/injection.dat", "{'H1': '/tmp/psd'}"),
        )

    def test_default_prior_file_not_captured(self):
        default_prior = next(iter(bilby_pipe.main.Input([], []).default_prior_files))
        args = _args_from_ini({"detectors": "['H1']", "prior-file": default_prior})

        result = _capture_supporting_files(args)

        self.assertIsNone(result[0])

    def test_captures_none_when_no_supporting_files(self):
        args = _args_from_ini({"detectors": "['H1']"})

        result = _capture_supporting_files(args)

        self.assertEqual(result, (None, None, None, None, None))


class TestStripSupportingFileArgs(BilbyTestCase):
    def test_strips_non_default_supporting_files(self):
        args = _args_from_ini(
            {
                "detectors": "['H1']",
                "prior-file": "/custom/prior.json",
                "gps-file": "/tmp/gps.dat",
                "timeslide-file": "/tmp/timeslide.dat",
                "injection-file": "/tmp/injection.dat",
                "psd-dict": "{'H1': '/tmp/psd'}",
            }
        )

        _strip_supporting_file_args(args)

        self.assertIsNone(args.prior_file)
        self.assertIsNone(args.gps_file)
        self.assertIsNone(args.timeslide_file)
        self.assertIsNone(args.injection_file)
        self.assertIsNone(args.psd_dict)

    def test_keeps_default_prior_file(self):
        default_prior = next(iter(bilby_pipe.main.Input([], []).default_prior_files))
        args = _args_from_ini({"detectors": "['H1']", "prior-file": default_prior})

        _strip_supporting_file_args(args)

        self.assertEqual(args.prior_file, default_prior)
