from unittest.mock import Mock, patch

from bilbyui.schema import _cache_job_controller_jobs
from bilbyui.tests.testcases import BilbyTestCase


class TestCacheJobControllerJobs(BilbyTestCase):
    def _make_queryset(self, job_controller_ids):
        queryset = Mock()
        queryset.exclude.return_value.values_list.return_value = job_controller_ids
        return queryset

    def test_no_job_controller_ids_skips_request(self):
        queryset = self._make_queryset([])
        context = Mock()

        with patch("bilbyui.schema.request_job_filter") as mock_request:
            _cache_job_controller_jobs(queryset, user_id=1, context=context)

        mock_request.assert_not_called()
        self.assertEqual(context.job_controller_jobs, {})

    def test_populated_path_filters_to_dicts_with_id(self):
        queryset = self._make_queryset([1, 2, 3])
        context = Mock()

        controller_response = [
            {"id": 1, "name": "first"},
            "not-a-dict",
            {"id": 2, "name": "second"},
            {"name": "missing-id"},
        ]

        with patch("bilbyui.schema.request_job_filter", return_value=("OK", controller_response)) as mock_request:
            _cache_job_controller_jobs(queryset, user_id=7, context=context)

        mock_request.assert_called_once_with(7, ids=[1, 2, 3])
        self.assertEqual(
            context.job_controller_jobs,
            {1: {"id": 1, "name": "first"}, 2: {"id": 2, "name": "second"}},
        )

    def test_empty_controller_response_caches_empty_dict(self):
        queryset = self._make_queryset([1])
        context = Mock()

        with patch("bilbyui.schema.request_job_filter", return_value=("OK", [])):
            _cache_job_controller_jobs(queryset, user_id=1, context=context)

        self.assertEqual(context.job_controller_jobs, {})
