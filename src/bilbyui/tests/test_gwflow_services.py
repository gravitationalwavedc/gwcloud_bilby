from unittest.mock import MagicMock, patch

import elasticsearch
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.utils import timezone

from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow import (
    _collect_library_options,
    _collect_review_status_options,
    _is_fresh,
    _parse_cache_record,
    list_gwflow_filter_options,
    list_gwflow_jobs,
)
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()

LIBRARIES_CACHE_KEY = "gwflow_filter_libraries"
REVIEW_STATUSES_CACHE_KEY = "gwflow_filter_review_statuses"


def _agg_response(agg_name, keys):
    return {
        "aggregations": {
            agg_name: {
                "buckets": [{"key": key, "doc_count": 1} for key in keys],
            }
        }
    }


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
    def test_list_gwflow_jobs_private_info_query_proceeds_to_es(self, mock_es_cls):
        # The GWFlow index has no `_private_info_` field (SEC-01 closure), so the
        # query proceeds to ES rather than being short-circuited.
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}

        res = list_gwflow_jobs(self.non_ligo_user, search="_private_info_.userId:100")

        self.assertEqual(res["jobs"], {})
        mock_client.search.assert_called_once()

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

    def _filter_terms(self, mock_client):
        query = mock_client.search.call_args[1]["query"]
        filter_terms = {}
        for f in query["bool"]["filter"]:
            for _clause_type, clause in f.items():
                filter_terms.update(clause)
        return filter_terms

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
        filter_terms = self._filter_terms(mock_client)
        self.assertIn("_gwcloud.ligoOnly", filter_terms)
        self.assertIn("_gwcloud.isPruned", filter_terms)
        self.assertIn("_gwcloud.lastUpdatedTime", filter_terms)

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

        filter_terms = self._filter_terms(mock_client)
        self.assertNotIn("_gwcloud.ligoOnly", filter_terms)
        self.assertNotIn("_gwcloud.isPruned", filter_terms)

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

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_skips_non_dict_hit(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    "corrupt-non-dict-hit",
                ]
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertIn(self.job_public.id, res["jobs"])
        self.assertEqual(len(res["records"]), 1)

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_skips_dict_hit_missing_id(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    {"_source": {"job": "missing-id-hit"}},
                ]
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertIn(self.job_public.id, res["jobs"])
        self.assertEqual(len(res["records"]), 1)

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_has_next_ignores_non_numeric_trailing_id(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        job2 = GWFlowJob.objects.create(
            sname="S200101d",
            user=self.non_ligo_user,
            ligo_only=False,
            is_pruned=False,
        )
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    {"_id": job2.id},
                    {"_id": "corrupt-non-numeric-id"},
                ]
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, page_size=2)

        self.assertFalse(res["has_next"])
        self.assertEqual(len(res["records"]), 2)

    @patch("elasticsearch.Elasticsearch")
    def test_list_gwflow_jobs_returns_extra_record_for_has_next(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        job2 = GWFlowJob.objects.create(
            sname="S200101e",
            user=self.non_ligo_user,
            ligo_only=False,
            is_pruned=False,
        )
        job3 = GWFlowJob.objects.create(
            sname="S200101f",
            user=self.non_ligo_user,
            ligo_only=False,
            is_pruned=False,
        )
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    {"_id": job2.id},
                    {"_id": job3.id},
                ],
                "total": {"value": 3},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, page_size=2)

        self.assertTrue(res["has_next"])
        self.assertEqual(len(res["records"]), 3)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_has_next_follows_total_with_non_numeric_ids(self, mock_get_es_client):
        """has_next follows the exact ES total, not the numeric-only records, so
        a non-numeric ID on the page cannot hide the next page."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    {"_id": "non-numeric-id"},
                ],
                "total": {"value": 3},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, page_size=1)

        self.assertTrue(res["has_next"])
        self.assertEqual(len(res["records"]), 1)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_bad_request_error_returns_invalid(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.BadRequestError(400, "bad request", {})

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertEqual(res["state"], "invalid")
        self.assertEqual(res["jobs"], {})

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_rejects_overlong_search(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client

        res = list_gwflow_jobs(self.non_ligo_user, search="x" * 300)

        self.assertEqual(res["state"], "invalid")
        mock_client.search.assert_not_called()

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_reconciliation_with_string_ids(self, mock_get_es_client):
        """Real ES returns string _id values; reconciliation must normalise them
        to ints so valid hits are not misclassified as stale."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": str(self.job_public.id)}],  # string, as real ES returns
                "total": {"value": 1},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, page_size=20)

        self.assertIn(self.job_public.id, res["jobs"])
        self.assertEqual(len(res["jobs"]), 1)
        self.assertEqual(res["total"], 1)
        self.assertFalse(res["has_next"])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_string_ids_preserve_exact_total_and_pagination(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": str(self.job_public.id)}],
                "total": {"value": 40},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, page_size=20)

        self.assertEqual(res["total"], 40)
        self.assertTrue(res["has_next"])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_stale_only_preserves_global_total(self, mock_get_es_client):
        """Stale ES rows (no DB row) are omitted from rendering but the global
        ES total and continuation state are preserved so later pages stay
        reachable."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    {"_id": 999999},  # stale: no DB row
                ],
                "total": {"value": 2},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, page_size=20)

        self.assertIn(self.job_public.id, res["jobs"])
        self.assertEqual(len(res["jobs"]), 1)
        self.assertEqual(res["total"], 2)
        self.assertFalse(res["has_next"])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_reconciliation_preserves_authorised_rows(self, mock_get_es_client):
        """A stale/restricted hit must not blank the whole page: authorised rows
        are preserved, stale vs restricted are logged separately, and the global
        total is retained so pagination stays intact."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        pruned = GWFlowJob.objects.create(
            sname="S200101p",
            user=self.non_ligo_user,
            ligo_only=False,
            is_pruned=True,
        )
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": self.job_public.id},
                    {"_id": pruned.id},
                    {"_id": "non-numeric-id"},
                    {"_id": 999999},  # stale: no DB row
                ],
                "total": {"value": 4},
            }
        }

        with patch("bilbyui.services.gwflow.logger.warning") as mock_warn:
            res = list_gwflow_jobs(self.non_ligo_user, page_size=20)

        self.assertIn(self.job_public.id, res["jobs"])
        self.assertNotIn(pruned.id, res["jobs"])
        self.assertEqual(len(res["jobs"]), 1)
        self.assertEqual(res["total"], 4)
        self.assertFalse(res["has_next"])
        logged = " ".join(str(c.args) for c in mock_warn.call_args_list)
        self.assertIn("stale", logged)
        self.assertIn("restricted", logged)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_multi_page_drift_preserves_pagination(self, mock_get_es_client):
        """A stale hit on page 2 must not collapse pagination: the global total
        is preserved so later pages remain reachable."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        job2 = GWFlowJob.objects.create(
            sname="S200101e",
            user=self.non_ligo_user,
            ligo_only=False,
            is_pruned=False,
        )
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_id": job2.id},
                    {"_id": 999999},  # stale: no DB row
                ],
                "total": {"value": 60},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user, page=2, page_size=20)

        self.assertIn(job2.id, res["jobs"])
        self.assertEqual(len(res["jobs"]), 1)
        self.assertEqual(res["total"], 60)
        self.assertTrue(res["has_next"])  # 20 + 20 < 60 -> page 3 reachable

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_advanced_syntax_at_256_char_limit_accepted(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        search = "sname:" + "a" * 250  # 256 chars total
        res = list_gwflow_jobs(self.non_ligo_user, search=search)

        self.assertEqual(res["state"], "ok")
        mock_client.search.assert_called_once()

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_maps_library_and_review_status(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": self.job_public.id}],
                "total": {"value": 1},
            }
        }

        res = list_gwflow_jobs(
            self.non_ligo_user,
            search="GW150914",
            library='cbc-workflow "o4a"',
            review_status="approved",
        )

        filter_terms = self._filter_terms(mock_client)
        self.assertEqual(filter_terms["_gwcloud.libraries"], 'cbc-workflow "o4a"')
        self.assertEqual(filter_terms["_gwcloud.reviewStatuses"], "approved")
        self.assertIn("_gwcloud.ligoOnly", filter_terms)
        self.assertIn("_gwcloud.isPruned", filter_terms)
        self.assertIn(self.job_public.id, res["jobs"])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_maps_review_status_with_special_chars(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": self.job_public.id}],
                "total": {"value": 1},
            }
        }

        list_gwflow_jobs(self.non_ligo_user, review_status="a:b*c")

        filter_terms = self._filter_terms(mock_client)
        self.assertEqual(filter_terms["_gwcloud.reviewStatuses"], "a:b*c")

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_groups_free_form_query_before_structured_filters(self, mock_get_es_client):
        """An OR expression must not leave a branch unconstrained by the
        Library/Review filters (query-policy bypass)."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        list_gwflow_jobs(
            self.non_ligo_user,
            search="sname:S1 OR sname:S2",
            library="lib-a",
            review_status="reviewed",
        )

        query = mock_client.search.call_args[1]["query"]
        self.assertEqual(query["bool"]["must"][0]["query_string"]["query"], "sname:S1 OR sname:S2")
        filter_terms = self._filter_terms(mock_client)
        self.assertEqual(filter_terms["_gwcloud.libraries"], "lib-a")
        self.assertEqual(filter_terms["_gwcloud.reviewStatuses"], "reviewed")

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_structured_filters_never_reach_query_string(self, mock_get_es_client):
        """Lucene operators in library/review values must stay in term filters,
        never in the query_string must clause (ES query-string injection)."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        list_gwflow_jobs(
            self.non_ligo_user,
            search="sname:S1",
            library='x" OR ligoOnly:true OR libraries:"y',
            review_status="a && b || !c",
        )

        query = mock_client.search.call_args[1]["query"]
        self.assertEqual(query["bool"]["must"][0]["query_string"]["query"], "sname:S1")
        filter_terms = self._filter_terms(mock_client)
        self.assertEqual(filter_terms["_gwcloud.libraries"], 'x" OR ligoOnly:true OR libraries:"y')
        self.assertEqual(filter_terms["_gwcloud.reviewStatuses"], "a && b || !c")

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_passes_advanced_syntax_through_unchanged(self, mock_get_es_client):
        """AC7: advanced query syntax is preserved verbatim (wrapped, not
        rewritten), so structured filters do not change its semantics."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        advanced = "sname:S2306* AND (analyses.software:bilby OR analyses.software:pycbc)"
        list_gwflow_jobs(self.non_ligo_user, search=advanced)

        query = mock_client.search.call_args[1]["query"]
        self.assertEqual(query["bool"]["must"][0]["query_string"]["query"], advanced)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_advanced_syntax_corpus_parity(self, mock_get_es_client):
        """AC7: a corpus of advanced queries produces the same ES query-string
        construction as the pre-change path (wrapped, never rewritten)."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        corpus = [
            "sname:S2306*",
            "analyses.software:bilby AND analyses.waveform:IMRPhenomXPHM",
            "libraries:cbc-workflow-o4c AND analyses.reviewStatus:reviewed",
            "gracedb.instruments:H1 OR gracedb.instruments:L1",
            "eventId.triggerId:S230601ag",
        ]
        for advanced in corpus:
            with self.subTest(advanced=advanced):
                list_gwflow_jobs(self.non_ligo_user, search=advanced)
                query = mock_client.search.call_args[1]["query"]
                self.assertEqual(query["bool"]["must"][0]["query_string"]["query"], advanced)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_preserves_total_on_empty_page(self, mock_get_es_client):
        """An out-of-range page with a positive ES total must not hide the total."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [], "total": {"value": 57}}}

        res = list_gwflow_jobs(self.non_ligo_user, page=99)

        self.assertEqual(res["total"], 57)
        self.assertEqual(res["jobs"], {})
        self.assertFalse(res["has_next"])

    def test_extract_es_total_legacy_integer_shape(self):
        from bilbyui.services.jobs import _extract_es_total

        self.assertEqual(_extract_es_total({"hits": {"total": 42}}), 42)
        self.assertEqual(_extract_es_total({"hits": {"total": {"value": 42}}}), 42)
        self.assertEqual(_extract_es_total({"hits": {"total": "42"}}), 42)
        self.assertEqual(_extract_es_total({"hits": {}}), 0)

    def test_extract_es_total_preserves_lower_bound(self):
        from bilbyui.services.jobs import _extract_es_total

        # A capped total (relation "gte") keeps its known value: a positive
        # lower bound must never be converted into a false exact zero.
        self.assertEqual(_extract_es_total({"hits": {"total": {"value": 10000, "relation": "gte"}}}), 10000)
        # Explicit "eq" relation is exact.
        self.assertEqual(_extract_es_total({"hits": {"total": {"value": 10000, "relation": "eq"}}}), 10000)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_requests_exact_total(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        list_gwflow_jobs(self.non_ligo_user)

        self.assertTrue(mock_client.search.call_args[1].get("track_total_hits"))

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_returns_total(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": self.job_public.id}],
                "total": {"value": 42},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertEqual(res["total"], 42)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_total_guards_string_value(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": self.job_public.id}],
                "total": {"value": "42"},
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertEqual(res["total"], 42)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_total_missing_returns_zero(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": self.job_public.id}],
            }
        }

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertEqual(res["total"], 0)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_unfielded_search_relies_on_bounded_default_field(self, mock_get_es_client):
        """An unfielded search must not set default_field to metadata.*: it
        relies on index.query.default_field (the bounded _gwcloud.* set)."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        list_gwflow_jobs(self.non_ligo_user, search="GW150914")

        query = mock_client.search.call_args[1]["query"]
        qs = query["bool"]["must"][0]["query_string"]
        self.assertNotIn("default_field", qs)
        self.assertEqual(qs["query"], "GW150914")

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_fielded_expert_query_to_metadata_still_works(self, mock_get_es_client):
        """Fielded expert queries to arbitrary known metadata.* paths remain
        available and are passed through unchanged."""
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        expert = "metadata.ParameterEstimation.results.inference_software:bilby"
        list_gwflow_jobs(self.non_ligo_user, search=expert)

        query = mock_client.search.call_args[1]["query"]
        qs = query["bool"]["must"][0]["query_string"]
        self.assertEqual(qs["query"], expert)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_sort_uses_gwcloud_last_updated_desc_missing_last(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        list_gwflow_jobs(self.non_ligo_user)

        sort = mock_client.search.call_args[1]["sort"]
        self.assertEqual(
            sort,
            [{"_gwcloud.lastUpdatedTime": {"order": "desc", "missing": "_last"}}],
        )

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_all_filters_target_gwcloud_fields(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        list_gwflow_jobs(
            self.non_ligo_user,
            search="sname:S1",
            library="lib-a",
            review_status="approved",
            time_range="1w",
        )

        filter_terms = self._filter_terms(mock_client)
        self.assertEqual(filter_terms["_gwcloud.libraries"], "lib-a")
        self.assertEqual(filter_terms["_gwcloud.reviewStatuses"], "approved")
        self.assertIn("_gwcloud.lastUpdatedTime", filter_terms)
        self.assertEqual(filter_terms["_gwcloud.ligoOnly"], False)
        self.assertEqual(filter_terms["_gwcloud.isPruned"], False)
        self.assertNotIn("libraries.keyword", filter_terms)
        self.assertNotIn("analyses.reviewStatus.keyword", filter_terms)
        self.assertNotIn("lastUpdatedTime", filter_terms)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_request_timeout(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"hits": {"hits": [{"_id": self.job_public.id}], "total": {"value": 1}}}

        list_gwflow_jobs(self.non_ligo_user)

        self.assertEqual(mock_client.search.call_args[1]["request_timeout"], 10)


class TestGWFlowFilterOptions(BilbyTestCase):
    def setUp(self):
        super().setUp()
        caches["default"].clear()
        self.user = self.create_user(id=200, name="Filter User", primary_email="filter@example.com")

    def _mock_es(self, libraries=None, review_statuses=None, side_effect=None):
        mock_client = MagicMock()
        if side_effect is not None:
            mock_client.search.side_effect = side_effect
        else:
            responses = {}
            if libraries is not None:
                responses["libraries"] = _agg_response("libraries", libraries)
            if review_statuses is not None:
                responses["review_statuses"] = _agg_response("review_statuses", review_statuses)
            mock_client.search.side_effect = lambda **kw: responses.get(
                list(kw.get("aggs", {}).keys())[0], {"aggregations": {}}
            )
        return mock_client

    def _agg_call(self, mock_client, agg_name):
        for call in mock_client.search.call_args_list:
            aggs = call.kwargs.get("aggs", {})
            if agg_name in aggs:
                return call
        return None

    def test_libraries_from_es_aggregation(self):
        mock_client = self._mock_es(libraries=["b-library", "a-library"])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["b-library", "a-library"], "state": "ok"})
        record = caches["default"].get(LIBRARIES_CACHE_KEY)
        self.assertEqual(record["values"], ["b-library", "a-library"])
        self.assertIn("fetched_at", record)

        call = self._agg_call(mock_client, "libraries")
        self.assertEqual(call.kwargs["aggs"]["libraries"]["terms"]["field"], "_gwcloud.libraries")
        self.assertEqual(call.kwargs["size"], 0)
        filters = call.kwargs["query"]["bool"]["filter"]
        self.assertIn({"term": {"_gwcloud.isPruned": False}}, filters)
        self.assertIn({"term": {"_gwcloud.ligoOnly": False}}, filters)

    def test_libraries_cached_fresh(self):
        mock_client = self._mock_es(libraries=["a-library"])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            list_gwflow_filter_options()
            mock_client.search.reset_mock()
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["a-library"], "state": "ok"})
        mock_client.search.assert_not_called()

    def test_review_statuses_from_es_aggregation(self):
        mock_client = self._mock_es(review_statuses=["approved", "pending"])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            options = list_gwflow_filter_options()

        self.assertEqual(
            options["review_statuses"],
            {"values": ["approved", "pending"], "state": "ok"},
        )
        record = caches["default"].get(REVIEW_STATUSES_CACHE_KEY)
        self.assertEqual(record["values"], ["approved", "pending"])

        call = self._agg_call(mock_client, "review_statuses")
        self.assertEqual(call.kwargs["aggs"]["review_statuses"]["terms"]["field"], "_gwcloud.reviewStatuses")
        self.assertEqual(call.kwargs["aggs"]["review_statuses"]["terms"]["size"], 50)
        self.assertEqual(call.kwargs["size"], 0)
        filters = call.kwargs["query"]["bool"]["filter"]
        self.assertIn({"term": {"_gwcloud.isPruned": False}}, filters)
        self.assertIn({"term": {"_gwcloud.ligoOnly": False}}, filters)

    def test_review_statuses_cached_fresh(self):
        mock_client = self._mock_es(review_statuses=["approved"])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            list_gwflow_filter_options()
            mock_client.search.reset_mock()
            options = list_gwflow_filter_options()

        self.assertEqual(options["review_statuses"], {"values": ["approved"], "state": "ok"})
        mock_client.search.assert_not_called()

    def test_successful_empty_is_ok_and_stored(self):
        mock_client = self._mock_es(libraries=[], review_statuses=[])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": [], "state": "ok"})
        self.assertEqual(options["review_statuses"], {"values": [], "state": "ok"})
        self.assertEqual(caches["default"].get(LIBRARIES_CACHE_KEY)["values"], [])
        self.assertEqual(caches["default"].get(REVIEW_STATUSES_CACHE_KEY)["values"], [])

    def test_failure_without_cache_is_unavailable(self):
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": [], "state": "unavailable"})
        self.assertEqual(options["review_statuses"], {"values": [], "state": "unavailable"})
        self.assertIsNone(caches["default"].get(LIBRARIES_CACHE_KEY))
        self.assertIsNone(caches["default"].get(REVIEW_STATUSES_CACHE_KEY))

    def test_failure_with_stale_cache_is_stale(self):
        caches["default"].set(
            LIBRARIES_CACHE_KEY,
            {"values": ["stale-lib"], "fetched_at": timezone.now() - __import__("datetime").timedelta(hours=2)},
        )
        caches["default"].set(
            REVIEW_STATUSES_CACHE_KEY,
            {
                "values": ["stale-status"],
                "fetched_at": timezone.now() - __import__("datetime").timedelta(hours=2),
            },
        )
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["stale-lib"], "state": "stale"})
        self.assertEqual(options["review_statuses"], {"values": ["stale-status"], "state": "stale"})

    def test_mixed_per_facet_outcomes(self):
        # Libraries: no cache + ES failure -> unavailable
        # Review statuses: stale cache + ES failure -> stale
        caches["default"].set(
            REVIEW_STATUSES_CACHE_KEY,
            {
                "values": ["stale-status"],
                "fetched_at": timezone.now() - __import__("datetime").timedelta(hours=3),
            },
        )
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": [], "state": "unavailable"})
        self.assertEqual(options["review_statuses"], {"values": ["stale-status"], "state": "stale"})

    def test_fresh_hit_ok(self):
        caches["default"].set(
            LIBRARIES_CACHE_KEY,
            {"values": ["fresh-lib"], "fetched_at": timezone.now()},
        )
        caches["default"].set(
            REVIEW_STATUSES_CACHE_KEY,
            {"values": ["fresh-status"], "fetched_at": timezone.now()},
        )
        with patch("bilbyui.services.gwflow.get_es_client") as mock_get_es_client:
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["fresh-lib"], "state": "ok"})
        self.assertEqual(options["review_statuses"], {"values": ["fresh-status"], "state": "ok"})
        mock_get_es_client.assert_not_called()

    def test_stale_hit_returns_stale_on_failure(self):
        caches["default"].set(
            LIBRARIES_CACHE_KEY,
            {"values": ["old-lib"], "fetched_at": timezone.now() - __import__("datetime").timedelta(hours=5)},
        )
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["old-lib"], "state": "stale"})

    def test_total_miss_unavailable(self):
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": [], "state": "unavailable"})

    def test_invalidation_of_both_keys_refetches(self):
        mock_client = self._mock_es(libraries=["a"], review_statuses=["b"])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            list_gwflow_filter_options()
            caches["default"].delete(LIBRARIES_CACHE_KEY)
            caches["default"].delete(REVIEW_STATUSES_CACHE_KEY)
            mock_client.search.reset_mock()
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["a"], "state": "ok"})
        self.assertEqual(options["review_statuses"], {"values": ["b"], "state": "ok"})
        self.assertEqual(mock_client.search.call_count, 2)

    def test_legacy_plain_list_cache_refreshes_through_collector(self):
        # Old format: a plain list of values with no {values, fetched_at}
        # record. It carries no trustworthy timestamp, so it must NOT be
        # returned as a fresh ok result; instead it refreshes through the
        # normal collector and the cache is rewritten to the new format.
        caches["default"].set(LIBRARIES_CACHE_KEY, ["legacy-lib-a", "legacy-lib-b"])
        mock_client = self._mock_es(libraries=["fresh-lib"])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["fresh-lib"], "state": "ok"})
        record = caches["default"].get(LIBRARIES_CACHE_KEY)
        self.assertEqual(record["values"], ["fresh-lib"])
        self.assertIn("fetched_at", record)
        self.assertEqual(self._agg_call(mock_client, "libraries") is not None, True)

    def test_legacy_plain_list_cache_unavailable_on_collector_failure(self):
        # A legacy plain-list record is treated as absent: on collector
        # failure it yields unavailable, never stale (no trustworthy data).
        caches["default"].set(LIBRARIES_CACHE_KEY, ["legacy-lib-a", "legacy-lib-b"])
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": [], "state": "unavailable"})

    def test_malformed_cache_record_treated_as_absent(self):
        # A dict without "values" and a non-list non-dict record are both
        # malformed and must be treated as absent (refresh through collector).
        caches["default"].set(LIBRARIES_CACHE_KEY, {"fetched_at": timezone.now()})
        caches["default"].set(REVIEW_STATUSES_CACHE_KEY, "not-a-record")
        mock_client = self._mock_es(libraries=["fresh-lib"], review_statuses=["fresh-status"])
        with patch("bilbyui.services.gwflow.get_es_client", return_value=mock_client):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["fresh-lib"], "state": "ok"})
        self.assertEqual(options["review_statuses"], {"values": ["fresh-status"], "state": "ok"})

    def test_malformed_cache_record_unavailable_on_collector_failure(self):
        # Malformed records are absent, so a collector failure yields
        # unavailable (not stale) for both facets.
        caches["default"].set(LIBRARIES_CACHE_KEY, {"fetched_at": timezone.now()})
        caches["default"].set(REVIEW_STATUSES_CACHE_KEY, "not-a-record")
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": [], "state": "unavailable"})
        self.assertEqual(options["review_statuses"], {"values": [], "state": "unavailable"})

    def test_valid_fresh_record_ok_without_recollect(self):
        # Guard against over-correcting: a valid {values, fetched_at} record
        # with a fresh timestamp must be returned as ok without re-collecting.
        caches["default"].set(
            LIBRARIES_CACHE_KEY,
            {"values": ["fresh-lib"], "fetched_at": timezone.now()},
        )
        caches["default"].set(
            REVIEW_STATUSES_CACHE_KEY,
            {"values": ["fresh-status"], "fetched_at": timezone.now()},
        )
        with patch("bilbyui.services.gwflow.get_es_client") as mock_get_es_client:
            options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], {"values": ["fresh-lib"], "state": "ok"})
        self.assertEqual(options["review_statuses"], {"values": ["fresh-status"], "state": "ok"})
        mock_get_es_client.assert_not_called()

    def test_failure_and_unavailable_never_written_to_cache(self):
        with patch(
            "bilbyui.services.gwflow.get_es_client",
            side_effect=elasticsearch.exceptions.ConnectionError("down"),
        ):
            list_gwflow_filter_options()

        self.assertIsNone(caches["default"].get(LIBRARIES_CACHE_KEY))
        self.assertIsNone(caches["default"].get(REVIEW_STATUSES_CACHE_KEY))


class TestCollectOptions(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=300, name="Collect User", primary_email="collect@example.com")

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_collect_library_options_uses_gwcloud_field_and_visibility(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = _agg_response("libraries", ["a-lib", "b-lib"])

        result = _collect_library_options()

        self.assertEqual(result, ["a-lib", "b-lib"])
        call = mock_client.search.call_args
        self.assertEqual(call.kwargs["aggs"]["libraries"]["terms"]["field"], "_gwcloud.libraries")
        filters = call.kwargs["query"]["bool"]["filter"]
        self.assertIn({"term": {"_gwcloud.isPruned": False}}, filters)
        self.assertIn({"term": {"_gwcloud.ligoOnly": False}}, filters)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_collect_review_status_options_uses_gwcloud_field_and_visibility(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = _agg_response("review_statuses", ["approved"])

        result = _collect_review_status_options()

        self.assertEqual(result, ["approved"])
        call = mock_client.search.call_args
        self.assertEqual(call.kwargs["aggs"]["review_statuses"]["terms"]["field"], "_gwcloud.reviewStatuses")
        self.assertEqual(call.kwargs["aggs"]["review_statuses"]["terms"]["size"], 50)
        filters = call.kwargs["query"]["bool"]["filter"]
        self.assertIn({"term": {"_gwcloud.isPruned": False}}, filters)
        self.assertIn({"term": {"_gwcloud.ligoOnly": False}}, filters)

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_collect_review_status_options_empty_buckets_returns_empty_list(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = _agg_response("review_statuses", [])

        self.assertEqual(_collect_review_status_options(), [])


class TestParseCacheRecord(BilbyTestCase):
    def test_none_record_returns_none_none(self):
        self.assertEqual(_parse_cache_record(None), (None, None))

    def test_non_dict_record_returns_none_none(self):
        self.assertEqual(_parse_cache_record("not-a-record"), (None, None))
        self.assertEqual(_parse_cache_record(["legacy-list"]), (None, None))

    def test_dict_missing_values_returns_none_none(self):
        self.assertEqual(_parse_cache_record({"fetched_at": timezone.now()}), (None, None))

    def test_valid_record_returns_values_and_fetched_at(self):
        fetched_at = timezone.now()
        self.assertEqual(
            _parse_cache_record({"values": ["a"], "fetched_at": fetched_at}),
            (["a"], fetched_at),
        )


class TestIsFresh(BilbyTestCase):
    def test_non_datetime_is_not_fresh(self):
        self.assertFalse(_is_fresh("not-a-datetime"))
        self.assertFalse(_is_fresh(None))

    def test_naive_datetime_now_is_fresh(self):
        self.assertTrue(_is_fresh(timezone.now().replace(tzinfo=None)))

    def test_fresh_aware_datetime_is_fresh(self):
        self.assertTrue(_is_fresh(timezone.now()))

    def test_stale_datetime_is_not_fresh(self):
        stale = timezone.now() - __import__("datetime").timedelta(hours=2)
        self.assertFalse(_is_fresh(stale))


class TestCollectReviewStatusOptions(BilbyTestCase):
    @patch("bilbyui.services.gwflow.get_es_client")
    def test_raises_on_es_connection_error(self, mock_get_es_client):
        mock_get_es_client.side_effect = elasticsearch.exceptions.ConnectionError("down")

        with self.assertRaises(elasticsearch.exceptions.ConnectionError):
            _collect_review_status_options()

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_raises_on_search_error(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.NotFoundError(404, "index not found", {})

        with self.assertRaises(elasticsearch.exceptions.NotFoundError):
            _collect_review_status_options()

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_returns_empty_list_on_empty_buckets(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"aggregations": {"review_statuses": {"buckets": []}}}

        self.assertEqual(_collect_review_status_options(), [])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_returns_valid_buckets(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "aggregations": {
                "review_statuses": {
                    "buckets": [
                        {"key": "approved", "doc_count": 10},
                        {"key": "pending", "doc_count": 5},
                    ]
                }
            }
        }

        self.assertEqual(_collect_review_status_options(), ["approved", "pending"])
