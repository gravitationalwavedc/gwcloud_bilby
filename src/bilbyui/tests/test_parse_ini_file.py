from unittest import mock

from django.test import override_settings

from bilbyui.models import BilbyJob, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.parse_ini_file import parse_ini_file


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestParseIniFileErrorBranches(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.job = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="test job",
            description="test job",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_missing_detectors_raises(self):
        # An ini that omits detectors should trigger the "Detectors must be set" branch
        self.job.ini_string = "label=no-detectors-job"

        with self.assertRaisesMessage(Exception, "Detectors must be set"):
            parse_ini_file(self.job)

    def test_data_input_exception_is_logged(self):
        # If bilby_ini_args_to_data_input raises, the error should be logged and swallowed
        self.job.ini_string = create_test_ini_string({"detectors": "['H1']"})

        with (
            mock.patch(
                "bilbyui.views.bilby_ini_args_to_data_input",
                side_effect=RuntimeError("boom"),
            ),
            self.assertLogs("bilbyui.utils.parse_ini_file", level="ERROR") as logs,
        ):
            parse_ini_file(self.job)

        self.assertIn("Error parsing INI file", "\n".join(logs.output))

        # Unprocessed k/v pairs are still persisted despite the data-input failure
        self.assertTrue(IniKeyValue.objects.filter(job=self.job, processed=False).exists())
        self.assertFalse(IniKeyValue.objects.filter(job=self.job, processed=True).exists())
