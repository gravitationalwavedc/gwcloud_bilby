import datetime
from unittest.mock import MagicMock, patch

import elasticsearch
import requests
from django.core.cache import caches
from django.core.management import call_command
from django.test import override_settings

from bilbyui.models import EventID, GWFlowJob
from bilbyui.services.gwflow import list_gwflow_filter_options, list_gwflow_jobs
from bilbyui.tests.gwflow_es_fixtures import (
    QUERY_ASSERTIONS,
    QUERY_REFERENCE_DATE,
    build_canonical_fixtures,
)
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_es import (
    InvalidGWFlowMetadata,
    _collect_review_statuses,
    build_gwflow_es_doc,
    get_es_client,
    gwflow_elastic_search_remove,
    gwflow_elastic_search_update,
    parse_analyses,
)

_GWCLOUD_FIELDS = {
    "sname",
    "libraries",
    "isPruned",
    "ligoOnly",
    "lastUpdatedTime",
    "reviewStatuses",
    "eventTriggerId",
}


class TestGWFlowESDocBuilder(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=10, name="Jane Doe", primary_email="jane@example.com")
        self.event_id = EventID.objects.create(
            event_id="GW150914",
            trigger_id="S150914a",
            nickname="The First",
            gps_time=1126259462.4,
        )
        self.job = GWFlowJob.objects.create(
            sname="S150914a",
            user=self.user,
            schema_version="v3",
            libraries=["cbc-workflow-o4a"],
            current_history_id="hist-001",
            current_history_timestamp=datetime.datetime(2026, 8, 31, 12, 34, 56, tzinfo=datetime.UTC),
            ligo_only=True,
            is_pruned=False,
            event_id=self.event_id,
        )

    def test_build_gwflow_es_doc_golden(self):
        metadata = {
            "ParameterEstimation": {
                "results": [
                    {
                        "uid": "pe-uid-1",
                        "inference_software": "bilby",
                        "waveform_approximant": "IMRPhenomXPHM",
                        "run_status": "completed",
                        "review_status": "approved",
                        "analysts": ["Alice", {"name": "Bob"}],
                        "reviewers": ["Charlie"],
                    }
                ]
            },
            "TGR": [
                {
                    "uid": "tgr-uid-1",
                    "software": "pycbc",
                    "waveform": "IMRPhenomD",
                    "run_status": "completed",
                    "review_status": "pending",
                    "analysts": ["Dave"],
                }
            ],
            "GraceDB": {
                "Events": [{"uid": "G197392"}, {"id": "G197393"}],
                "preferred_event_gps": 1126259462.4,
                "preferred_event_far": 1e-7,
                "instruments": "H1,L1",
            },
        }

        doc = build_gwflow_es_doc(self.job, metadata)

        self.assertEqual(set(doc.keys()), {"_gwcloud", "metadata"})
        self.assertEqual(set(doc["_gwcloud"].keys()), _GWCLOUD_FIELDS)
        self.assertEqual(doc["metadata"], metadata)

        envelope = doc["_gwcloud"]
        self.assertEqual(envelope["sname"], "S150914a")
        self.assertEqual(envelope["libraries"], ["cbc-workflow-o4a"])
        self.assertFalse(envelope["isPruned"])
        self.assertTrue(envelope["ligoOnly"])
        self.assertEqual(envelope["lastUpdatedTime"], "2026-08-31T12:34:56+00:00")
        self.assertEqual(envelope["eventTriggerId"], "S150914a")
        self.assertEqual(envelope["reviewStatuses"], ["approved", "pending"])

    def test_build_gwflow_es_doc_unknown_future_sections_preserved(self):
        metadata = {
            "ParameterEstimation": {"results": [{"uid": "pe-1", "review_status": "approved"}]},
            "FutureAnalysisType": {"some_new_field": {"deep": [1, 2, 3]}},
            "AnotherUnknown": ["a", "b"],
        }

        doc = build_gwflow_es_doc(self.job, metadata)

        self.assertEqual(doc["metadata"], metadata)
        self.assertEqual(doc["_gwcloud"]["reviewStatuses"], ["approved"])

    def test_build_gwflow_es_doc_nested_arrays(self):
        metadata = {
            "ParameterEstimation": {
                "results": [
                    {"uid": "pe-1", "review_status": "approved"},
                    {"uid": "pe-2", "review_status": "pending"},
                ]
            },
            "TGR": [
                [
                    {"uid": "tgr-1", "review_status": "needs_review"},
                    {"review_status": "withdrawn"},
                ]
            ],
        }

        doc = build_gwflow_es_doc(self.job, metadata)

        self.assertEqual(doc["metadata"], metadata)
        self.assertEqual(
            doc["_gwcloud"]["reviewStatuses"],
            ["approved", "pending", "needs_review", "withdrawn"],
        )

    def test_build_gwflow_es_doc_missing_statuses(self):
        metadata = {"ParameterEstimation": {"results": [{"uid": "pe-1", "run_status": "completed"}]}}

        doc = build_gwflow_es_doc(self.job, metadata)

        self.assertEqual(doc["_gwcloud"]["reviewStatuses"], [])

    def test_build_gwflow_es_doc_duplicates_deduplicated(self):
        metadata = {
            "ParameterEstimation": {"results": [{"review_status": "approved"}]},
            "TGR": [{"review_status": "approved"}],
            "Lensing": {"review_status": "approved"},
        }

        doc = build_gwflow_es_doc(self.job, metadata)

        self.assertEqual(doc["_gwcloud"]["reviewStatuses"], ["approved"])

    def test_build_gwflow_es_doc_non_scalar_review_status_skipped(self):
        metadata = {
            "ParameterEstimation": {"results": [{"review_status": "approved"}]},
            "TGR": [{"review_status": {"nested": "pending"}}],
            "Lensing": {"review_status": ["needs_review"]},
        }

        with self.assertLogs("bilbyui.utils.gwflow_es", level="WARNING") as logs:
            doc = build_gwflow_es_doc(self.job, metadata)

        self.assertEqual(doc["_gwcloud"]["reviewStatuses"], ["approved"])
        self.assertEqual(len(logs.records), 2)
        self.assertTrue(all("Non-scalar review_status" in r.getMessage() for r in logs.records))

    def test_build_gwflow_es_doc_null_current_history_timestamp(self):
        self.job.current_history_timestamp = None
        self.job.save()

        doc = build_gwflow_es_doc(self.job, {"ParameterEstimation": {"results": []}})

        self.assertIsNone(doc["_gwcloud"]["lastUpdatedTime"])

    def test_build_gwflow_es_doc_no_event_link(self):
        self.job.event_id = None
        self.job.save()

        doc = build_gwflow_es_doc(self.job, {"ParameterEstimation": {"results": []}})

        self.assertIsNone(doc["_gwcloud"]["eventTriggerId"])

    def test_build_gwflow_es_doc_invalid_non_object(self):
        for bad in (None, [], "not-a-dict", 42):
            with self.subTest(bad=bad):
                with self.assertRaises(InvalidGWFlowMetadata):
                    build_gwflow_es_doc(self.job, bad)

    def test_build_gwflow_es_doc_invalid_nan(self):
        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(self.job, {"x": float("nan")})

    def test_build_gwflow_es_doc_invalid_infinity(self):
        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(self.job, {"x": float("inf")})

    def test_build_gwflow_es_doc_invalid_non_json_value(self):
        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(self.job, {"x": {1, 2, 3}})

    def test_build_gwflow_es_doc_invalid_lossy_tuple(self):
        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(self.job, {"x": (1, 2, 3)})

    def test_build_gwflow_es_doc_invalid_lossy_non_string_key(self):
        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(self.job, {1: "one"})

    def test_build_gwflow_es_doc_invalid_deeply_nested(self):
        metadata = {}
        node = metadata
        for _ in range(2000):
            node["x"] = {}
            node = node["x"]
        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(self.job, metadata)

    def test_build_gwflow_es_doc_envelope_has_exactly_seven_fields(self):
        doc = build_gwflow_es_doc(self.job, {"ParameterEstimation": {"results": []}})

        self.assertEqual(set(doc["_gwcloud"].keys()), _GWCLOUD_FIELDS)

    def test_build_gwflow_es_doc_metadata_deep_equal_to_input(self):
        metadata = {
            "ParameterEstimation": {
                "results": [
                    {
                        "uid": "pe-1",
                        "review_status": "approved",
                        "analysts": [{"name": "Alice"}, "Bob"],
                        "nested": {"deep": [1, 2, {"three": 3}]},
                    }
                ]
            },
            "Unknown": {"capitalised": True, "value": 1.5},
        }

        doc = build_gwflow_es_doc(self.job, metadata)

        self.assertEqual(doc["metadata"], metadata)

    def test_parse_analyses_malformed_first_record_does_not_abort_later_records(self):
        """A single malformed record must not discard later valid analyses."""

        class RaisingGetDict(dict):
            def get(self, *args, **kwargs):
                raise ValueError("boom")

        metadata = {
            "ParameterEstimation": {
                "results": [
                    RaisingGetDict({"uid": "bad-1"}),
                    {"uid": "good-1", "inference_software": "bilby", "run_status": "completed"},
                ]
            }
        }

        analyses = parse_analyses(metadata)

        self.assertEqual([a["uid"] for a in analyses], ["good-1"])
        self.assertEqual(analyses[0]["software"], "bilby")

    def test_parse_analyses_non_dict_returns_empty(self):
        self.assertEqual(parse_analyses(None), [])
        self.assertEqual(parse_analyses("not-a-dict"), [])

    def test_parse_analyses_scalar_analysts_reviewers_wrapped_in_list(self):
        """A non-list scalar analysts/reviewers value is wrapped as a single string."""
        metadata = {
            "ParameterEstimation": {
                "results": [
                    {
                        "uid": "pe-1",
                        "analysts": "Alice",
                        "reviewers": "Bob",
                    }
                ]
            }
        }

        analyses = parse_analyses(metadata)

        self.assertEqual(analyses[0]["analysts"], ["Alice"])
        self.assertEqual(analyses[0]["reviewers"], ["Bob"])

    def test_parse_analyses_missing_analysts_reviewers_default_to_empty(self):
        """Missing analysts/reviewers fields default to empty lists."""
        metadata = {
            "ParameterEstimation": {
                "results": [
                    {
                        "uid": "pe-1",
                    }
                ]
            }
        }

        analyses = parse_analyses(metadata)

        self.assertEqual(analyses[0]["analysts"], [])
        self.assertEqual(analyses[0]["reviewers"], [])

    def test_parse_analyses_mixed_dict_and_string_list_entries(self):
        """List entries that are dicts use their 'name'; plain strings are kept as-is."""
        metadata = {
            "ParameterEstimation": {
                "results": [
                    {
                        "uid": "pe-1",
                        "analysts": [{"name": "Alice"}, "Bob", None],
                        "reviewers": [{"name": "Carol"}, "Dave"],
                    }
                ]
            }
        }

        analyses = parse_analyses(metadata)

        self.assertEqual(analyses[0]["analysts"], ["Alice", "Bob"])
        self.assertEqual(analyses[0]["reviewers"], ["Carol", "Dave"])


