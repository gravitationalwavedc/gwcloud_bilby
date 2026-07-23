import bilby_pipe
from bilby_pipe.data_generation import DataGenerationInput

from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.ini_utils import bilby_ini_string_to_args
from bilbyui.views import bilby_ini_args_to_data_input


def _args_from_ini(config):
    return bilby_ini_string_to_args(create_test_ini_string(config).encode("utf-8"))


class TestBilbyIniArgsToDataInput(BilbyTestCase):
    def test_clears_file_fields_and_returns_data_generation_input(self):
        args = _args_from_ini(
            {
                "detectors": "['H1']",
                "gps-file": "/tmp/gps.dat",
                "timeslide-file": "/tmp/timeslide.dat",
                "injection-file": "/tmp/injection.dat",
                "psd-dict": "{'H1': '/tmp/psd'}",
            },
        )

        result = bilby_ini_args_to_data_input(args)

        self.assertIsInstance(result, DataGenerationInput)
        self.assertIsNone(args.gps_file)
        self.assertIsNone(args.timeslide_file)
        self.assertIsNone(args.injection_file)
        self.assertIsNone(args.psd_dict)
        self.assertIsNone(args.ini)

    def test_sets_idx_when_generation_seed_present_without_idx(self):
        args = _args_from_ini({"detectors": "['H1']", "generation-seed": "42"})
        args.idx = 3
        delattr(args, "idx")

        bilby_ini_args_to_data_input(args)

        self.assertEqual(args.idx, 0)

    def test_preserves_idx_when_generation_seed_and_idx_set(self):
        args = _args_from_ini({"detectors": "['H1']", "generation-seed": "42"})
        args.idx = 7

        bilby_ini_args_to_data_input(args)

        self.assertEqual(args.idx, 7)

    def test_clears_non_default_prior_file(self):
        args = _args_from_ini({"detectors": "['H1']", "prior-file": "/custom/prior.json"})

        bilby_ini_args_to_data_input(args)

        self.assertIsNone(args.prior_file)

    def test_keeps_default_prior_file(self):
        default_prior = next(iter(bilby_pipe.main.Input([], []).default_prior_files))
        args = _args_from_ini({"detectors": "['H1']", "prior-file": default_prior})

        bilby_ini_args_to_data_input(args)

        self.assertEqual(args.prior_file, default_prior)

    def test_idx_none_without_generation_seed(self):
        args = _args_from_ini({"detectors": "['H1']"})
        args.idx = None

        bilby_ini_args_to_data_input(args)

        self.assertIsNone(args.idx)
