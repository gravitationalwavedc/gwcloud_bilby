from unittest import mock

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, EventID, Label
from bilbyui.status import JobStatus
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_user_job_rows


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBuildUserJobRows(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ini = create_test_ini_string({"detectors": "['H1']"})
        cls.event = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
        )
        cls.label = Label.objects.get(name="Production Run")

    def setUp(self):
        self.authenticate()

    def _make_job(self, **kwargs):
        defaults = {
            "user_id": self.user.id,
            "name": "test_job",
            "description": "Test description",
            "ini_string": self.ini,
            "job_type": BilbyJobType.NORMAL,
            "job_controller_id": None,
        }
        defaults.update(kwargs)
        return BilbyJob.objects.create(**defaults)

    @mock.patch("bilbyui.views.request_job_filter")
    def test_normal_job_with_controller_status(self, request_job_filter):
        job = self._make_job(job_controller_id=42)
        request_job_filter.return_value = (
            "OK",
            [{"id": 42, "history": [{"state": JobStatus.RUNNING, "timestamp": "2020-01-01 12:00:00 UTC"}]}],
        )

        rows = _build_user_job_rows({"jobs": [job], "page_size": 20}, self.user)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], job.id)
        self.assertEqual(rows[0]["user"], self.user.name)
        self.assertEqual(rows[0]["name"], "test_job")
        self.assertEqual(rows[0]["description"], "Test description")
        self.assertEqual(rows[0]["status_name"], "Running")
        self.assertEqual(rows[0]["status_badge_class"], "info")
        self.assertEqual(rows[0]["labels"], [])
        self.assertEqual(rows[0]["event_id_values"], [])

    @mock.patch("bilbyui.views.request_job_filter")
    def test_normal_job_missing_controller_record_shows_unknown(self, request_job_filter):
        job = self._make_job(job_controller_id=99)
        request_job_filter.return_value = ("OK", [])

        rows = _build_user_job_rows({"jobs": [job], "page_size": 20}, self.user)

        self.assertEqual(rows[0]["status_name"], "Unknown")
        self.assertEqual(rows[0]["status_badge_class"], "dark")

    @mock.patch("bilbyui.views.request_job_filter")
    def test_uploaded_job_shows_completed(self, request_job_filter):
        job = self._make_job(job_type=BilbyJobType.UPLOADED)

        rows = _build_user_job_rows({"jobs": [job], "page_size": 20}, self.user)

        self.assertEqual(rows[0]["status_name"], "Completed")
        self.assertEqual(rows[0]["status_badge_class"], "primary")
        request_job_filter.assert_not_called()

    @mock.patch("bilbyui.views.request_job_filter")
    def test_external_job_shows_completed(self, request_job_filter):
        job = self._make_job(job_type=BilbyJobType.EXTERNAL)

        rows = _build_user_job_rows({"jobs": [job], "page_size": 20}, self.user)

        self.assertEqual(rows[0]["status_name"], "Completed")
        request_job_filter.assert_not_called()

    @mock.patch("bilbyui.views.request_job_filter")
    def test_unknown_job_type_shows_unknown(self, request_job_filter):
        job = self._make_job(job_type=99)

        rows = _build_user_job_rows({"jobs": [job], "page_size": 20}, self.user)

        self.assertEqual(rows[0]["status_name"], "Unknown")
        request_job_filter.assert_not_called()

    @mock.patch("bilbyui.views.request_job_filter")
    def test_empty_description_becomes_blank_string(self, request_job_filter):
        job = self._make_job(description=None, job_type=BilbyJobType.UPLOADED)

        rows = _build_user_job_rows({"jobs": [job], "page_size": 20}, self.user)

        self.assertEqual(rows[0]["description"], "")

    @mock.patch("bilbyui.views.request_job_filter")
    def test_includes_labels_and_event_id_values(self, request_job_filter):
        job = self._make_job(job_type=BilbyJobType.UPLOADED, event_id=self.event)
        job.labels.add(self.label)

        rows = _build_user_job_rows({"jobs": [job], "page_size": 20}, self.user)

        self.assertEqual(list(rows[0]["labels"]), [self.label])
        self.assertEqual(
            rows[0]["event_id_values"],
            ["GW123456_123456", "S123456a", "GW123456"],
        )

    @mock.patch("bilbyui.views.request_job_filter")
    def test_respects_page_size_slice(self, request_job_filter):
        jobs = [self._make_job(name=f"job_{i}", job_type=BilbyJobType.UPLOADED) for i in range(3)]

        rows = _build_user_job_rows({"jobs": jobs, "page_size": 2}, self.user)

        self.assertEqual(len(rows), 2)
