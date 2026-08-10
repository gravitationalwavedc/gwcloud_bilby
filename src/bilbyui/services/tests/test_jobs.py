from datetime import timedelta
from unittest.mock import patch

import elasticsearch
from django.utils import timezone

from bilbyui.models import BilbyJob
from bilbyui.services.jobs import (
    _apply_search_filter,
    _apply_time_range_filter,
    get_job,
    list_public_jobs,
    list_user_jobs,
    update_job,
)
from bilbyui.tests.test_utils import create_test_ini_string, generate_elastic_doc
from bilbyui.tests.testcases import BilbyTestCase


class TestJobsService(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.other_user = cls.create_user(id=2, name="other user", primary_email="other@gmail.com")
        cls.job1 = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="first_job",
            description="First job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.job2 = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="second_job",
            description="Second job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.other_user_job = BilbyJob.objects.create(
            user_id=cls.other_user.id,
            name="other_job",
            description="Other user job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def setUp(self):
        self.authenticate()

    def test_list_user_jobs_returns_expected_jobs(self):
        result = list_user_jobs(self.user)
        job_ids = [job.id for job in result["jobs"]]
        self.assertEqual(job_ids, [self.job2.id, self.job1.id])
        self.assertFalse(result["has_next"])
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["page_size"], 20)

    def test_list_user_jobs_pagination_page_two(self):
        result = list_user_jobs(self.user, page=2, page_size=1)
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0].id, self.job1.id)
        self.assertFalse(result["has_next"])
        self.assertEqual(result["page"], 2)

    def test_list_user_jobs_search_filters_by_name_or_description(self):
        by_name = list_user_jobs(self.user, search="first")
        self.assertEqual([job.id for job in by_name["jobs"]], [self.job1.id])

        by_description = list_user_jobs(self.user, search="Second job")
        self.assertEqual([job.id for job in by_description["jobs"]], [self.job2.id])

    def test_list_user_jobs_time_range_excludes_old_jobs(self):
        BilbyJob.objects.filter(pk=self.job1.pk).update(
            last_updated=timezone.now() - timedelta(days=2),
        )
        result = list_user_jobs(self.user, time_range="1d")
        self.assertEqual([job.id for job in result["jobs"]], [self.job2.id])

    def test_apply_search_filter(self):
        qs = BilbyJob.objects.filter(user_id=1)
        self.assertEqual(_apply_search_filter(qs, "").count(), 2)
        self.assertEqual(_apply_search_filter(qs, "first").count(), 1)
        self.assertEqual(_apply_search_filter(qs, "Second job").count(), 1)

    def test_apply_time_range_filter(self):
        now = timezone.now()
        qs = BilbyJob.objects.filter(user_id=1)
        self.assertEqual(_apply_time_range_filter(qs, "all").count(), 2)

        BilbyJob.objects.filter(pk=self.job1.pk).update(last_updated=now - timedelta(days=2))
        self.assertEqual(_apply_time_range_filter(qs, "1d").count(), 1)

        BilbyJob.objects.filter(pk=self.job2.pk).update(last_updated=now - timedelta(days=8))
        self.assertEqual(_apply_time_range_filter(qs, "1w").count(), 1)

        BilbyJob.objects.filter(pk=self.job1.pk).update(last_updated=now - timedelta(days=20))
        BilbyJob.objects.filter(pk=self.job2.pk).update(last_updated=now - timedelta(days=40))
        self.assertEqual(_apply_time_range_filter(qs, "1m").count(), 1)

        BilbyJob.objects.filter(pk=self.job1.pk).update(last_updated=now - timedelta(days=400))
        self.assertEqual(_apply_time_range_filter(qs, "1y").count(), 1)

    def test_apply_time_range_filter_invalid_raises(self):
        with self.assertRaises(Exception) as ctx:
            _apply_time_range_filter(BilbyJob.objects.all(), "bogus")
        self.assertIn("Unexpected timeRange", str(ctx.exception))

    def test_update_job_with_name(self):
        success, message = update_job(self.job1.id, self.user, name="renamed_job")
        self.assertTrue(success)
        self.assertEqual(message, "Job saved!")
        self.job1.refresh_from_db()
        self.assertEqual(self.job1.name, "renamed_job")

    def test_get_job_raises_for_unknown_id(self):
        with self.assertRaises(BilbyJob.DoesNotExist):
            get_job(99999, self.user)

    @patch("bilbyui.services.jobs.elasticsearch.Elasticsearch")
    def test_list_public_jobs_elasticsearch_connection_failure(self, mock_elasticsearch):
        mock_elasticsearch.side_effect = elasticsearch.exceptions.ConnectionError("connection failed")
        result = list_public_jobs(self.user)
        self.assertEqual(
            result,
            {
                "jobs": {},
                "records": [],
                "job_controller_jobs": {},
                "has_next": False,
                "page": 1,
                "page_size": 20,
            },
        )
        mock_elasticsearch.assert_called_once()

    @patch("bilbyui.services.jobs.elasticsearch.Elasticsearch")
    def test_list_public_jobs_elasticsearch_missing_index(self, mock_elasticsearch):
        mock_es = mock_elasticsearch.return_value
        mock_es.search.side_effect = elasticsearch.NotFoundError("Exists", None, None)
        result = list_public_jobs(self.user)
        self.assertEqual(
            result,
            {
                "jobs": {},
                "records": [],
                "job_controller_jobs": {},
                "has_next": False,
                "page": 1,
                "page_size": 20,
            },
        )
        mock_es.search.assert_called_once()

    @patch("bilbyui.services.jobs.elasticsearch.Elasticsearch")
    def test_list_public_jobs_elasticsearch_search_connection_error(self, mock_elasticsearch):
        mock_es = mock_elasticsearch.return_value
        mock_es.search.side_effect = elasticsearch.exceptions.ConnectionError("connection failed")
        result = list_public_jobs(self.user)
        self.assertEqual(
            result,
            {
                "jobs": {},
                "records": [],
                "job_controller_jobs": {},
                "has_next": False,
                "page": 1,
                "page_size": 20,
            },
        )
        mock_es.search.assert_called_once()

    @patch("bilbyui.services.jobs.elasticsearch.Elasticsearch")
    def test_list_public_jobs_empty_hits_returns_empty_result(self, mock_elasticsearch):
        mock_es = mock_elasticsearch.return_value
        mock_es.search.return_value = {"hits": {"total": 0, "hits": []}}
        result = list_public_jobs(self.user)
        self.assertEqual(
            result,
            {
                "jobs": {},
                "records": [],
                "job_controller_jobs": {},
                "has_next": False,
                "page": 1,
                "page_size": 20,
            },
        )
        mock_es.search.assert_called_once()

    @patch("bilbyui.services.jobs.request_job_filter")
    @patch("bilbyui.services.jobs.elasticsearch.Elasticsearch")
    def test_list_public_jobs_skips_unexpected_controller_job_id(self, mock_elasticsearch, mock_request_job_filter):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="public_job",
            description="Public job",
            private=False,
            job_controller_id=42,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        mock_es = mock_elasticsearch.return_value
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": generate_elastic_doc(job, {"name": self.user.name, "id": self.user.id}),
                        "_id": job.id,
                    }
                ]
            }
        }
        mock_request_job_filter.return_value = (
            "OK",
            [
                {"id": 42, "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}]},
                {"id": 999, "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}]},
            ],
        )

        result = list_public_jobs(self.user)

        self.assertEqual(list(result["job_controller_jobs"].keys()), [job.id])
        self.assertEqual(result["job_controller_jobs"][job.id]["id"], 42)

    @patch("bilbyui.services.jobs.elasticsearch.Elasticsearch")
    def test_list_public_jobs_has_next_ignores_non_numeric_trailing_id(self, mock_elasticsearch):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="public_job",
            description="Public job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        mock_es = mock_elasticsearch.return_value
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job1.id},
                    {"_id": job.id},
                    {"_id": "corrupt-non-numeric-id"},
                ]
            }
        }

        result = list_public_jobs(self.user, page_size=2)

        self.assertFalse(result["has_next"])
        self.assertEqual(len(result["records"]), 2)
