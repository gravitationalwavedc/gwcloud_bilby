from unittest.mock import MagicMock, patch

import elasticsearch
from django.contrib.auth import get_user_model
from django.core.cache import caches

from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow import list_gwflow_filter_options, list_gwflow_jobs
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
        query = mock_client.search.call_args[1]["query"]
        filter_terms = {}
        for f in query["bool"]["filter"]:
            for _clause_type, clause in f.items():
                filter_terms.update(clause)
        self.assertIn("ligoOnly", filter_terms)
        self.assertIn("isPruned", filter_terms)
        self.assertIn("lastUpdatedTime", filter_terms)

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

        query = mock_client.search.call_args[1]["query"]
        filter_terms = {}
        for f in query["bool"]["filter"]:
            for _clause_type, clause in f.items():
                filter_terms.update(clause)
        self.assertNotIn("ligoOnly", filter_terms)
        self.assertNotIn("isPruned", filter_terms)

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
    def test_list_gwflow_jobs_bad_request_error_returns_down(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.exceptions.BadRequestError(400, "bad request", {})

        res = list_gwflow_jobs(self.non_ligo_user)

        self.assertEqual(res["state"], "down")
        self.assertEqual(res["jobs"], {})

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_list_gwflow_jobs_reconciliation_preserves_authorised_rows(self, mock_get_es_client):
        """A stale/restricted hit must not blank the whole page: authorised rows
        are preserved and stale vs restricted are logged separately."""
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
        # Fail closed: the ES total may include restricted records, so it is not
        # exposed as an exact count.
        self.assertEqual(res["total"], 1)
        self.assertFalse(res["has_next"])
        logged = " ".join(str(c.args) for c in mock_warn.call_args_list)
        self.assertIn("stale", logged)
        self.assertIn("restricted", logged)

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

        query = mock_client.search.call_args[1]["query"]
        filter_terms = {}
        for f in query["bool"]["filter"]:
            for _clause_type, clause in f.items():
                filter_terms.update(clause)
        self.assertEqual(filter_terms["libraries.keyword"], 'cbc-workflow "o4a"')
        self.assertEqual(filter_terms["analyses.reviewStatus.keyword"], "approved")
        self.assertIn("ligoOnly", filter_terms)
        self.assertIn("isPruned", filter_terms)
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

        query = mock_client.search.call_args[1]["query"]
        filter_terms = {}
        for f in query["bool"]["filter"]:
            for _clause_type, clause in f.items():
                filter_terms.update(clause)
        self.assertEqual(filter_terms["analyses.reviewStatus.keyword"], "a:b*c")

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
        filter_terms = {}
        for f in query["bool"]["filter"]:
            for _clause_type, clause in f.items():
                filter_terms.update(clause)
        self.assertEqual(filter_terms["libraries.keyword"], "lib-a")
        self.assertEqual(filter_terms["analyses.reviewStatus.keyword"], "reviewed")

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
        filter_terms = {}
        for f in query["bool"]["filter"]:
            for _clause_type, clause in f.items():
                filter_terms.update(clause)
        self.assertEqual(filter_terms["libraries.keyword"], 'x" OR ligoOnly:true OR libraries:"y')
        self.assertEqual(filter_terms["analyses.reviewStatus.keyword"], "a && b || !c")

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


class TestGWFlowFilterOptions(BilbyTestCase):
    def setUp(self):
        super().setUp()
        caches["default"].clear()
        self.user = self.create_user(id=200, name="Filter User", primary_email="filter@example.com")

    @patch("bilbyui.services.gwflow.get_es_client", side_effect=elasticsearch.exceptions.ConnectionError("down"))
    def test_libraries_from_db_sorted_deduped(self, mock_get_es_client):
        GWFlowJob.objects.create(
            sname="S200201a", user=self.user, ligo_only=False, libraries=["b-library", "a-library"]
        )
        GWFlowJob.objects.create(
            sname="S200201b", user=self.user, ligo_only=False, libraries=["a-library", "c-library"]
        )

        options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], ["a-library", "b-library", "c-library"])
        self.assertEqual(
            caches["default"].get("gwflow_filter_libraries"),
            ["a-library", "b-library", "c-library"],
        )

    @patch("bilbyui.services.gwflow.get_es_client", side_effect=elasticsearch.exceptions.ConnectionError("down"))
    def test_libraries_from_db_case_insensitive_sort(self, mock_get_es_client):
        GWFlowJob.objects.create(sname="S200201c", user=self.user, ligo_only=False, libraries=["Zeta", "alpha"])

        options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], ["alpha", "Zeta"])

    @patch("bilbyui.services.gwflow.get_es_client", side_effect=elasticsearch.exceptions.ConnectionError("down"))
    def test_libraries_cached(self, mock_get_es_client):
        GWFlowJob.objects.create(sname="S200201d", user=self.user, ligo_only=False, libraries=["a-library"])
        list_gwflow_filter_options()

        GWFlowJob.objects.create(sname="S200201e", user=self.user, ligo_only=False, libraries=["b-library"])

        options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], ["a-library"])

    @patch("bilbyui.services.gwflow.get_es_client", side_effect=elasticsearch.exceptions.ConnectionError("down"))
    def test_libraries_exclude_ligo_only_jobs(self, mock_get_es_client):
        GWFlowJob.objects.create(sname="S200201f", user=self.user, ligo_only=False, libraries=["public-lib"])
        GWFlowJob.objects.create(sname="S200201g", user=self.user, ligo_only=True, libraries=["ligo-secret-lib"])

        options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"], ["public-lib"])
        self.assertNotIn("ligo-secret-lib", options["libraries"])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_review_statuses_from_es_aggregation(self, mock_get_es_client):
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

        options = list_gwflow_filter_options()

        self.assertEqual(options["review_statuses"], ["approved", "pending"])
        self.assertEqual(
            caches["default"].get("gwflow_filter_review_statuses"),
            ["approved", "pending"],
        )
        call_kwargs = mock_client.search.call_args[1]
        self.assertEqual(call_kwargs["q"], "isPruned:false AND ligoOnly:false")
        self.assertEqual(call_kwargs["size"], 0)

    @patch("bilbyui.services.gwflow.get_es_client", side_effect=elasticsearch.exceptions.ConnectionError("down"))
    def test_review_statuses_fallback_on_connection_error(self, mock_get_es_client):
        options = list_gwflow_filter_options()

        self.assertEqual(options["review_statuses"], ["reviewed", "unreviewed", "pending", "approved"])
        self.assertIsNone(caches["default"].get("gwflow_filter_review_statuses"))

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_review_statuses_fallback_on_not_found(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.side_effect = elasticsearch.NotFoundError(404, "index not found", {})

        options = list_gwflow_filter_options()

        self.assertEqual(options["review_statuses"], ["reviewed", "unreviewed", "pending", "approved"])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_review_statuses_fallback_on_empty_buckets(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {"aggregations": {"review_statuses": {"buckets": []}}}

        options = list_gwflow_filter_options()

        self.assertEqual(options["review_statuses"], ["reviewed", "unreviewed", "pending", "approved"])

    @patch("bilbyui.services.gwflow.get_es_client")
    def test_review_statuses_cached(self, mock_get_es_client):
        mock_client = MagicMock()
        mock_get_es_client.return_value = mock_client
        mock_client.search.return_value = {
            "aggregations": {
                "review_statuses": {
                    "buckets": [{"key": "approved", "doc_count": 1}],
                }
            }
        }

        list_gwflow_filter_options()
        mock_client.search.reset_mock()
        list_gwflow_filter_options()

        mock_client.search.assert_not_called()
