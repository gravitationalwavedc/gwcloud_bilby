from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _parse_and_validate_ini


class TestParseAndValidateIni(BilbyTestCase):
    def test_returns_parsed_args_for_valid_ini(self):
        ini_content = create_test_ini_string({"detectors": "['H1']", "label": "valid_job_name"})
        args = _parse_and_validate_ini(ini_content)
        self.assertEqual(args.label, "valid_job_name")

    def test_raises_for_invalid_job_name(self):
        ini_content = create_test_ini_string({"detectors": "['H1']", "label": "bad"})
        with self.assertRaises(Exception) as ctx:
            _parse_and_validate_ini(ini_content)
        self.assertIn("at least 5 characters", str(ctx.exception))
