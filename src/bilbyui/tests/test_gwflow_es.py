import datetime
from unittest.mock import MagicMock, patch

import elasticsearch
import requests
from django.core.management import call_command
from django.test import override_settings

from bilbyui.models import EventID, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_es import (
    InvalidGWFlowMetadata,
    _collect_review_statuses,
    build_gwflow_es_doc,
    get_es_client,
    gwflow_elastic_search_remove,
    gwflow_elastic_search_update,
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
