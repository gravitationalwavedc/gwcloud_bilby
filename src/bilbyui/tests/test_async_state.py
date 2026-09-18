from unittest.mock import MagicMock, patch

import elasticsearch
from django.template.loader import get_template

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.services.gwflow import list_gwflow_jobs
from bilbyui.services.jobs import list_public_jobs, list_user_jobs
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


def render_state(**kwargs):
    """Render the _async_state.html partial with the given context."""
    return get_template("bilbyui/_async_state.html").render(kwargs)


class TestListGWFlowJobsStateFlag(BilbyTestCase):
    """Service contract: list_gwflow_jobs returns state='ok'|'down'."""

    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=100, name="GWFlow User", primary_email="gwflow@example.com")
        self.job = GWFlowJob.objects.create(
            sname="S200101a",
            user=self.user,
            ligo_only=False,
            is_pruned=False,
        )

    def _mock_search(self, mock_es_cls, hits):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": hits}}
        return mock_client

    @patch("elasticsearch.Elasticsearch")
    def test_success_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [{"_id": self.job.id}])
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertIn(self.job.id, res["jobs"])

    @patch("elasticsearch.Elasticsearch")
    def test_no_hits_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [])
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_private_info_search_proceeds_to_es(self, mock_es_cls):
        # The GWFlow index has no `_private_info_` field (SEC-01 closure), so the
        # query proceeds to ES; the unknown field simply matches nothing.
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}

        res = list_gwflow_jobs(self.user, search="_private_info_.userId:100")

        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})
        mock_client.search.assert_called_once()

    @patch("elasticsearch.Elasticsearch")
    def test_reconciliation_mismatch_returns_state_ok(self, mock_es_cls):
        ligo_job = GWFlowJob.objects.create(
            sname="S200101b",
            user=self.user,
            ligo_only=True,
            is_pruned=False,
        )
        self._mock_search(mock_es_cls, [{"_id": ligo_job.id}])
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_client_returns_state_down(self, mock_es_cls):
        mock_es_cls.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_search_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_not_found_error_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.NotFoundError(404, "index not found", {})
        res = list_gwflow_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})


class TestListPublicJobsStateFlag(BilbyTestCase):
    """Service contract: list_public_jobs returns state='ok'|'down'."""

    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=200, name="Public User", primary_email="public@example.com")
        self.job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Public job",
            description="public",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Public job"}),
        )

    def _mock_search(self, mock_es_cls, hits):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": hits}}
        return mock_client

    @patch("elasticsearch.Elasticsearch")
    def test_success_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [{"_id": self.job.id, "_source": {}}])
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertIn(self.job.id, res["jobs"])

    @patch("elasticsearch.Elasticsearch")
    def test_no_hits_returns_state_ok(self, mock_es_cls):
        self._mock_search(mock_es_cls, [])
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_private_info_search_returns_state_ok(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        res = list_public_jobs(self.user, search="_private_info_.userId:200")
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})
        mock_client.search.assert_not_called()

    @patch("elasticsearch.Elasticsearch")
    def test_reconciliation_mismatch_returns_state_ok(self, mock_es_cls):
        private_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Private job",
            description="private",
            private=True,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Private job"}),
        )
        self._mock_search(mock_es_cls, [{"_id": private_job.id, "_source": {}}])
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_client_returns_state_down(self, mock_es_cls):
        mock_es_cls.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_connection_error_on_search_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.ConnectionError("Connection refused")
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("elasticsearch.Elasticsearch")
    def test_not_found_error_returns_state_down(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.NotFoundError(404, "index not found", {})
        res = list_public_jobs(self.user)
        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})


class TestListUserJobsStateFlag(BilbyTestCase):
    """Service contract: list_user_jobs is DB-backed and always state='ok'."""

    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=300, name="My Jobs User", primary_email="myjobs@example.com")

    def test_success_returns_state_ok(self):
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="My job",
            description="mine",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "My job"}),
        )
        res = list_user_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(len(res["jobs"]), 1)

    def test_empty_returns_state_ok(self):
        res = list_user_jobs(self.user)
        self.assertEqual(res["state"], "ok")
        self.assertEqual(res["jobs"], [])


# ============================================================================
# task-5: view failure-branch tests (issue #50)
# ============================================================================
