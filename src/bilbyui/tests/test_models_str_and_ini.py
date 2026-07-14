from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, Label
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestModelStrAndIniGuards(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.label = Label.objects.create(name="Test Label")
        cls.event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=1126259462.391,
        )
        cls.job = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="Test_Job",
            description="Test job description",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_label_str(self):
        self.assertEqual(str(self.label), "Label: Test Label")

    def test_event_id_str(self):
        self.assertEqual(str(self.event_id), "EventID: GW123456_123456")

    def test_bilby_job_str(self):
        self.assertEqual(str(self.job), "Bilby Job: Test_Job")

    def test_save_skips_ini_updates_when_empty(self):
        # A job with no ini_string should still save without error and should skip
        # the ini parsing / elastic search update steps.
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Empty_Ini_Job",
            description="Job without an ini string",
            private=False,
            ini_string="",
        )
        job.save()
        job.refresh_from_db()
        self.assertEqual(job.name, "Empty_Ini_Job")

    def test_elastic_search_update_returns_when_ignored(self):
        # With IGNORE_ELASTIC_SEARCH enabled elastic_search_update returns early before
        # touching elastic search.
        self.assertIsNone(self.job.elastic_search_update())

    def test_elastic_search_update_returns_when_empty_ini(self):
        # With elastic search enabled but no ini_string, elastic_search_update returns early
        # before connecting to elastic search.
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Empty_Ini_ES_Job",
            description="Job without an ini string",
            private=False,
            ini_string="",
        )
        with override_settings(IGNORE_ELASTIC_SEARCH=False):
            self.assertIsNone(job.elastic_search_update())
