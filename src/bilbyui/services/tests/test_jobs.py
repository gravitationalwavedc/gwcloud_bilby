from bilbyui.models import BilbyJob
from bilbyui.services.jobs import get_job, list_user_jobs, update_job
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestJobsService(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.other_user = cls.create_user(id=2, name="other user", primary_email="other@gmail.com")
        cls.job1 = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="first_job",
            description="First job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.job2 = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="second_job",
            description="Second job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.other_user_job = BilbyJob.objects.create(
            user_id=cls.other_user.id,
            name="other_job",
            description="Other user job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def setUp(self):
        self.authenticate()

    def test_list_user_jobs_returns_expected_jobs(self):
        result = list_user_jobs(self.user)
        job_ids = [job.id for job in result["jobs"]]
        self.assertEqual(job_ids, [self.job2.id, self.job1.id])
        self.assertFalse(result["has_next"])
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 20)

    def test_list_user_jobs_pagination_page_two(self):
        result = list_user_jobs(self.user, page=2, page_size=1)
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0].id, self.job1.id)
        self.assertFalse(result["has_next"])
        self.assertEqual(result["page"], 2)

    def test_update_job_with_name(self):
        success, message = update_job(self.job1.id, self.user, name="renamed_job")
        self.assertTrue(success)
        self.assertEqual(message, "Job saved!")
        self.job1.refresh_from_db()
        self.assertEqual(self.job1.name, "renamed_job")

    def test_get_job_raises_for_unknown_id(self):
        with self.assertRaises(BilbyJob.DoesNotExist):
            get_job(99999, self.user)
