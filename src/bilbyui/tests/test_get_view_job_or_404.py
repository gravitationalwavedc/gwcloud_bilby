from unittest import mock

from django.http import Http404
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _get_view_job_or_404


@override_settings(EMBARGO_START_TIME=100.0)
class TestGetViewJobOr404(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Viewable job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            trigger_time=99.0,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_returns_job_when_accessible(self):
        self.assertEqual(_get_view_job_or_404(self.job.id, self.user), self.job)

    def test_raises_404_for_missing_job(self):
        with self.assertRaises(Http404):
            _get_view_job_or_404(99999, self.user)

    def test_raises_404_for_direct_event_tainted_job(self):
        self.job.event_id = EventID.objects.create(
            event_id="GW123456",
            gps_time=100.0,
        )
        self.job.save(update_fields=["event_id"])
        with self.assertRaises(Http404):
            _get_view_job_or_404(self.job.id, self.user)

    def test_legacy_flag_does_not_deny_view(self):
        self.job.is_ligo_job = True
        self.job.save(update_fields=["is_ligo_job"])
        self.assertEqual(_get_view_job_or_404(self.job.id, self.user), self.job)

    @mock.patch("bilbyui.views.get_job")
    def test_raises_404_on_permission_error(self, mock_get_job):
        mock_get_job.side_effect = PermissionError("permission denied")
        with self.assertRaises(Http404):
            _get_view_job_or_404(self.job.id, self.user)

    def test_raises_404_for_non_numeric_job_id(self):
        with self.assertRaises(Http404):
            _get_view_job_or_404("abc", self.user)
