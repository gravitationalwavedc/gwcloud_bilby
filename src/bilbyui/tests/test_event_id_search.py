from django.test import override_settings

from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestEventIdSearch(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Event id job",
            description="A job to edit the event id of",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Event id job"}),
        )
        self.event = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="nick-one",
        )
        self.url = "/event-ids/"

    def test_empty_query_returns_prompt(self):
        response = self.client.get(self.url, {"q": "", "job_id": self.job.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Type to search")

    def test_missing_job_id_returns_404(self):
        response = self.client.get(self.url, {"q": "GW123456"})

        self.assertEqual(response.status_code, 404)

    def test_no_matches_returns_no_matches(self):
        response = self.client.get(self.url, {"q": "no-such-event", "job_id": self.job.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No matches")

    def test_matches_returns_result_list(self):
        response = self.client.get(self.url, {"q": "GW123456", "job_id": self.job.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "list-group")
        self.assertContains(response, "GW123456_123456")
        self.assertContains(response, "S123456a")
