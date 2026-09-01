from types import SimpleNamespace
from unittest import mock

from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.status import JobStatus
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _job_status_name


def _job(job_type):
    return SimpleNamespace(id=1, job_type=job_type)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestJobStatusName(BilbyTestCase):
    def test_normal_without_controller_job_returns_unknown(self):
        self.assertEqual(_job_status_name(_job(BilbyJobType.NORMAL), {}), "Unknown")

    def test_normal_without_history_returns_unknown(self):
        controller_jobs = {1: {}}
        self.assertEqual(_job_status_name(_job(BilbyJobType.NORMAL), controller_jobs), "Unknown")

    def test_normal_with_empty_history_returns_unknown(self):
        controller_jobs = {1: {"history": []}}
        self.assertEqual(_job_status_name(_job(BilbyJobType.NORMAL), controller_jobs), "Unknown")

    @mock.patch("bilbyui.views.derive_job_status", return_value=(JobStatus.COMPLETED, "Completed", None))
    def test_normal_with_history_uses_derive_job_status(self, mock_derive):
        controller_jobs = {1: {"history": [{"state": JobStatus.COMPLETED, "timestamp": "2020-01-01 00:00:00 UTC"}]}}

        self.assertEqual(_job_status_name(_job(BilbyJobType.NORMAL), controller_jobs), "Completed")
        mock_derive.assert_called_once_with(controller_jobs[1]["history"])

    def test_uploaded_returns_completed(self):
        self.assertEqual(_job_status_name(_job(BilbyJobType.UPLOADED), {}), "Completed")

    def test_external_returns_completed(self):
        self.assertEqual(_job_status_name(_job(BilbyJobType.EXTERNAL), {}), "Completed")

    def test_unknown_job_type_returns_unknown(self):
        self.assertEqual(_job_status_name(_job(99), {}), "Unknown")
