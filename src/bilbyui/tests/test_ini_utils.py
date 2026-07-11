from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.ini_utils import bilby_args_to_ini_string, bilby_ini_string_to_args


class TestBilbyIniStringToArgs(BilbyTestCase):
    def test_parses_minimal_ini_string(self):
        ini = create_test_ini_string({"label": "round-trip-job"}, complete=True)
        args = bilby_ini_string_to_args(ini.encode("utf-8"))

        self.assertEqual(args.label, "round-trip-job")
        self.assertEqual(args.duration, 4)
        self.assertEqual(len(args.detectors), 2)

    def test_removes_ini_and_verbose_attributes(self):
        ini = create_test_ini_string({"label": "attr-check"})
        args = bilby_ini_string_to_args(ini.encode("utf-8"))

        self.assertFalse(hasattr(args, "ini"))
        self.assertFalse(hasattr(args, "verbose"))

    def test_round_trip_through_args_to_ini_string(self):
        ini = create_test_ini_string({"label": "round-trip", "duration": 8}, complete=True)
        args = bilby_ini_string_to_args(ini.encode("utf-8"))
        round_trip_args = bilby_ini_string_to_args(
            bilby_args_to_ini_string(args).encode("utf-8"),
        )

        self.assertEqual(round_trip_args.label, "round-trip")
        self.assertEqual(round_trip_args.duration, args.duration)
        self.assertEqual(round_trip_args.sampler, args.sampler)
