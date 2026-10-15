import json
import logging

import responses
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from bilbyui.utils.jobs.request_job_filter import JOB_FILTER_BATCH_SIZE, request_job_filter


@override_settings(ALLOW_HTTP_LEAKS=True)
class TestRequestJobFilter(SimpleTestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.base_url = f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/job/"

    def test_success_no_query_params(self):
        jobs = [{"id": 1}, {"id": 2}]
        self.responses.add(
            responses.GET,
            f"{self.base_url}?",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(123)

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

    def test_error_fallback(self):
        try:
            logging.disable(logging.CRITICAL)

            self.responses.add(responses.GET, f"{self.base_url}?", status=500)

            status, result = request_job_filter(123)

            self.assertEqual(status, "UNKNOWN")
            self.assertEqual(result, [])
        finally:
            logging.disable(logging.NOTSET)

    def test_malformed_response_fallback(self):
        try:
            logging.disable(logging.CRITICAL)

            # Test a 200 response that is a dict
            self.responses.add(
                responses.GET,
                f"{self.base_url}?",
                body=json.dumps({"error": "oops"}),
                status=200,
            )

            status, result = request_job_filter(123)

            self.assertEqual(status, "UNKNOWN")
            self.assertEqual(result, [])

            # Test a 200 response that is null
            self.responses.add(
                responses.GET,
                f"{self.base_url}?",
                body=json.dumps(None),
                status=200,
            )

            status, result = request_job_filter(123)

            self.assertEqual(status, "UNKNOWN")
            self.assertEqual(result, [])
        finally:
            logging.disable(logging.NOTSET)

    def test_query_params(self):
        jobs = [{"id": 42}]

        ids_url = f"{self.base_url}?jobIds=10,20"
        self.responses.add(responses.GET, ids_url, body=json.dumps(jobs), status=200)
        status, result = request_job_filter(123, ids=[10, 20])
        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)

    def test_large_id_set_batches_requests(self):
        ids = list(range(JOB_FILTER_BATCH_SIZE * 2 + 1))
        chunks = [ids[i : i + JOB_FILTER_BATCH_SIZE] for i in range(0, len(ids), JOB_FILTER_BATCH_SIZE)]

        expected = []
        for chunk in chunks:
            chunk_jobs = [{"id": job_id} for job_id in chunk]
            expected.extend(chunk_jobs)
            self.responses.add(
                responses.GET,
                f"{self.base_url}?jobIds={','.join(map(str, chunk))}",
                body=json.dumps(chunk_jobs),
                status=200,
            )

        status, result = request_job_filter(123, ids=ids)

        self.assertEqual(status, "OK")
        self.assertEqual(result, expected)
        self.assertEqual(len(self.responses.calls), len(chunks))

    def test_small_id_set_single_request(self):
        jobs = [{"id": 1}, {"id": 2}]
        self.responses.add(
            responses.GET,
            f"{self.base_url}?jobIds=1,2",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(123, ids=[1, 2])

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)
        self.assertEqual(len(self.responses.calls), 1)

    def test_dict_keys_view_input(self):
        jobs = [{"id": 1}, {"id": 2}]
        self.responses.add(
            responses.GET,
            f"{self.base_url}?jobIds=1,2",
            body=json.dumps(jobs),
            status=200,
        )

        status, result = request_job_filter(123, ids={"1": "a", "2": "b"}.keys())

        self.assertEqual(status, "OK")
        self.assertEqual(result, jobs)
        self.assertEqual(len(self.responses.calls), 1)
