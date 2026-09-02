from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_result_file_entries


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBuildResultFileEntries(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ini = create_test_ini_string({"detectors": "['H1']"})
        cls.user = cls.create_user()

    def setUp(self):
        self.create_user(id=1)

    def test_external_job_with_no_external_record_returns_empty(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="external_job",
            description="external",
            job_type=BilbyJobType.EXTERNAL,
            ini_string=self.ini,
        )

        self.assertEqual(_build_result_file_entries(job), [])
