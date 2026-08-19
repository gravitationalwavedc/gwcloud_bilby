import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gwflow_ingest
import settings
import state
from tests.base import GWFlowTestBase


def _bilby_pe_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5"):
    return {
        "uid": uid,
        "inference_software": "BILBY",
        "config_file": {"path": config_path, "file_size": 100},
        "result_file": {"path": result_path, "file_size": 1000},
        "pesummary_result_file": None,
    }


def _superevent_detail(sname="S260101a", analyses=None, files=None):
    if analyses is None:
        analyses = [_bilby_pe_analysis()]
    return {
        "sname": sname,
        "raw_payload": {"sname": sname, "event": "GW260101"},
        "libraries": [{"name": "bilby"}],
        "pe": {"results": analyses},
        "files": files or [],
    }


class TestKillStateRecovery(GWFlowTestBase):
    @patch("gwflow_ingest.fetch_to_staging")
    @patch("gwflow_ingest.PortalClient")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_killed_between_metadata_and_bilby_phase_recovers_bilby_jobs(
        self, mock_gwc_cls, mock_jc_cls, mock_portal_cls, mock_fetch
    ):
        """Regression test: when killed after metadata phase (watermark advanced)

        before phase_bilby_children runs, the next run with an empty metadata delta
        must still process and link the Bilby jobs for the changed superevent.
        """
        sname = "S260101a"
        detail = _superevent_detail(sname=sname, analyses=[_bilby_pe_analysis(uid="uid1")])

        mock_gwc = MagicMock()
        mock_jc = MagicMock()
        mock_portal = MagicMock()

        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = mock_jc
        mock_portal_cls.return_value = mock_portal

        uploaded_job = MagicMock()
        uploaded_job.id = "bilby-job-123"
        mock_gwc.upload_job_archive.return_value = uploaded_job

        # Initially no linked jobs in GWCloud
        gwc_gwflow_job = MagicMock()
        gwc_gwflow_job.bilby_jobs = []
        mock_gwc.get_gwflow_job.return_value = gwc_gwflow_job
        mock_gwc.get_gwflow_job_list.return_value = []
        mock_gwc.get_gwflow_pending_files.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "gwflow.db"
            staging_dir = Path(tmpdir) / "staging"
            staging_dir.mkdir()

            ini_file = Path(tmpdir) / "config.ini"
            ini_file.write_text("label = old\n")
            res_file = Path(tmpdir) / "result.h5"
            res_file.write_bytes(b"result-data")
            mock_fetch.side_effect = [ini_file, res_file]

            with (
                patch.object(settings, "DB_PATH", str(db_file)),
                patch.object(settings, "STAGING_DIR", str(staging_dir)),
                patch.object(settings, "GWCLOUD_TOKEN", "token"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "secret"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "bundle"),
            ):
                # --- RUN 1: Metadata phase runs and updates watermark, but script is killed before bilby phase ---
                mock_portal.iter_changed.return_value = [
                    {
                        "sname": sname,
                        "commit_timestamp": "2026-01-01T12:00:00Z",
                        "schema_version": "1.0",
                        "commit_sha": "sha-run1",
                    }
                ]
                mock_portal.get_superevent.return_value = detail
                mock_portal.iter_current_snames.return_value = [sname]

                con = gwflow_ingest.sqlite3.connect(settings.DB_PATH)
                con.row_factory = gwflow_ingest.sqlite3.Row
                gwflow_ingest.state.init_db(con)

                # Execute phase_metadata only (simulating kill during file mirror / before bilby children)
                gwflow_ingest.phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=con)
                con.close()

                # Verify metadata upsert happened and watermark advanced
                mock_gwc.upsert_gwflow_job.assert_called_once()
                self.assertEqual(mock_gwc.upload_job_archive.call_count, 0)

                # --- RUN 2: Next invocation. Portal delta is empty because watermark is current ---
                mock_portal.iter_changed.return_value = []
                mock_portal.get_superevent.return_value = detail
                mock_portal.iter_current_snames.return_value = [sname]

                res = gwflow_ingest.run([])
                self.assertEqual(res, 0)

                # Assert that Bilby child was picked up, uploaded, and linked in Run 2
                self.assertEqual(mock_gwc.upload_job_archive.call_count, 1)
                mock_gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded_job.id, sname, "uid1")

                # Verify that SQLite job_errors state was cleaned up
                con2 = gwflow_ingest.sqlite3.connect(settings.DB_PATH)
                con2.row_factory = gwflow_ingest.sqlite3.Row
                cur2 = con2.cursor()
                self.assertEqual(state.get_failure_count(cur2, f"bilby:{sname}"), 0)
                self.assertEqual(state.get_failure_count(cur2, f"bilby:{sname}/uid1"), 0)
                con2.close()

    @patch("gwflow_ingest.fetch_to_staging")
    @patch("gwflow_ingest.PortalClient")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_killed_during_file_mirror_resumes_file_uploads_and_bilby_jobs(
        self, mock_gwc_cls, mock_jc_cls, mock_portal_cls, mock_fetch
    ):
        """When killed during phase_file_mirror, the next run must finish uploading remaining

        pending files AND process the Bilby children.
        """
        sname = "S260101a"
        detail = _superevent_detail(sname=sname, analyses=[_bilby_pe_analysis(uid="uid1")])

        mock_gwc = MagicMock()
        mock_jc = MagicMock()
        mock_portal = MagicMock()

        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = mock_jc
        mock_portal_cls.return_value = mock_portal

        uploaded_job = MagicMock()
        uploaded_job.id = "bilby-job-123"
        mock_gwc.upload_job_archive.return_value = uploaded_job

        gwc_gwflow_job = MagicMock()
        gwc_gwflow_job.bilby_jobs = []
        mock_gwc.get_gwflow_job.return_value = gwc_gwflow_job
        mock_gwc.get_gwflow_job_list.return_value = []

        pending_f1 = SimpleNamespace(
            id="f1", sname=sname, analysis_uid="", path="/data/f1.h5", file_name="f1.h5", md5_sum=""
        )
        pending_f2 = SimpleNamespace(
            id="f2", sname=sname, analysis_uid="", path="/data/f2.h5", file_name="f2.h5", md5_sum=""
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "gwflow.db"
            staging_dir = Path(tmpdir) / "staging"
            staging_dir.mkdir()

            staged_f1 = Path(tmpdir) / "staged_f1.h5"
            staged_f1.write_bytes(b"f1-data")
            staged_f2 = Path(tmpdir) / "staged_f2.h5"
            staged_f2.write_bytes(b"f2-data")
            ini_file = Path(tmpdir) / "config.ini"
            ini_file.write_text("label = old\n")
            res_file = Path(tmpdir) / "result.h5"
            res_file.write_bytes(b"result-data")

            with (
                patch.object(settings, "DB_PATH", str(db_file)),
                patch.object(settings, "STAGING_DIR", str(staging_dir)),
                patch.object(settings, "GWCLOUD_TOKEN", "token"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "secret"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "bundle"),
            ):
                # --- RUN 1: Metadata runs, File Mirror uploads f1 then crashes/kills on f2 ---
                mock_portal.iter_changed.return_value = [
                    {
                        "sname": sname,
                        "commit_timestamp": "2026-01-01T12:00:00Z",
                        "schema_version": "1.0",
                        "commit_sha": "sha-run1",
                    }
                ]
                mock_portal.get_superevent.return_value = detail
                mock_portal.iter_current_snames.return_value = [sname]
                mock_gwc.get_gwflow_pending_files.return_value = [pending_f1, pending_f2]
                mock_fetch.side_effect = [staged_f1, RuntimeError("Network killed mid-mirror")]

                con = gwflow_ingest.sqlite3.connect(settings.DB_PATH)
                con.row_factory = gwflow_ingest.sqlite3.Row
                gwflow_ingest.state.init_db(con)

                gwflow_ingest.phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=con)
                # phase_file_mirror runs and f2 fails
                gwflow_ingest.phase_file_mirror(jc=mock_jc, gwc_client=mock_gwc, con=con)
                # Script is killed before phase_bilby_children
                con.close()

                mock_gwc.upload_gwflow_file.assert_called_once_with("f1", staged_f1)
                self.assertEqual(mock_gwc.upload_job_archive.call_count, 0)

                # --- RUN 2: Next run. Only f2 remains pending in GWCloud, metadata delta is empty ---
                mock_portal.iter_changed.return_value = []
                mock_gwc.get_gwflow_pending_files.return_value = [pending_f2]
                mock_fetch.side_effect = [staged_f2, ini_file, res_file]

                res = gwflow_ingest.run([])
                self.assertEqual(res, 0)

                # Verify f2 uploaded
                mock_gwc.upload_gwflow_file.assert_called_with("f2", staged_f2)
                # Verify Bilby job created and linked
                self.assertEqual(mock_gwc.upload_job_archive.call_count, 1)
                mock_gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded_job.id, sname, "uid1")

    @patch("gwflow_ingest.fetch_to_staging")
    @patch("gwflow_ingest.PortalClient")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_killed_after_archive_upload_uses_job_ref_to_avoid_duplicate(
        self, mock_gwc_cls, mock_jc_cls, mock_portal_cls, mock_fetch
    ):
        """When killed after job archive is uploaded but before linking completes,

        the next run must use the stored job_ref to link without re-uploading.
        """
        sname = "S260101a"
        detail = _superevent_detail(sname=sname, analyses=[_bilby_pe_analysis(uid="uid1")])

        mock_gwc = MagicMock()
        mock_jc = MagicMock()
        mock_portal = MagicMock()

        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = mock_jc
        mock_portal_cls.return_value = mock_portal

        uploaded_job = MagicMock()
        uploaded_job.id = "bilby-job-orphan-999"
        mock_gwc.upload_job_archive.return_value = uploaded_job

        gwc_gwflow_job = MagicMock()
        gwc_gwflow_job.bilby_jobs = []
        mock_gwc.get_gwflow_job.return_value = gwc_gwflow_job
        mock_gwc.get_gwflow_job_list.return_value = []
        mock_gwc.get_gwflow_pending_files.return_value = []

        # Make linking fail in Run 1 (simulating failure/kill during link mutation)
        mock_gwc.link_bilby_job_to_gwflow.side_effect = [RuntimeError("GraphQL timeout during link"), None]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "gwflow.db"
            staging_dir = Path(tmpdir) / "staging"
            staging_dir.mkdir()

            ini_file = Path(tmpdir) / "config.ini"
            ini_file.write_text("label = old\n")
            res_file = Path(tmpdir) / "result.h5"
            res_file.write_bytes(b"result-data")
            mock_fetch.side_effect = [ini_file, res_file]

            with (
                patch.object(settings, "DB_PATH", str(db_file)),
                patch.object(settings, "STAGING_DIR", str(staging_dir)),
                patch.object(settings, "GWCLOUD_TOKEN", "token"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "secret"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "bundle"),
            ):
                mock_portal.iter_changed.return_value = [
                    {
                        "sname": sname,
                        "commit_timestamp": "2026-01-01T12:00:00Z",
                        "schema_version": "1.0",
                        "commit_sha": "sha-run1",
                    }
                ]
                mock_portal.get_superevent.return_value = detail
                mock_portal.iter_current_snames.return_value = [sname]

                # Run 1: Fails at link step
                gwflow_ingest.run([])

                self.assertEqual(mock_gwc.upload_job_archive.call_count, 1)
                self.assertEqual(mock_fetch.call_count, 2)

                # Run 2: Next run. Should link using job_ref without calling fetch or upload
                mock_portal.iter_changed.return_value = []
                gwflow_ingest.run([])

                # upload_job_archive and fetch must NOT have been called in Run 2
                self.assertEqual(mock_gwc.upload_job_archive.call_count, 1)
                self.assertEqual(mock_fetch.call_count, 2)
                mock_gwc.link_bilby_job_to_gwflow.assert_called_with("bilby-job-orphan-999", sname, "uid1")

    @patch("gwflow_ingest.fetch_to_staging")
    @patch("gwflow_ingest.PortalClient")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_multiple_superevents_killed_after_metadata_recovers_all(
        self, mock_gwc_cls, mock_jc_cls, mock_portal_cls, mock_fetch
    ):
        """When multiple superevents are upserted in metadata phase and process is killed,

        all of them are recovered and have their Bilby jobs processed on the next run.
        """
        sname1 = "S260101a"
        sname2 = "S260102b"
        detail1 = _superevent_detail(sname=sname1, analyses=[_bilby_pe_analysis(uid="uid-a")])
        detail2 = _superevent_detail(sname=sname2, analyses=[_bilby_pe_analysis(uid="uid-b")])

        mock_gwc = MagicMock()
        mock_jc = MagicMock()
        mock_portal = MagicMock()

        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = mock_jc
        mock_portal_cls.return_value = mock_portal

        uploaded_job_a = MagicMock(id="job-a")
        uploaded_job_b = MagicMock(id="job-b")
        mock_gwc.upload_job_archive.side_effect = [uploaded_job_a, uploaded_job_b]

        mock_gwc.get_gwflow_job.return_value = MagicMock(bilby_jobs=[])
        mock_gwc.get_gwflow_job_list.return_value = []
        mock_gwc.get_gwflow_pending_files.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "gwflow.db"
            staging_dir = Path(tmpdir) / "staging"
            staging_dir.mkdir()

            ini_file = Path(tmpdir) / "config.ini"
            ini_file.write_text("label = old\n")
            res_file = Path(tmpdir) / "result.h5"
            res_file.write_bytes(b"result-data")
            mock_fetch.side_effect = [ini_file, res_file, ini_file, res_file]

            with (
                patch.object(settings, "DB_PATH", str(db_file)),
                patch.object(settings, "STAGING_DIR", str(staging_dir)),
                patch.object(settings, "GWCLOUD_TOKEN", "token"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "secret"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "bundle"),
            ):
                # Run 1: Metadata phase processes both S1 and S2, then kills
                mock_portal.iter_changed.return_value = [
                    {
                        "sname": sname1,
                        "commit_timestamp": "2026-01-01T10:00:00Z",
                        "schema_version": "1.0",
                        "commit_sha": "sha1",
                    },
                    {
                        "sname": sname2,
                        "commit_timestamp": "2026-01-02T10:00:00Z",
                        "schema_version": "1.0",
                        "commit_sha": "sha2",
                    },
                ]
                mock_portal.get_superevent.side_effect = lambda s: detail1 if s == sname1 else detail2
                mock_portal.iter_current_snames.return_value = [sname1, sname2]

                con = gwflow_ingest.sqlite3.connect(settings.DB_PATH)
                con.row_factory = gwflow_ingest.sqlite3.Row
                gwflow_ingest.state.init_db(con)
                gwflow_ingest.phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=con)
                con.close()

                # Run 2: Full run with empty metadata delta
                mock_portal.iter_changed.return_value = []
                res = gwflow_ingest.run([])
                self.assertEqual(res, 0)

                # Verify both jobs uploaded and linked
                self.assertEqual(mock_gwc.upload_job_archive.call_count, 2)
                mock_gwc.link_bilby_job_to_gwflow.assert_any_call("job-a", sname1, "uid-a")
                mock_gwc.link_bilby_job_to_gwflow.assert_any_call("job-b", sname2, "uid-b")

    @patch("gwflow_ingest.fetch_to_staging")
    @patch("gwflow_ingest.PortalClient")
    @patch("gwflow_ingest.JobControllerClient")
    @patch("gwflow_ingest.GWCloud")
    def test_superevent_without_bilby_pe_cleans_pending_marker_on_resume(
        self, mock_gwc_cls, mock_jc_cls, mock_portal_cls, mock_fetch
    ):
        """A superevent that has no Bilby PE analyses is cleanly processed and clears its pending marker."""
        sname = "S_NO_BILBY"
        detail = _superevent_detail(sname=sname, analyses=[])

        mock_gwc = MagicMock()
        mock_jc = MagicMock()
        mock_portal = MagicMock()

        mock_gwc_cls.return_value = mock_gwc
        mock_jc_cls.return_value = mock_jc
        mock_portal_cls.return_value = mock_portal

        mock_gwc.get_gwflow_job.return_value = MagicMock(bilby_jobs=[])
        mock_gwc.get_gwflow_job_list.return_value = []
        mock_gwc.get_gwflow_pending_files.return_value = []

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "gwflow.db"
            staging_dir = Path(tmpdir) / "staging"
            staging_dir.mkdir()

            with (
                patch.object(settings, "DB_PATH", str(db_file)),
                patch.object(settings, "STAGING_DIR", str(staging_dir)),
                patch.object(settings, "GWCLOUD_TOKEN", "token"),
                patch.object(settings, "JOB_CONTROLLER_JWT_SECRET", "secret"),
                patch.object(settings, "JOB_CONTROLLER_BUNDLE", "bundle"),
            ):
                # Run 1: Metadata phase runs and kills
                mock_portal.iter_changed.return_value = [
                    {
                        "sname": sname,
                        "commit_timestamp": "2026-01-01T10:00:00Z",
                        "schema_version": "1.0",
                        "commit_sha": "sha1",
                    }
                ]
                mock_portal.get_superevent.return_value = detail
                mock_portal.iter_current_snames.return_value = [sname]

                con = gwflow_ingest.sqlite3.connect(settings.DB_PATH)
                con.row_factory = gwflow_ingest.sqlite3.Row
                gwflow_ingest.state.init_db(con)
                gwflow_ingest.phase_metadata(portal_client=mock_portal, gwc_client=mock_gwc, con=con)
                con.close()

                # Run 2: Full run
                mock_portal.iter_changed.return_value = []
                res = gwflow_ingest.run([])
                self.assertEqual(res, 0)

                mock_gwc.upload_job_archive.assert_not_called()
                con2 = gwflow_ingest.sqlite3.connect(settings.DB_PATH)
                con2.row_factory = gwflow_ingest.sqlite3.Row
                cur2 = con2.cursor()
                self.assertEqual(state.get_failure_count(cur2, f"bilby:{sname}"), 0)
                con2.close()


if __name__ == "__main__":
    unittest.main()
