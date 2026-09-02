from types import SimpleNamespace
from unittest import mock

from bilbyui.services.jobs import _fetch_job_controller_jobs
from bilbyui.tests.testcases import BilbyTestCase


def _job(job_id, job_controller_id):
    return SimpleNamespace(id=job_id, job_controller_id=job_controller_id)


class TestFetchJobControllerJobs(BilbyTestCase):
    def test_empty_job_controller_ids_returns_empty(self):
        jobs = [_job(1, None), _job(2, "")]
        self.assertEqual(_fetch_job_controller_jobs(jobs, 1), {})

    @mock.patch("bilbyui.services.jobs.request_job_filter")
    def test_populated_path_returns_filtered_mapping(self, mock_request_job_filter):
        mock_request_job_filter.return_value = (
            "OK",
            [
                {"id": 42, "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}]},
                {"id": 999, "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}]},
            ],
        )

        jobs = [_job(10, 42), _job(11, 999)]

        result = _fetch_job_controller_jobs(jobs, 7)

        self.assertEqual(list(result.keys()), [10, 11])
        self.assertEqual(result[10]["id"], 42)
        self.assertEqual(result[11]["id"], 999)
        mock_request_job_filter.assert_called_once_with(7, ids={42, 999})

    @mock.patch("bilbyui.services.jobs.request_job_filter")
    def test_non_ok_status_returns_empty(self, mock_request_job_filter):
        mock_request_job_filter.return_value = ("UNKNOWN", [])

        jobs = [_job(10, 42)]

        self.assertEqual(_fetch_job_controller_jobs(jobs, 7), {})
