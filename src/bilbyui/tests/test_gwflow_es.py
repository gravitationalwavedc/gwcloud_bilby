from unittest.mock import MagicMock, patch

import elasticsearch
import requests
from django.core.management import call_command
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_es import (
    build_gwflow_es_doc,
    gwflow_elastic_search_remove,
    gwflow_elastic_search_update,
    update_child_job_ids,
)


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
            ligo_only=True,
            is_pruned=False,
            event_id=self.event_id,
        )

    def test_build_gwflow_es_doc_golden_v3(self):
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

        self.assertEqual(doc["user"]["name"], "Jane Doe")
        self.assertEqual(doc["sname"], "S150914a")
        self.assertEqual(doc["schemaVersion"], "v3")
        self.assertEqual(doc["libraries"], ["cbc-workflow-o4a"])
        self.assertTrue(doc["ligoOnly"])
        self.assertFalse(doc["isPruned"])
        self.assertEqual(doc["eventId"]["eventId"], "GW150914")
        self.assertEqual(doc["eventId"]["gpsTime"], 1126259462.4)
        self.assertEqual(len(doc["analyses"]), 2)

        pe_analysis = doc["analyses"][0]
        self.assertEqual(pe_analysis["uid"], "pe-uid-1")
        self.assertEqual(pe_analysis["type"], "pe")
        self.assertEqual(pe_analysis["software"], "bilby")
        self.assertEqual(pe_analysis["waveform"], "IMRPhenomXPHM")
        self.assertEqual(pe_analysis["analysts"], ["Alice", "Bob"])
        self.assertEqual(pe_analysis["reviewers"], ["Charlie"])

        tgr_analysis = doc["analyses"][1]
        self.assertEqual(tgr_analysis["uid"], "tgr-uid-1")
        self.assertEqual(tgr_analysis["type"], "tgr")
        self.assertEqual(tgr_analysis["software"], "pycbc")

        self.assertEqual(doc["gracedb"]["uids"], ["G197392", "G197393"])
        self.assertEqual(doc["gracedb"]["instruments"], "H1,L1")

    def test_build_gwflow_es_doc_missing_sections(self):
        doc = build_gwflow_es_doc(self.job, {})
        self.assertEqual(doc["sname"], "S150914a")
        self.assertEqual(doc["analyses"], [])
        self.assertEqual(doc["gracedb"]["uids"], [])
        self.assertEqual(doc["gracedb"]["gpsTime"], "")

    def test_build_gwflow_es_doc_non_dict_metadata(self):
        doc = build_gwflow_es_doc(self.job, None)
        self.assertEqual(doc["sname"], "S150914a")
        self.assertEqual(doc["analyses"], [])

    def test_build_gwflow_es_doc_no_event_id(self):
        self.job.event_id = None
        self.job.save()
        doc = build_gwflow_es_doc(self.job, {})
        self.assertIsNone(doc["eventId"])


class TestGWFlowESUpdateRemove(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=11, primary_email="user11@example.com")
        self.job = GWFlowJob.objects.create(
            sname="S150914b",
            user=self.user,
        )
        self.child_job_1 = BilbyJob.objects.create(
            user=self.user,
            name="child_1",
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "job_1"}),
            gwflow_job=self.job,
        )
        self.child_job_2 = BilbyJob.objects.create(
            user=self.user,
            name="child_2",
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "job_2"}),
            gwflow_job=self.job,
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

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    @patch("elasticsearch.Elasticsearch")
    def test_update_child_job_ids_ignored(self, mock_es):
        update_child_job_ids(self.job)
        mock_es.assert_not_called()

    @override_settings(
        IGNORE_ELASTIC_SEARCH=False,
        ELASTIC_SEARCH_HOST="localhost",
        ELASTIC_SEARCH_API_KEY="test_key",
        ELASTIC_SEARCH_GWFLOW_INDEX="gwflow_test_idx",
    )
    @patch("elasticsearch.Elasticsearch")
    def test_update_child_job_ids_updates_doc(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client

        update_child_job_ids(self.job)

        mock_client.update.assert_called_once()
        call_kwargs = mock_client.update.call_args.kwargs
        self.assertEqual(call_kwargs["index"], "gwflow_test_idx")
        self.assertEqual(call_kwargs["id"], self.job.id)
        self.assertEqual(
            call_kwargs["doc"]["childJobIds"],
            list(self.job.bilby_jobs.values_list("id", flat=True)),
        )

    @override_settings(
        IGNORE_ELASTIC_SEARCH=False,
        ELASTIC_SEARCH_HOST="localhost",
        ELASTIC_SEARCH_API_KEY="test_key",
        ELASTIC_SEARCH_GWFLOW_INDEX="gwflow_test_idx",
    )
    @patch("elasticsearch.Elasticsearch")
    def test_update_child_job_ids_swallows_not_found(self, mock_es_cls):
        mock_client = MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.update.side_effect = elasticsearch.NotFoundError(404, "not found", {})

        update_child_job_ids(self.job)
        mock_client.update.assert_called_once()

    @override_settings(IGNORE_ELASTIC_SEARCH=False)
    @patch("bilbyui.models.gwflow_elastic_search_remove")
    def test_pre_delete_signal(self, mock_remove):
        job = GWFlowJob.objects.create(sname="S150914c", user=self.user)
        job.delete()
        mock_remove.assert_called_once()


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
