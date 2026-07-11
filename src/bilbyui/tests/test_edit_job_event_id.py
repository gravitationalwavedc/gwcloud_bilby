from django.conf import settings

from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestEditJobEventId(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.event = EventID.create(
            event_id="GW150914_123456",
            gps_time=1126259462.391,
            trigger_id="S123456a",
            nickname="GW150914",
            is_ligo_event=False,
        )
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="viewable_job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "viewable_job"}),
        )
        self.base_url = f"/job-results/{self.job.id}/"
        self.search_url = "/event-ids/"

    def test_search_returns_matches(self):
        response = self.client.get(
            self.search_url,
            {"q": "GW150914", "job_id": self.job.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GW150914_123456")
        self.assertContains(response, "S123456a")
        self.assertContains(response, f'hx-target="#event-id-field-{self.job.id}"')

    def test_search_empty(self):
        response = self.client.get(self.search_url, {"q": ""})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Type to search")

    def test_search_no_match(self):
        response = self.client.get(
            self.search_url,
            {"q": "nonexistent", "job_id": self.job.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No matches")

    def test_set_event_id(self):
        response = self.client.post(
            f"{self.base_url}edit/event-id/",
            {"event_id": self.event.event_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast, close-modal")
        self.assertContains(response, self.event.event_id)
        self.assertContains(response, "Clear")
        self.job.refresh_from_db()
        self.assertEqual(self.job.event_id, self.event)

    def test_clear_event_id(self):
        self.job.event_id = self.event
        self.job.save()

        response = self.client.post(
            f"{self.base_url}edit/event-id/",
            {"event_id": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Trigger"], "save-toast, close-modal")
        self.assertContains(response, "No event ID set")
        self.assertNotContains(response, "Clear")
        self.job.refresh_from_db()
        self.assertIsNone(self.job.event_id)

    def test_invalid_event_id_returns_400(self):
        response = self.client.post(
            f"{self.base_url}edit/event-id/",
            {"event_id": "GW999999_999999"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "not found", status_code=400)
        self.job.refresh_from_db()
        self.assertIsNone(self.job.event_id)

    def test_other_users_job_returns_404(self):
        other_user = self.create_user(id=self.user.id + 1, name="other user", primary_email="other@gmail.com")
        other_job = BilbyJob.objects.create(
            user_id=other_user.id,
            name="other_users_job",
            description="hidden",
            job_controller_id=10002,
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "other_users_job"}),
        )
        other_base_url = f"/job-results/{other_job.id}/"

        response = self.client.post(
            f"{other_base_url}edit/event-id/",
            {"event_id": self.event.event_id},
        )

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_redirected(self):
        self.deauthenticate()
        response = self.client.post(
            f"{self.base_url}edit/event-id/",
            {"event_id": self.event.event_id},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{settings.LOGIN_URL}?next={self.base_url}edit/event-id/",
        )
