from unittest.mock import MagicMock, patch

import elasticsearch
from django.contrib.auth import get_user_model

from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow import list_gwflow_jobs
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestGWFlowServices(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.ligo_user = self.create_user(
            id=100,
            name="LIGO User",
            primary_email="ligo@example.com",
            authentication_method="ligo_shibboleth",
        )
        self.non_ligo_user = self.create_user(
            id=101,
            name="Public User",
            primary_email="public@example.com",
            authentication_method="password",
        )

        self.job_public = GWFlowJob.objects.create(
            sname="S200101a",
            user=self.non_ligo_user,
            ligo_only=False,
            is_pruned=False,
        )
        self.job_ligo = GWFlowJob.objects.create(
            sname="S200101b",
            user=self.ligo_user,
            ligo_only=True,
            is_pruned=False,
        )
        self.job_pruned = GWFlowJob.objects.create(
            sname="S200101c",
            user=self.ligo_user,
            ligo_only=False,
            is_pruned=True,
        )

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_connection_error(self, mock_es_cls):
        mock_es_cls.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_gwflow_jobs(self.non_ligo_user)
        self.assertEqual(res["jobs"], {})
        self.assertFalse(res["has_next"])

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_private_info_query(self, mock_es_cls):
        res = list_gwflow_jobs(self.non_ligo_user, search="_private_info_.userId:100")
        self.assertEqual(res["jobs"], {})
        mock_es_cls.assert_not_called()

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_index_not_found(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.NotFoundError(404, "index not found", {})

        res = list_gwflow_jobs(self.non_ligo_user)
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_search_connection_error(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")

        res = list_gwflow_jobs(self.non_ligo_user)
        self.assertEqual(res["jobs"], {})
        self.assertFalse(res["has_next"])
        mock_client.search.assert_called_once()

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_non_ligo_user_query(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                ]
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, search="GW150914", time_range="1d")

        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args[1]
        q = call_kwargs["q"]
        self.assertIn("ligoOnly:false", q)
        self.assertIn("isPruned:false", q)
        self.assertIn("lastUpdatedTime:", q)

        self.assertIn(self.job_public.id, res["jobs"])

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_ligo_user_query(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_ligo.id},
                ]
            }
        }

        res = list_gwflow_jobs(self.ligo_user, include_pruned=True)

        call_kwargs = mock_client.search.call_args[1]
        q = call_kwargs["q"]
        self.assertNotIn("ligoOnly:false", q)
        self.assertNotIn("isPruned:false", q)

        self.assertIn(self.job_ligo.id, res["jobs"])

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_reconciliation_mismatch_bails(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        # Mock ES returning a ligo_only job hit for a non-LIGO user
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_ligo.id},
                ]
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user)
        # Reconciliation will see count mismatch (1 returned from ES vs 0 passing DB filter for non_ligo)
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_skips_malformed_non_numeric_id(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    {"_id": "corrupt-non-numeric-id"},
                ]
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertIn(self.job_public.id, res["jobs"])
        self.assertEqual(len(res["records"]), 1)
