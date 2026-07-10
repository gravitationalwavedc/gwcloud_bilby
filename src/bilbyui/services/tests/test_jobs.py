from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, Label
from bilbyui.services.jobs import get_job, list_user_jobs, update_job
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestJobsService(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job1 = BilbyJob.objects.create(
            user_id=1,
            name="first_job",
            description="First job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.job2 = BilbyJob.objects.create(
            user_id=1,
            name="second_job",
            description="Second job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.other_user_job = BilbyJob.objects.create(
            user_id=2,
            name="other_job",
            description="Other user job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.event = EventID.objects.create(event_id="GW123456_123456", is_ligo_event=False)
        cls.label = Label.objects.create(name="Bad Run", description="Bad Run label")
        cls.protected_label = Label.objects.create(
            name="TestProtected",
            description="Protected label",
            protected=True,
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

    def test_update_job_with_description(self):
        success, message = update_job(self.job1.id, self.user, description="updated description")
        self.assertTrue(success)
        self.assertEqual(message, "Job saved!")
        self.job1.refresh_from_db()
        self.assertEqual(self.job1.description, "updated description")

    def test_update_job_with_private(self):
        success, message = update_job(self.job1.id, self.user, private=True)
        self.assertTrue(success)
        self.job1.refresh_from_db()
        self.assertTrue(self.job1.private)

    def test_update_job_with_labels(self):
        self.job1.labels.add(self.protected_label)
        success, message = update_job(self.job1.id, self.user, labels=["Bad Run"])
        self.assertTrue(success)
        self.job1.refresh_from_db()
        label_names = set(self.job1.labels.values_list("name", flat=True))
        self.assertEqual(label_names, {"Bad Run", "TestProtected"})

    def test_update_job_with_event_id(self):
        success, message = update_job(self.job1.id, self.user, event_id=self.event.event_id)
        self.assertTrue(success)
        self.job1.refresh_from_db()
        self.assertEqual(self.job1.event_id, self.event)

    def test_update_job_clears_event_id(self):
        self.job1.event_id = self.event
        self.job1.save()
        success, message = update_job(self.job1.id, self.user, event_id="")
        self.assertTrue(success)
        self.job1.refresh_from_db()
        self.assertIsNone(self.job1.event_id)

    @override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[3])
    def test_update_job_permitted_user_updates_event_id(self):
        self.user.id = 3
        success, message = update_job(self.other_user_job.id, self.user, event_id=self.event.event_id)
        self.assertTrue(success)
        self.assertEqual(message, "Job saved")
        self.other_user_job.refresh_from_db()
        self.assertEqual(self.other_user_job.event_id, self.event)

    def test_update_job_raises_for_non_owner(self):
        self.user.id = 2
        with self.assertRaises(Exception) as ctx:
            update_job(self.job1.id, self.user, description="not allowed")
        self.assertEqual(str(ctx.exception), "You must own the job to change it!")

    def test_get_job_raises_for_unknown_id(self):
        with self.assertRaises(BilbyJob.DoesNotExist):
            get_job(99999, self.user)
