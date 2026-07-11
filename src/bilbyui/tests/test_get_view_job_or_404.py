from unittest import mock

from django.http import Http404

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _get_view_job_or_404


class TestGetViewJobOr404(BilbyTestCase):
    def setUp(self):
        self.authenticate()
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Viewable job",
            description="A job to view",
            job_controller_id=10001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Viewable job"}),
        )

    def test_returns_job_when_accessible(self):
        job = _get_view_job_or_404(self.job.id, self.user)

        self.assertEqual(job, self.job)

    def test_raises_404_for_missing_job(self):
        with self.assertRaises(Http404):
            _get_view_job_or_404(99999, self.user)

    def test_raises_404_when_access_denied_by_filter(self):
        ligo_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="LIGO job",
            description="ligo only",
            job_controller_id=10002,
            private=False,
            is_ligo_job=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "LIGO job"}),
        )

        with self.assertRaises(Http404):
            _get_view_job_or_404(ligo_job.id, self.user)

    @mock.patch("bilbyui.views.get_job")
    def test_raises_404_on_generic_exception(self, mock_get_job):
        mock_get_job.side_effect = RuntimeError("unexpected")

        with self.assertRaises(Http404):
            _get_view_job_or_404(self.job.id, self.user)