class TestCollectReviewStatuses(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.job = MagicMock(id=99, current_history_id="hist-001")

    def test_collect_nested_and_array_review_statuses(self):
        metadata = {
            "ParameterEstimation": {
                "results": [
                    {"uid": "pe-1", "review_status": "approved"},
                    {"uid": "pe-2", "review_status": "pending"},
                ]
            },
            "TGR": [
                [
                    {"uid": "tgr-1", "review_status": "needs_review"},
                    {"review_status": "withdrawn"},
                ]
            ],
        }

        result = _collect_review_statuses(metadata, self.job)

        self.assertEqual(result, ["approved", "pending", "needs_review", "withdrawn"])

    def test_collect_deduplicates_preserving_first_occurrence(self):
        metadata = {
            "ParameterEstimation": {"results": [{"review_status": "approved"}]},
            "TGR": [{"review_status": "approved"}],
            "Lensing": {"review_status": "approved"},
        }

        result = _collect_review_statuses(metadata, self.job)

        self.assertEqual(result, ["approved"])

    def test_collect_non_scalar_review_status_skipped_with_warning(self):
        metadata = {
            "ParameterEstimation": {"results": [{"review_status": "approved"}]},
            "TGR": [{"review_status": {"nested": "pending"}}],
            "Lensing": {"review_status": ["needs_review"]},
        }

        with self.assertLogs("bilbyui.utils.gwflow_es", level="WARNING") as logs:
            result = _collect_review_statuses(metadata, self.job)

        self.assertEqual(result, ["approved"])
        self.assertEqual(len(logs.records), 2)
        self.assertTrue(all("Non-scalar review_status" in r.getMessage() for r in logs.records))

    def test_collect_empty_metadata(self):
        for empty in ({}, [], None, "scalar", 42):
            with self.subTest(empty=empty):
                self.assertEqual(_collect_review_statuses(empty, self.job), [])

    def test_collect_scalar_leaf_values_ignored(self):
        metadata = {
            "ParameterEstimation": {"results": [{"uid": "pe-1", "run_status": "completed"}]},
            "GraceDB": {"Events": [{"uid": "G197392"}]},
        }

        result = _collect_review_statuses(metadata, self.job)

        self.assertEqual(result, [])


class TestGWFlowESUpdateRemove(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=11, primary_email="user11@example.com")
        self.job = GWFlowJob.objects.create(
            sname="S150914b",
            user=self.user,
        )

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    @patch("elasticsearch.Elasticsearch")
    def test_update_ignored(self, mock_es):
        gwflow_elastic_search_update(self.job, {})
        mock_es.assert_not_called()

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    @patch("elasticsearch.Elasticsearch")
    def test_remove_ignored(self, mock_es):
        gwflow_elastic_search_remove(self.job)
        mock_es.assert_not_called()

    @override_settings(
        IGNORE_ELASTIC_SEARCH=False,
        ELASTIC_SEARCH_HOST="localhost",
        ELASTIC_SEARCH_API_KEY="test_key",
        ELASTIC_SEARCH_GWFLOW_INDEX="gwflow_test_idx",
    )
    @patch("elasticsearch.Elasticsearch")
    def test_update_and_index_fallback(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.update.side_effect = elasticsearch.NotFoundError(404, "not found", {})

        gwflow_elastic_search_update(self.job, {})

        mock_client.update.assert_called_once()
        mock_client.index.assert_called_once()

    @override_settings(
        IGNORE_ELASTIC_SEARCH=False,
        ELASTIC_SEARCH_HOST="localhost",
        ELASTIC_SEARCH_API_KEY="test_key",
        ELASTIC_SEARCH_GWFLOW_INDEX="gwflow_test_idx",
    )
    @patch("elasticsearch.Elasticsearch")
    def test_remove_swallows_not_found(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.delete.side_effect = elasticsearch.NotFoundError(404, "not found", {})

        gwflow_elastic_search_remove(self.job)
        mock_client.delete.assert_called_once()

    @override_settings(
        IGNORE_ELASTIC_SEARCH=False,
        ELASTIC_SEARCH_HOST="localhost",
        ELASTIC_SEARCH_API_KEY="test_key",
        ELASTIC_SEARCH_GWFLOW_INDEX="gwflow_test_idx",
    )
    @patch("elasticsearch.Elasticsearch")
    def test_update_non_object_makes_zero_es_calls_and_leaves_doc_unchanged(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client

        gwflow_elastic_search_update(self.job, "not-an-object")

        mock_client.update.assert_not_called()
        mock_client.index.assert_not_called()

    @override_settings(IGNORE_ELASTIC_SEARCH=False)
    @patch("bilbyui.models.gwflow_elastic_search_remove")
    def test_pre_delete_signal(self, mock_remove):
        job = GWFlowJob.objects.create(sname="S150914c", user=self.user)
        job.delete()
        mock_remove.assert_called_once()


class TestGetESClient(BilbyTestCase):
    @override_settings(
        ELASTIC_SEARCH_HOST="https://es.example.com:9200",
        ELASTIC_SEARCH_API_KEY="test_api_key",
    )
    @patch("elasticsearch.Elasticsearch")
    def test_get_es_client_uses_configured_settings(self, mock_es_cls):
        get_es_client()

        mock_es_cls.assert_called_once_with(
            hosts=["https://es.example.com:9200"],
            api_key="test_api_key",
            verify_certs=False,
        )


class TestESIngestGWFlowCommand(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=12, primary_email="user12@example.com")
        self.job = GWFlowJob.objects.create(sname="S230601ag", user=self.user)

    @override_settings(CBCFLOW_PORTAL_URL="", CBCFLOW_PORTAL_TOKEN="")
    def test_ingest_gwflow_missing_settings(self):
        call_command("es_ingest", "--gwflow")

    @override_settings(
        CBCFLOW_PORTAL_URL="https://portal.example.com",
        CBCFLOW_PORTAL_TOKEN="Bearer token123",
        IGNORE_ELASTIC_SEARCH=True,
    )
    @patch("requests.get")
    def test_ingest_gwflow_success(self, mock_get):
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "results": [{"sname": "S230601ag"}],
            "next": None,
        }

        detail_resp = MagicMock()
        detail_resp.status_code = 200
        detail_resp.json.return_value = {"ParameterEstimation": {"results": []}}

        mock_get.side_effect = [list_resp, detail_resp]

        call_command("es_ingest", "--gwflow")
        self.assertEqual(mock_get.call_count, 2)

    @override_settings(
        CBCFLOW_PORTAL_URL="https://portal.example.com",
        CBCFLOW_PORTAL_TOKEN="Bearer token123",
        IGNORE_ELASTIC_SEARCH=True,
    )
    @patch("requests.get")
    def test_ingest_gwflow_skips_invalid_detail_json(self, mock_get):
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "results": [{"sname": "S230601ag"}, {"sname": "S230601ah"}],
            "next": None,
        }

        invalid_detail_resp = MagicMock()
        invalid_detail_resp.status_code = 200
        invalid_detail_resp.json.side_effect = ValueError("No JSON object could be decoded")

        valid_detail_resp = MagicMock()
        valid_detail_resp.status_code = 200
        valid_detail_resp.json.return_value = {"ParameterEstimation": {"results": []}}

        mock_get.side_effect = [list_resp, invalid_detail_resp, valid_detail_resp]

        call_command("es_ingest", "--gwflow")
        self.assertEqual(mock_get.call_count, 3)

    @override_settings(
        CBCFLOW_PORTAL_URL="https://portal.example.com",
        CBCFLOW_PORTAL_TOKEN="Bearer token123",
        IGNORE_ELASTIC_SEARCH=True,
    )
    @patch("requests.get")
    def test_ingest_gwflow_skips_detail_request_error(self, mock_get):
        list_resp = MagicMock()
        list_resp.status_code = 200
        list_resp.json.return_value = {
            "results": [{"sname": "S230601ag"}, {"sname": "S230601ah"}],
            "next": None,
        }

        detail_resp = MagicMock()
        detail_resp.status_code = 200
        detail_resp.json.return_value = {"ParameterEstimation": {"results": []}}

        mock_get.side_effect = [list_resp, requests.ConnectionError("connection timeout"), detail_resp]

        call_command("es_ingest", "--gwflow")
        self.assertEqual(mock_get.call_count, 3)


class FakeGWFlowES:
    """Minimal in-memory Elasticsearch for deterministic integration tests.

    Indexes the canonical fixture documents and evaluates the exact query DSL
    produced by ``list_gwflow_jobs`` and the filter-option collectors against
    them, so the issue #72 query assertion table is verified against real query
    construction with no reliance on a live ES server.

    Supported query constructs (the subset the service emits):
    - ``bool`` with ``must`` and ``filter`` lists
    - ``match_all``
    - ``term`` (exact match, including membership in a keyword array)
    - ``range`` on ``_gwcloud.lastUpdatedTime`` (ISO-8601 bounds)
    - ``query_string`` with ``field:*`` (exists) and ``field:value`` (term)
    - ``terms`` aggregation with per-bucket doc counts
    - sort by ``_gwcloud.lastUpdatedTime`` desc with missing values last
    """

    def __init__(self, docs_by_id):
        self.docs = {int(doc_id): entry["doc"] for doc_id, entry in docs_by_id.items()}
        self.search_calls = []
        self._agg_buckets = {}

    def _field_values(self, doc, field):
        """All values reachable at ``field``, flattening arrays of objects.

        Mirrors how ES indexes array-of-object paths (e.g.
        ``metadata.ParameterEstimation.results.inference_software``) as a set
        of leaf values, so a term query matches if any element matches.
        """
        parts = field.split(".")
        values = []

        def walk(node, idx):
            if idx == len(parts):
                values.append(node)
                return
            if isinstance(node, dict):
                if parts[idx] in node:
                    walk(node[parts[idx]], idx + 1)
            elif isinstance(node, list):
                for item in node:
                    walk(item, idx)

        walk(doc, 0)
        return values

    def _exists(self, doc, field):
        for value in self._field_values(doc, field):
            if value is None:
                continue
            if isinstance(value, list):
                if value:
                    return True
                continue
            if value != "":
                return True
        return False

    def _term_matches(self, doc, field, value):
        for actual in self._field_values(doc, field):
            if isinstance(actual, list):
                if value in actual:
                    return True
            elif actual == value:
                return True
        return False

    def _range_matches(self, doc, ranges):
        for field, bounds in ranges.items():
            actual = self._field_values(doc, field)
            actual = next((v for v in actual if v is not None), None)
            if actual is None:
                return False
            actual_dt = datetime.datetime.fromisoformat(actual)
            for op, bound in bounds.items():
                bound_dt = datetime.datetime.fromisoformat(bound)
                if op == "gte" and actual_dt < bound_dt:
                    return False
                if op == "lte" and actual_dt > bound_dt:
                    return False
        return True

    def _query_string_matches(self, doc, qs):
        query = qs.strip()
        if not query or query == "*":
            return True
        if ":" in query:
            field, _, value = query.partition(":")
            value = value.strip()
            if value == "*":
                return self._exists(doc, field)
            return self._term_matches(doc, field, value)
        return False

    def _matches_clause(self, doc, clause):
        if "match_all" in clause:
            return True
        if "term" in clause:
            field, value = next(iter(clause["term"].items()))
            return self._term_matches(doc, field, value)
        if "range" in clause:
            return self._range_matches(doc, clause["range"])
        if "query_string" in clause:
            return self._query_string_matches(doc, clause["query_string"]["query"])
        if "bool" in clause:
            return self._matches_bool(doc, clause["bool"])
        raise NotImplementedError(f"Unsupported query clause in FakeGWFlowES: {clause!r}")

    def _matches_bool(self, doc, bool_q):
        for key in ("must", "filter"):
            for clause in bool_q.get(key, []):
                if not self._matches_clause(doc, clause):
                    return False
        return True

    def _sort_key(self, doc, sort):
        values = self._field_values(doc, "_gwcloud.lastUpdatedTime")
        ts = next((v for v in values if v is not None), None)
        if ts is None:
            return (1, 0)
        return (0, -datetime.datetime.fromisoformat(ts).timestamp())

    def _aggregations(self, matching_ids, aggs):
        result = {}
        for name, agg in aggs.items():
            if "terms" not in agg:
                continue
            field = agg["terms"]["field"]
            counts = {}
            for doc_id in matching_ids:
                for value in self._field_values(self.docs[doc_id], field):
                    if isinstance(value, list):
                        for item in value:
                            counts[item] = counts.get(item, 0) + 1
                    elif value is not None:
                        counts[value] = counts.get(value, 0) + 1
            buckets = [
                {"key": key, "doc_count": count}
                for key, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ]
            result[name] = {"buckets": buckets}
            self._agg_buckets[name] = buckets
        return result

    def agg_buckets(self, name):
        return self._agg_buckets.get(name, [])

    def search(
        self,
        index,
        query=None,
        size=None,
        from_=0,
        sort=None,
        track_total_hits=None,
        request_timeout=None,
        aggs=None,
        **kwargs,
    ):
        self.search_calls.append(
            {"index": index, "query": query, "size": size, "from_": from_, "sort": sort, "aggs": aggs}
        )
        matching = [doc_id for doc_id, doc in self.docs.items() if self._matches_clause(doc, query)]
        matching.sort(key=lambda doc_id: self._sort_key(self.docs[doc_id], sort))
        total = len(matching)
        hits = [{"_id": str(doc_id), "_source": self.docs[doc_id]} for doc_id in matching]
        if size is not None:
            hits = hits[from_ : from_ + size]
        response = {"hits": {"total": {"value": total, "relation": "eq"}, "hits": hits}}
        if aggs:
            response["aggregations"] = self._aggregations(matching, aggs)
        return response


class TestGWFlowESIntegration(BilbyTestCase):
    """Deterministic integration test of the list query construction and
    filter-option aggregations against the #71 mapping using the canonical
    fixture matrix, with no reliance on a live ES server."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.fixtures = build_canonical_fixtures(cls)
        cls.non_ligo_user = cls.create_user(
            id=700, name="Public User", primary_email="public700@example.com", authentication_method="password"
        )

    def setUp(self):
        super().setUp()
        self.fake_es = FakeGWFlowES(self.fixtures)
        self._es_patcher = patch("bilbyui.services.gwflow.get_es_client", return_value=self.fake_es)
        self._es_patcher.start()
        self.addCleanup(self._es_patcher.stop)
        caches["default"].clear()

    def _ids(self, res):
        return [record["_id"] for record in res["records"]]

    def test_query_assertion_table(self):
        """Every entry in the issue #72 query assertion table returns exactly
        the expected ordered document ids for a public, non-pruned query."""
        for label, kwargs, expected in QUERY_ASSERTIONS:
            with self.subTest(label=label):
                if label == "updated past 30 days":
                    with patch(
                        "bilbyui.services.gwflow.timezone.now",
                        return_value=QUERY_REFERENCE_DATE,
                    ):
                        res = list_gwflow_jobs(self.non_ligo_user, **kwargs)
                else:
                    res = list_gwflow_jobs(self.non_ligo_user, **kwargs)
                self.assertEqual(res["state"], "ok")
                self.assertEqual(self._ids(res), expected)

    def test_library_and_review_filters_are_terms_on_gwcloud_fields(self):
        """The library and review-status filters are term clauses on the
        _gwcloud.* keyword fields (not .keyword, not the old paths)."""
        list_gwflow_jobs(self.non_ligo_user, library="cbc-workflow-o4a", review_status="approved")
        query = self.fake_es.search_calls[-1]["query"]
        filter_terms = {}
        for clause in query["bool"]["filter"]:
            for clause_type, body in clause.items():
                if clause_type == "term":
                    filter_terms.update(body)
        self.assertEqual(filter_terms["_gwcloud.libraries"], "cbc-workflow-o4a")
        self.assertEqual(filter_terms["_gwcloud.reviewStatuses"], "approved")
        self.assertNotIn("libraries.keyword", filter_terms)
        self.assertNotIn("analyses.reviewStatus.keyword", filter_terms)

    def test_ligo_user_sees_ligo_only_and_pruned(self):
        """A LIGO user (include_pruned) sees fixtures 3 and 4, which the
        public query excludes."""
        ligo_user = self.create_user(
            id=701, name="LIGO User", primary_email="ligo701@example.com", authentication_method="ligo_shibboleth"
        )
        # match_all: a LIGO user with include_pruned sees all five fixtures
        # (sorted by _gwcloud.lastUpdatedTime desc, missing last).
        res = list_gwflow_jobs(ligo_user, include_pruned=True)
        self.assertEqual(self._ids(res), [1, 2, 3, 4, 5])

    def test_non_ligo_option_aggregation_excludes_ligo_only_and_pruned(self):
        """The public option aggregation excludes fixture 3 (LIGO-only) and
        fixture 4 (pruned), proven by per-bucket doc counts."""
        options = list_gwflow_filter_options()

        self.assertEqual(options["libraries"]["state"], "ok")
        self.assertEqual(
            set(options["libraries"]["values"]),
            {"cbc-workflow-o4a", "cbc-workflow-o4c"},
        )
        lib_counts = {b["key"]: b["doc_count"] for b in self.fake_es.agg_buckets("libraries")}
        # o4a appears on docs 1 and 5 only; doc 4 (pruned) is excluded.
        self.assertEqual(lib_counts["cbc-workflow-o4a"], 2)
        self.assertEqual(lib_counts["cbc-workflow-o4c"], 2)

        self.assertEqual(options["review_statuses"]["state"], "ok")
        self.assertEqual(
            set(options["review_statuses"]["values"]),
            {"approved", "pending", "reviewed", "Approved"},
        )
        rev_counts = {b["key"]: b["doc_count"] for b in self.fake_es.agg_buckets("review_statuses")}
        # approved appears on doc 1 only; doc 3 (LIGO-only) is excluded.
        self.assertEqual(rev_counts["approved"], 1)
        self.assertEqual(rev_counts["pending"], 1)
        self.assertEqual(rev_counts["reviewed"], 1)
        self.assertEqual(rev_counts["Approved"], 1)
