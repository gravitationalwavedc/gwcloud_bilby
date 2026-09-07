import sys
from pathlib import Path
from unittest import TestCase

from tests.utils import args_to_bilby_ini


class TestBilbyIniToArgs(TestCase):
    def setUp(self):
        sys.path.append(str(Path(__file__).parent / "misc"))

    def tearDown(self):
        sys.path = sys.path[:-1]

    def test_parses_valid_ini_into_args_namespace(self):
        from core.submit import bilby_ini_to_args

        ini = args_to_bilby_ini(
            {
                "label": "test-label",
                "detectors": ["H1"],
                "trigger-time": "12345678",
                "channel-dict": {"H1": "GWOSC"},
                "gaussian-noise": True,
                "n-simulation": 1,
            }
        ).decode("utf-8")

        args = bilby_ini_to_args(ini)

        self.assertEqual(args.label, "test-label")
        self.assertEqual(args.detectors, ["'H1'"])
        self.assertEqual(args.trigger_time, "12345678")
        self.assertEqual(args.channel_dict, "{'H1': 'GWOSC'}")
        self.assertTrue(args.gaussian_noise)
        self.assertEqual(args.n_simulation, 1)
