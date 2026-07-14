from django.test import override_settings

from bilbyui.constants import BILBY_JOB_TYPE_CHOICES, BilbyJobType
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBilbyJobTypeConstants(BilbyTestCase):
    def test_bilby_job_type_values(self):
        self.assertEqual(BilbyJobType.NORMAL, 0)
        self.assertEqual(BilbyJobType.UPLOADED, 1)
        self.assertEqual(BilbyJobType.EXTERNAL, 2)

    def test_bilby_job_type_choices(self):
        self.assertEqual(
            BILBY_JOB_TYPE_CHOICES,
            (
                (BilbyJobType.NORMAL, "Normal Job"),
                (BilbyJobType.UPLOADED, "Uploaded Job"),
                (BilbyJobType.EXTERNAL, "External Job"),
            ),
        )
