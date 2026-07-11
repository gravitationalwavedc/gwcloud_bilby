from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.ini_utils import bilby_args_to_ini_string, bilby_ini_string_to_args


def _args_to_dict(args):
    return {key: getattr(args, key) for key in sorted(vars(args))}


def _normalize_value(value):
    if isinstance(value, list):
        if len(value) == 1:
            return _normalize_value(value[0])
        return [_normalize_value(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _assert_args_equivalent(test, left, right):
    left_dict = _args_to_dict(left)
    right_dict = _args_to_dict(right)
    test.assertEqual(set(left_dict), set(right_dict))
    for key in left_dict:
        test.assertEqual(
            _normalize_value(left_dict[key]),
            _normalize_value(right_dict[key]),
            key,
        )


class TestIniUtils(BilbyTestCase):
    def test_bilby_args_to_ini_string_roundtrip_default(self):
        ini = create_test_ini_string()
        args = bilby_ini_string_to_args(ini.encode("utf-8"))

        roundtrip_ini = bilby_args_to_ini_string(args)
        self.assertIsInstance(roundtrip_ini, str)
        self.assertIn("label", roundtrip_ini)

        roundtrip_args = bilby_ini_string_to_args(roundtrip_ini.encode("utf-8"))
        _assert_args_equivalent(self, args, roundtrip_args)

    def test_bilby_args_to_ini_string_roundtrip_custom_values(self):
        ini = create_test_ini_string(
            {
                "detectors": "['H1']",
                "label": "my-custom-label",
                "n-parallel": 4,
                "pn-phase-order": 12345,
            }
        )
        args = bilby_ini_string_to_args(ini.encode("utf-8"))

        roundtrip_ini = bilby_args_to_ini_string(args)
        self.assertIn("my-custom-label", roundtrip_ini)

        roundtrip_args = bilby_ini_string_to_args(roundtrip_ini.encode("utf-8"))
        _assert_args_equivalent(self, args, roundtrip_args)

        self.assertEqual(roundtrip_args.label, "my-custom-label")
        self.assertEqual(roundtrip_args.n_parallel, 4)
        self.assertEqual(roundtrip_args.pn_phase_order, 12345)
