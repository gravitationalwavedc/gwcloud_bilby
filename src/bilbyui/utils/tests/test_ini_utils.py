from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.ini_utils import bilby_args_to_ini_string, bilby_ini_string_to_args


class TestIniUtils(BilbyTestCase):
    def test_bilby_args_to_ini_string_round_trip(self):
        ini_string = create_test_ini_string({"detectors": "['H1']", "label": "roundtrip_job"})
        args = bilby_ini_string_to_args(ini_string.encode("utf-8"))
        round_trip = bilby_args_to_ini_string(args)
        round_trip_args = bilby_ini_string_to_args(round_trip.encode("utf-8"))

        self.assertEqual(args.detectors, round_trip_args.detectors)
        self.assertEqual(args.label, round_trip_args.label)

    def test_bilby_args_to_ini_string_returns_parseable_ini(self):
        ini_string = create_test_ini_string({"detectors": "['H1', 'L1']", "label": "ini_export"})
        args = bilby_ini_string_to_args(ini_string.encode("utf-8"))
        result = bilby_args_to_ini_string(args)

        self.assertIsInstance(result, str)
        self.assertIn("label", result)
        self.assertIn("detectors", result)
