import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from graphql_relay.node.node import to_global_id

from bilbyui.models import BilbyJob, EventID, GWFlowFile, GWFlowJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


class TestGWFlowMutations(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()
        self.normal_user = self.user
        self.ingest_user = self.create_user(id=99, name="ingest user", primary_email="ingest@gwflow.org")

    def _auth_as(self, user):
        if user is None:
            self.deauthenticate()
        else:
            self.authenticate(user=user)

    def test_auth_matrix(self):
        upsert_query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                    }
                }
            }
        """
        upload_query = """
            mutation Upload($input: UploadGwflowFileMutationInput!) {
                uploadGwflowFile(input: $input) {
                    success
                }
            }
        """
        link_query = """
            mutation Link($input: LinkBilbyJobToGwflowMutationInput!) {
                linkBilbyJobToGwflow(input: $input) {
                    success
                }
            }
        """
        pending_query = """
            query {
                gwflowPendingFiles {
                    id
                }
            }
        """

        upsert_input = {"params": {"sname": "S230601auth"}}
        upload_input = {
            "gwflowFileId": to_global_id("GWFlowFileNode", 999),
            "file": None,
        }
        dummy_file = io.BytesIO(b"dummy")
        dummy_file.name = "dummy.txt"
        upload_files = {"input.file": dummy_file}

        link_input = {
            "jobId": to_global_id("BilbyJobNode", 999),
            "sname": "S230601auth",
            "analysisUid": "pe_1",
        }

        with override_settings(GWFLOW_INGEST_USER=99):
            # 1. Anonymous user -> permission denied
            self._auth_as(None)

            res_upsert = self.query(upsert_query, input_data=upsert_input)
            self.assertIsNotNone(res_upsert.errors)
            self.assertIn("Permission Denied", res_upsert.errors[0]["message"])

            res_upload = self.file_query(upload_query, input_data=upload_input, files=upload_files)
            self.assertIsNotNone(res_upload.errors)
            self.assertIn("Permission Denied", res_upload.errors[0]["message"])

            res_link = self.query(link_query, input_data=link_input)
            self.assertIsNotNone(res_link.errors)
            self.assertIn("Permission Denied", res_link.errors[0]["message"])

            res_pending = self.query(pending_query)
            self.assertIsNotNone(res_pending.errors)
            # @login_required fires before our handler for anonymous users
            self.assertTrue(
                any(
                    ("Permission Denied" in e["message"] or "do not have permission" in e["message"])
                    for e in res_pending.errors
                )
            )

            # 2. Non-ingest user -> permission denied
            self._auth_as(self.normal_user)

            res_upsert = self.query(upsert_query, input_data=upsert_input)
            self.assertIsNotNone(res_upsert.errors)
            self.assertIn("Permission Denied", res_upsert.errors[0]["message"])

            res_upload = self.file_query(upload_query, input_data=upload_input, files=upload_files)
            self.assertIsNotNone(res_upload.errors)
            self.assertIn("Permission Denied", res_upload.errors[0]["message"])

            res_link = self.query(link_query, input_data=link_input)
            self.assertIsNotNone(res_link.errors)
            self.assertIn("Permission Denied", res_link.errors[0]["message"])

            res_pending = self.query(pending_query)
            self.assertIsNotNone(res_pending.errors)
            self.assertIn("Permission Denied", res_pending.errors[0]["message"])

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_gwflow_job_create_and_update(self):
        self._auth_as(self.ingest_user)

        event = EventID.create(
            event_id="GW230601_123456",
            gps_time=123456789.0,
            trigger_id="S230601ag",
            is_ligo_event=True,
        )

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        gwflowJobId
                        sname
                        created
                        filesPending {
                            id
                            sname
                            analysisUid
                            path
                            fileName
                            md5Sum
                        }
                    }
                }
            }
        """

        input_data = {
            "params": {
                "sname": "S230601ag",
                "schemaVersion": "v1",
                "libraries": ["cbc-workflow-o4a"],
                "eventId": "S230601ag",
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/data.h5",
                        "fileName": "data.h5",
                        "fileSize": 1024,
                        "md5Sum": "abc123md5",
                    }
                ],
            }
        }

        with mock.patch("bilbyui.views.gwflow_elastic_search_update") as mock_es_update:
            res = self.query(query, input_data=input_data)
            self.assertIsNone(res.errors)

            data = res.data["upsertGwflowJob"]["result"]
            self.assertEqual(data["sname"], "S230601ag")
            self.assertTrue(data["created"])
            self.assertEqual(len(data["filesPending"]), 1)
            self.assertEqual(data["filesPending"][0]["path"], "outdir/data.h5")

            job = GWFlowJob.objects.get(sname="S230601ag")
            self.assertTrue(job.ligo_only)  # Default on creation
            self.assertEqual(job.event_id, event)
            self.assertEqual(job.schema_version, "v1")

        # 2. Re-upsert (Update) without modifying ligo_only (omitted on update)
        input_data_update = {
            "params": {
                "sname": "S230601ag",
                "schemaVersion": "v2",
                "metadata": '{"test": "json"}',
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/data.h5",
                        "fileName": "data.h5",
                        "fileSize": 2048,
                        "md5Sum": "newmd5_456",
                    }
                ],
            }
        }

        with mock.patch("bilbyui.views.gwflow_elastic_search_update") as mock_es_update:
            res_update = self.query(query, input_data=input_data_update)
            self.assertIsNone(res_update.errors)

            data_update = res_update.data["upsertGwflowJob"]["result"]
            self.assertFalse(data_update["created"])

            job.refresh_from_db()
            self.assertEqual(job.schema_version, "v2")
            self.assertTrue(job.ligo_only)  # Kept prior value
            mock_es_update.assert_called_once_with(job, {"test": "json"})

            f_obj = GWFlowFile.objects.get(job=job, path="outdir/data.h5")
            self.assertEqual(f_obj.md5_sum, "newmd5_456")
            self.assertFalse(f_obj.uploaded)

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_event_link_best_effort(self):
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                    }
                }
            }
        """
        # Unknown event_id should not fail job creation
        input_data = {
            "params": {
                "sname": "S230699unknown",
                "eventId": "NONEXISTENT_EVENT",
            }
        }
        res = self.query(query, input_data=input_data)
        self.assertIsNone(res.errors)
        job = GWFlowJob.objects.get(sname="S230699unknown")
        self.assertIsNone(job.event_id)

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upload_gwflow_file(self):
        self._auth_as(self.ingest_user)

        job = GWFlowJob.objects.create(sname="S230601upload", user=self.ingest_user)
        content = b"sample binary file content"
        correct_md5 = hashlib.md5(content).hexdigest()

        gwflow_file = GWFlowFile.objects.create(
            job=job,
            analysis_uid="pe_1",
            path="data.h5",
            file_name="data.h5",
            md5_sum=correct_md5,
            uploaded=False,
        )

        query = """
            mutation Upload($input: UploadGwflowFileMutationInput!) {
                uploadGwflowFile(input: $input) {
                    success
                    fileSize
                }
            }
        """

        file_id = to_global_id("GWFlowFileNode", gwflow_file.id)

        with TemporaryDirectory() as tmpdir, override_settings(GWFLOW_FILE_UPLOAD_DIR=tmpdir):
            # 1. MD5 mismatch test
            bad_file = io.BytesIO(b"wrong content")
            bad_file.name = "data.h5"

            bad_input = {"gwflowFileId": file_id, "file": None}
            bad_files = {"input.file": bad_file}

            res_bad = self.file_query(query, input_data=bad_input, files=bad_files)
            self.assertIsNotNone(res_bad.errors)
            self.assertIn("MD5 checksum mismatch", res_bad.errors[0]["message"])
            gwflow_file.refresh_from_db()
            self.assertFalse(gwflow_file.uploaded)

            # 2. Success upload test
            good_file = io.BytesIO(content)
            good_file.name = "data.h5"

            good_input = {"gwflowFileId": file_id, "file": None}
            good_files = {"input.file": good_file}

            res_good = self.file_query(query, input_data=good_input, files=good_files)
            self.assertIsNone(res_good.errors)
            self.assertTrue(res_good.data["uploadGwflowFile"]["success"])
            self.assertEqual(res_good.data["uploadGwflowFile"]["fileSize"], len(content))

            gwflow_file.refresh_from_db()
            self.assertTrue(gwflow_file.uploaded)
            self.assertEqual(gwflow_file.file_size, len(content))

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_link_and_unlink_bilby_job_to_gwflow(self):
        self._auth_as(self.ingest_user)

        gwflow_job = GWFlowJob.objects.create(sname="S230601link", user=self.ingest_user)
        ini_str1 = create_test_ini_string({"detectors": "['H1']", "label": "job_1"})
        ini_str2 = create_test_ini_string({"detectors": "['H1']", "label": "job_2"})
        bilby_job1 = BilbyJob.objects.create(user=self.normal_user, name="bilby_job_1", ini_string=ini_str1)
        bilby_job2 = BilbyJob.objects.create(user=self.normal_user, name="bilby_job_2", ini_string=ini_str2)

        query = """
            mutation Link($input: LinkBilbyJobToGwflowMutationInput!) {
                linkBilbyJobToGwflow(input: $input) {
                    success
                }
            }
        """

        job1_id = to_global_id("BilbyJobNode", bilby_job1.id)
        job2_id = to_global_id("BilbyJobNode", bilby_job2.id)

        with mock.patch("bilbyui.views.update_gwflow_child_job_ids") as mock_update_es:
            # 1. Link bilby_job1 to S230601link with uid "pe_1"
            input_data1 = {
                "jobId": job1_id,
                "sname": "S230601link",
                "analysisUid": "pe_1",
            }
            res1 = self.query(query, input_data=input_data1)
            self.assertIsNone(res1.errors)
            self.assertTrue(res1.data["linkBilbyJobToGwflow"]["success"])

            bilby_job1.refresh_from_db()
            self.assertEqual(bilby_job1.gwflow_job, gwflow_job)
            self.assertEqual(bilby_job1.gwflow_analysis_uid, "pe_1")
            mock_update_es.assert_called_once_with(gwflow_job)

        with mock.patch("bilbyui.views.update_gwflow_child_job_ids"):
            # 2. Try linking bilby_job2 to same sname and duplicate uid "pe_1" -> error
            input_data2 = {
                "jobId": job2_id,
                "sname": "S230601link",
                "analysisUid": "pe_1",
            }
            res2 = self.query(query, input_data=input_data2)
            self.assertIsNotNone(res2.errors)
            self.assertIn("already linked to another BilbyJob", res2.errors[0]["message"])

        with mock.patch("bilbyui.views.update_gwflow_child_job_ids") as mock_update_es_unlink:
            # 3. Unlink bilby_job1 (sname="")
            unlink_input = {
                "jobId": job1_id,
                "sname": "",
                "analysisUid": "",
            }
            res_unlink = self.query(query, input_data=unlink_input)
            self.assertIsNone(res_unlink.errors)

            bilby_job1.refresh_from_db()
            self.assertIsNone(bilby_job1.gwflow_job)
            self.assertEqual(bilby_job1.gwflow_analysis_uid, "")
            mock_update_es_unlink.assert_called_once_with(gwflow_job)

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_pending_files_query_ordering_and_select_related(self):
        self._auth_as(self.ingest_user)

        job_b = GWFlowJob.objects.create(sname="S230602b", user=self.ingest_user)
        job_a = GWFlowJob.objects.create(sname="S230601a", user=self.ingest_user)

        GWFlowFile.objects.create(
            job=job_b, analysis_uid="pe_1", path="b_path.h5", file_name="b_path.h5", uploaded=False
        )
        GWFlowFile.objects.create(
            job=job_a, analysis_uid="pe_2", path="a_path2.h5", file_name="a_path2.h5", uploaded=False
        )
        GWFlowFile.objects.create(
            job=job_a, analysis_uid="pe_1", path="a_path1.h5", file_name="a_path1.h5", uploaded=False
        )
        # Uploaded file should be excluded from pending
        GWFlowFile.objects.create(
            job=job_a, analysis_uid="pe_1", path="uploaded.h5", file_name="uploaded.h5", uploaded=True
        )

        query = """
            query {
                gwflowPendingFiles {
                    id
                    sname
                    analysisUid
                    path
                    fileName
                }
            }
        """

        with self.assertNumQueries(3):  # auth + pending files (with select_related join) + session
            res = self.query(query)
        self.assertIsNone(res.errors)

        pending = res.data["gwflowPendingFiles"]
        self.assertEqual(len(pending), 3)

        # Ordering by job.sname, analysis_uid, path
        self.assertEqual(pending[0]["sname"], "S230601a")
        self.assertEqual(pending[0]["analysisUid"], "pe_1")
        self.assertEqual(pending[0]["path"], "a_path1.h5")

        self.assertEqual(pending[1]["sname"], "S230601a")
        self.assertEqual(pending[1]["analysisUid"], "pe_2")
        self.assertEqual(pending[1]["path"], "a_path2.h5")

        self.assertEqual(pending[2]["sname"], "S230602b")
        self.assertEqual(pending[2]["analysisUid"], "pe_1")
        self.assertEqual(pending[2]["path"], "b_path.h5")

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_omit_field_preserves_prior_value(self):
        """Omitting schema_version / current_history_id on an update must not overwrite prior values."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result { sname created }
                }
            }
        """

        # Initial create with explicit values
        input_create = {
            "params": {
                "sname": "S230701omit",
                "schemaVersion": "v1",
                "currentHistoryId": "hist-001",
            }
        }
        res_create = self.query(query, input_data=input_create)
        self.assertIsNone(res_create.errors)
        self.assertTrue(res_create.data["upsertGwflowJob"]["result"]["created"])

        job = GWFlowJob.objects.get(sname="S230701omit")
        self.assertEqual(job.schema_version, "v1")
        self.assertEqual(job.current_history_id, "hist-001")

        # Update omitting both fields — prior values must be preserved
        input_update = {
            "params": {
                "sname": "S230701omit",
                "libraries": ["updated-lib"],
            }
        }
        res_update = self.query(query, input_data=input_update)
        self.assertIsNone(res_update.errors)
        self.assertFalse(res_update.data["upsertGwflowJob"]["result"]["created"])

        job.refresh_from_db()
        self.assertEqual(job.schema_version, "v1", "schema_version was silently reset — default_value bug not fixed")
        self.assertEqual(
            job.current_history_id, "hist-001", "current_history_id was silently reset — default_value bug not fixed"
        )
        self.assertEqual(job.libraries, ["updated-lib"])

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upload_gwflow_file_invalid_relay_id(self):
        """Relay-ID decode errors must return a GraphQL error, not a 500."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upload($input: UploadGwflowFileMutationInput!) {
                uploadGwflowFile(input: $input) {
                    success
                }
            }
        """

        bad_file = io.BytesIO(b"content")
        bad_file.name = "x.h5"
        with TemporaryDirectory() as tmpdir, override_settings(GWFLOW_FILE_UPLOAD_DIR=tmpdir):
            res = self.file_query(
                query,
                input_data={"gwflowFileId": "not-a-valid-relay-id", "file": None},
                files={"input.file": bad_file},
            )
        self.assertIsNotNone(res.errors)
        self.assertIn("Invalid gwflow_file_id", res.errors[0]["message"])

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_link_unknown_sname_raises_error(self):
        """Linking to a non-existent GWFlowJob sname must raise a descriptive GraphQL error."""
        self._auth_as(self.ingest_user)

        ini_str = create_test_ini_string({"detectors": "['H1']", "label": "job_x"})
        bilby_job = BilbyJob.objects.create(user=self.normal_user, name="bilby_job_x", ini_string=ini_str)

        query = """
            mutation Link($input: LinkBilbyJobToGwflowMutationInput!) {
                linkBilbyJobToGwflow(input: $input) { success }
            }
        """
        res = self.query(
            query,
            input_data={
                "jobId": to_global_id("BilbyJobNode", bilby_job.id),
                "sname": "NONEXISTENT_SNAME",
                "analysisUid": "pe_1",
            },
        )
        self.assertIsNotNone(res.errors)
        self.assertIn("NONEXISTENT_SNAME", res.errors[0]["message"])

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_link_invalid_job_id_raises_error(self):
        """An invalid/non-existent relay job_id must raise a descriptive GraphQL error."""
        self._auth_as(self.ingest_user)

        GWFlowJob.objects.create(sname="S230701link_err", user=self.ingest_user)

        query = """
            mutation Link($input: LinkBilbyJobToGwflowMutationInput!) {
                linkBilbyJobToGwflow(input: $input) { success }
            }
        """
        res = self.query(
            query,
            input_data={
                "jobId": to_global_id("BilbyJobNode", 99999),
                "sname": "S230701link_err",
                "analysisUid": "pe_1",
            },
        )
        self.assertIsNotNone(res.errors)
        self.assertIn("Invalid job_id", res.errors[0]["message"])

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_reconciliation_deletes_removed_files(self):
        """Create a job with 2 files, re-upsert with only 1 — dropped file must be deleted and listed in removedFiles."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                        created
                        filesPending { id path fileName }
                        removedFiles { id path fileName }
                    }
                }
            }
        """

        create_input = {
            "params": {
                "sname": "S230801recon1",
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/a.h5",
                        "fileName": "a.h5",
                        "fileSize": 100,
                        "md5Sum": "aaa",
                    },
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/b.h5",
                        "fileName": "b.h5",
                        "fileSize": 200,
                        "md5Sum": "bbb",
                    },
                ],
            }
        }

        with mock.patch("bilbyui.views.gwflow_elastic_search_update"):
            res_create = self.query(query, input_data=create_input)
            self.assertIsNone(res_create.errors)
            self.assertTrue(res_create.data["upsertGwflowJob"]["result"]["created"])

            a_file = GWFlowFile.objects.get(job__sname="S230801recon1", path="outdir/a.h5")
            b_file = GWFlowFile.objects.get(job__sname="S230801recon1", path="outdir/b.h5")

            # Re-upsert with only a.h5
            update_input = {
                "params": {
                    "sname": "S230801recon1",
                    "files": [
                        {
                            "analysisUid": "pe_1",
                            "path": "outdir/a.h5",
                            "fileName": "a.h5",
                            "fileSize": 100,
                            "md5Sum": "aaa",
                        },
                    ],
                }
            }
            res_update = self.query(query, input_data=update_input)
            self.assertIsNone(res_update.errors)
            result = res_update.data["upsertGwflowJob"]["result"]
            self.assertFalse(result["created"])

            # b.h5 row deleted, a.h5 remains
            self.assertFalse(GWFlowFile.objects.filter(id=b_file.id).exists())
            self.assertTrue(GWFlowFile.objects.filter(id=a_file.id).exists())

            # removedFiles contains b.h5's id
            removed_ids = [r["id"] for r in result["removedFiles"]]
            self.assertEqual(len(removed_ids), 1)
            self.assertEqual(removed_ids[0], to_global_id("GWFlowFileNode", b_file.id))
            self.assertEqual(result["removedFiles"][0]["path"], "outdir/b.h5")
            self.assertEqual(result["removedFiles"][0]["fileName"], "b.h5")

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_reconciliation_idempotent(self):
        """Re-upserting the exact same manifest must not delete anything; removedFiles must be empty."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                        removedFiles { id path fileName }
                    }
                }
            }
        """

        files_payload = [
            {
                "analysisUid": "pe_1",
                "path": "outdir/a.h5",
                "fileName": "a.h5",
                "fileSize": 100,
                "md5Sum": "aaa",
            },
            {
                "analysisUid": "pe_1",
                "path": "outdir/b.h5",
                "fileName": "b.h5",
                "fileSize": 200,
                "md5Sum": "bbb",
            },
        ]
        input_data = {"params": {"sname": "S230801recon_idem", "files": files_payload}}

        with mock.patch("bilbyui.views.gwflow_elastic_search_update"):
            res_create = self.query(query, input_data=input_data)
            self.assertIsNone(res_create.errors)

            a_file = GWFlowFile.objects.get(job__sname="S230801recon_idem", path="outdir/a.h5")
            b_file = GWFlowFile.objects.get(job__sname="S230801recon_idem", path="outdir/b.h5")

            # Re-upsert with the same manifest
            res_update = self.query(query, input_data=input_data)
            self.assertIsNone(res_update.errors)
            result = res_update.data["upsertGwflowJob"]["result"]
            self.assertEqual(result["removedFiles"], [])

            # Both rows still present
            self.assertTrue(GWFlowFile.objects.filter(id=a_file.id).exists())
            self.assertTrue(GWFlowFile.objects.filter(id=b_file.id).exists())
            self.assertEqual(GWFlowFile.objects.filter(job__sname="S230801recon_idem").count(), 2)

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_reconciliation_omitted_files_skips_reconcile(self):
        """Omitting `files` on update must not delete anything (prune-path regression test)."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                        filesPending { id path fileName }
                        removedFiles { id path fileName }
                    }
                }
            }
        """

        create_input = {
            "params": {
                "sname": "S230801recon_omit",
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/a.h5",
                        "fileName": "a.h5",
                        "fileSize": 100,
                        "md5Sum": "aaa",
                    },
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/b.h5",
                        "fileName": "b.h5",
                        "fileSize": 200,
                        "md5Sum": "bbb",
                    },
                ],
            }
        }

        with mock.patch("bilbyui.views.gwflow_elastic_search_update"):
            res_create = self.query(query, input_data=create_input)
            self.assertIsNone(res_create.errors)

            a_file = GWFlowFile.objects.get(job__sname="S230801recon_omit", path="outdir/a.h5")
            b_file = GWFlowFile.objects.get(job__sname="S230801recon_omit", path="outdir/b.h5")

            # Re-upsert omitting `files` (simulates A11 prune path).
            omit_input = {
                "params": {
                    "sname": "S230801recon_omit",
                    "isPruned": True,
                }
            }
            res_update = self.query(query, input_data=omit_input)
            self.assertIsNone(res_update.errors)
            result = res_update.data["upsertGwflowJob"]["result"]

            # No reconciliation
            self.assertEqual(result["removedFiles"], [])
            self.assertTrue(GWFlowFile.objects.filter(id=a_file.id).exists())
            self.assertTrue(GWFlowFile.objects.filter(id=b_file.id).exists())
            self.assertEqual(GWFlowFile.objects.filter(job__sname="S230801recon_omit").count(), 2)

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_reconciliation_empty_files_deletes_all(self):
        """Re-upsert with files=[] must delete all existing files; all ids must appear in removedFiles."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                        filesPending { id path fileName }
                        removedFiles { id path fileName }
                    }
                }
            }
        """

        create_input = {
            "params": {
                "sname": "S230801recon_empty",
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/a.h5",
                        "fileName": "a.h5",
                        "fileSize": 100,
                        "md5Sum": "aaa",
                    },
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/b.h5",
                        "fileName": "b.h5",
                        "fileSize": 200,
                        "md5Sum": "bbb",
                    },
                ],
            }
        }

        with mock.patch("bilbyui.views.gwflow_elastic_search_update"):
            res_create = self.query(query, input_data=create_input)
            self.assertIsNone(res_create.errors)

            a_file = GWFlowFile.objects.get(job__sname="S230801recon_empty", path="outdir/a.h5")
            b_file = GWFlowFile.objects.get(job__sname="S230801recon_empty", path="outdir/b.h5")

            # Re-upsert with files=[]
            empty_input = {"params": {"sname": "S230801recon_empty", "files": []}}
            res_update = self.query(query, input_data=empty_input)
            self.assertIsNone(res_update.errors)
            result = res_update.data["upsertGwflowJob"]["result"]

            # Both deleted
            self.assertFalse(GWFlowFile.objects.filter(id=a_file.id).exists())
            self.assertFalse(GWFlowFile.objects.filter(id=b_file.id).exists())
            self.assertEqual(GWFlowFile.objects.filter(job__sname="S230801recon_empty").count(), 0)

            # Both ids in removedFiles
            removed_ids = sorted(r["id"] for r in result["removedFiles"])
            self.assertEqual(
                removed_ids,
                sorted([to_global_id("GWFlowFileNode", a_file.id), to_global_id("GWFlowFileNode", b_file.id)]),
            )
            removed_paths = sorted(r["path"] for r in result["removedFiles"])
            self.assertEqual(removed_paths, ["outdir/a.h5", "outdir/b.h5"])

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_reconciliation_md5_change_keeps_record(self):
        """Same (analysis_uid, path) with a changed md5 must update the row, NOT delete it."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                        filesPending { id path fileName }
                        removedFiles { id path fileName }
                    }
                }
            }
        """

        create_input = {
            "params": {
                "sname": "S230801recon_md5",
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/a.h5",
                        "fileName": "a.h5",
                        "fileSize": 100,
                        "md5Sum": "oldmd5",
                    },
                ],
            }
        }

        with mock.patch("bilbyui.views.gwflow_elastic_search_update"):
            res_create = self.query(query, input_data=create_input)
            self.assertIsNone(res_create.errors)

            f_obj = GWFlowFile.objects.get(job__sname="S230801recon_md5", path="outdir/a.h5")
            # Simulate file already mirrored successfully; md5 change should reset uploaded=False.
            f_obj.uploaded = True
            f_obj.save()

            # Re-upsert same path with a different md5
            update_input = {
                "params": {
                    "sname": "S230801recon_md5",
                    "files": [
                        {
                            "analysisUid": "pe_1",
                            "path": "outdir/a.h5",
                            "fileName": "a.h5",
                            "fileSize": 100,
                            "md5Sum": "newmd5",
                        },
                    ],
                }
            }
            res_update = self.query(query, input_data=update_input)
            self.assertIsNone(res_update.errors)
            result = res_update.data["upsertGwflowJob"]["result"]

            # Row remains, NOT in removedFiles
            f_obj.refresh_from_db()
            self.assertTrue(GWFlowFile.objects.filter(id=f_obj.id).exists())
            self.assertEqual(f_obj.md5_sum, "newmd5")
            self.assertFalse(f_obj.uploaded)
            removed_ids = [r["id"] for r in result["removedFiles"]]
            self.assertNotIn(to_global_id("GWFlowFileNode", f_obj.id), removed_ids)

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_reconciliation_deletes_mirrored_file_from_disk(self):
        """Dropping a file from the manifest must delete its mirrored file and .part sibling from disk."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                        removedFiles { id path fileName }
                    }
                }
            }
        """

        create_input = {
            "params": {
                "sname": "S230801recon_disk",
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/a.h5",
                        "fileName": "a.h5",
                        "fileSize": 100,
                        "md5Sum": "aaa",
                    },
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/b.h5",
                        "fileName": "b.h5",
                        "fileSize": 200,
                        "md5Sum": "bbb",
                    },
                ],
            }
        }

        with TemporaryDirectory() as tmpdir, override_settings(GWFLOW_FILE_UPLOAD_DIR=tmpdir):
            with mock.patch("bilbyui.views.gwflow_elastic_search_update"):
                res_create = self.query(query, input_data=create_input)
                self.assertIsNone(res_create.errors)

                job = GWFlowJob.objects.get(sname="S230801recon_disk")
                a_file = GWFlowFile.objects.get(job__sname="S230801recon_disk", path="outdir/a.h5")
                b_file = GWFlowFile.objects.get(job__sname="S230801recon_disk", path="outdir/b.h5")

                # Simulate both files mirrored on disk, b.h5 with an interrupted .part sibling.
                for f in (a_file, b_file):
                    file_path = Path(tmpdir) / str(job.id) / str(f.id)
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(b"mirrored content")
                a_disk = Path(tmpdir) / str(job.id) / str(a_file.id)
                b_disk = Path(tmpdir) / str(job.id) / str(b_file.id)
                b_part = Path(tmpdir) / str(job.id) / f"{b_file.id}.part"
                b_part.write_bytes(b"partial content")
                self.assertTrue(a_disk.exists())
                self.assertTrue(b_disk.exists())
                self.assertTrue(b_part.exists())

                # Re-upsert with only a.h5 -> b.h5 dropped.
                update_input = {
                    "params": {
                        "sname": "S230801recon_disk",
                        "files": [
                            {
                                "analysisUid": "pe_1",
                                "path": "outdir/a.h5",
                                "fileName": "a.h5",
                                "fileSize": 100,
                                "md5Sum": "aaa",
                            },
                        ],
                    }
                }
                res_update = self.query(query, input_data=update_input)
                self.assertIsNone(res_update.errors)
                result = res_update.data["upsertGwflowJob"]["result"]

                # Record deleted and listed in removedFiles.
                self.assertFalse(GWFlowFile.objects.filter(id=b_file.id).exists())
                self.assertTrue(GWFlowFile.objects.filter(id=a_file.id).exists())
                removed_ids = [r["id"] for r in result["removedFiles"]]
                self.assertEqual(removed_ids, [to_global_id("GWFlowFileNode", b_file.id)])

                # Mirrored file and .part sibling removed from disk; kept file untouched.
                self.assertFalse(b_disk.exists())
                self.assertFalse(b_part.exists())
                self.assertTrue(a_disk.exists())
                self.assertEqual(a_disk.read_bytes(), b"mirrored content")

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_upsert_reconciliation_delete_missing_disk_file_no_error(self):
        """Deleting a record whose mirrored file is already absent from disk must not error."""
        self._auth_as(self.ingest_user)

        query = """
            mutation Upsert($input: UpsertGwflowJobMutationInput!) {
                upsertGwflowJob(input: $input) {
                    result {
                        sname
                        removedFiles { id path fileName }
                    }
                }
            }
        """

        create_input = {
            "params": {
                "sname": "S230801recon_missing",
                "files": [
                    {
                        "analysisUid": "pe_1",
                        "path": "outdir/a.h5",
                        "fileName": "a.h5",
                        "fileSize": 100,
                        "md5Sum": "aaa",
                    },
                ],
            }
        }

        with TemporaryDirectory() as tmpdir, override_settings(GWFLOW_FILE_UPLOAD_DIR=tmpdir):
            with mock.patch("bilbyui.views.gwflow_elastic_search_update"):
                res_create = self.query(query, input_data=create_input)
                self.assertIsNone(res_create.errors)

                a_file = GWFlowFile.objects.get(job__sname="S230801recon_missing", path="outdir/a.h5")
                job = GWFlowJob.objects.get(sname="S230801recon_missing")

                # No file was ever mirrored to disk.
                disk = Path(tmpdir) / str(job.id) / str(a_file.id)
                self.assertFalse(disk.exists())

                # Dropping the file must not raise on the missing disk file.
                update_input = {"params": {"sname": "S230801recon_missing", "files": []}}
                res_update = self.query(query, input_data=update_input)
                self.assertIsNone(res_update.errors)
                result = res_update.data["upsertGwflowJob"]["result"]

                self.assertFalse(GWFlowFile.objects.filter(id=a_file.id).exists())
                self.assertEqual(len(result["removedFiles"]), 1)
                self.assertFalse(disk.exists())
