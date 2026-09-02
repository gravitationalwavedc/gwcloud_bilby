import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    from tests.base import GWFlowTestBase
except ImportError:
    from base import GWFlowTestBase

import settings
import state
from fetch import MD5Mismatch
from gwflow_ingest import _with_normalized_uid, phase_file_mirror
from job_controller import ClusterOffline, FetchError


def make_rec(file_id="f1", sname="S1", analysis_uid="uid1", path="/data/foo.h5", md5="abc"):
    return {
        "id": file_id,
        "sname": sname,
        "analysis_uid": analysis_uid,
        "path": path,
        "file_name": path.rsplit("/", 1)[-1],
        "md5_sum": md5,
    }


def key_for(sname="S1", analysis_uid="uid1", path="/data/foo.h5"):
    return f"{sname}/{analysis_uid or ''}/{path}"


def make_staged(tmpdir, name="staged.h5", content=b"file content"):
    staged = Path(tmpdir) / name
    staged.write_bytes(content)
    return staged


class TestFileMirrorPhase(GWFlowTestBase):
    def test_clients_not_wired_skips_without_calling_anything(self):
        gwc = MagicMock()
        jc = MagicMock()

        phase_file_mirror(jc=None, gwc_client=gwc, con=self.con)
        gwc.get_gwflow_pending_files.assert_not_called()

        phase_file_mirror(jc=jc, gwc_client=None, con=self.con)
        jc.create_file_downloads.assert_not_called()
        gwc.upload_gwflow_file.assert_not_called()

        phase_file_mirror(jc=None, gwc_client=None, con=self.con)

    def test_happy_path_uploads_and_cleans_staging(self):
        rec = SimpleNamespace(**make_rec())
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [rec]
        jc = MagicMock()
        cur = self.con.cursor()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged = make_staged(tmpdir)
            with patch("gwflow_ingest.fetch_to_staging", return_value=staged) as mock_fetch:
                phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)
            self.assertFalse(staged.exists())

        gwc.upload_gwflow_file.assert_called_once_with("f1", staged)
        mock_fetch.assert_called_once()
        self.assertEqual(mock_fetch.call_args.args[0], jc)
        self.assertEqual(mock_fetch.call_args.args[1].analysis_uid, "uid1")
        self.assertEqual(state.get_failure_count(cur, key_for()), 0)

    def test_md5_mismatch_records_failure_no_upload(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec()]
        jc = MagicMock()
        cur = self.con.cursor()

        with patch("gwflow_ingest.fetch_to_staging", side_effect=MD5Mismatch("bad md5")):
            phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)

        gwc.upload_gwflow_file.assert_not_called()
        self.assertEqual(state.get_failure_count(cur, key_for()), 1)

    def test_fetch_error_records_failure_no_upload(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec()]
        jc = MagicMock()
        cur = self.con.cursor()

        with patch("gwflow_ingest.fetch_to_staging", side_effect=FetchError("download failed")):
            phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)

        gwc.upload_gwflow_file.assert_not_called()
        self.assertEqual(state.get_failure_count(cur, key_for()), 1)

    def test_cluster_offline_defers_remaining_without_consuming_retries(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec(file_id="f1"), make_rec(file_id="f2")]
        jc = MagicMock()
        cur = self.con.cursor()

        with patch("gwflow_ingest.fetch_to_staging", side_effect=[ClusterOffline("offline")]) as mock_fetch:
            phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)

        self.assertEqual(mock_fetch.call_count, 1)
        gwc.upload_gwflow_file.assert_not_called()
        self.assertEqual(state.get_failure_count(cur, key_for()), 0)

    def test_unexpected_exception_records_failure_and_continues(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [
            make_rec(file_id="f1", path="/data/foo1.h5"),
            make_rec(file_id="f2", path="/data/foo2.h5"),
        ]
        jc = MagicMock()
        cur = self.con.cursor()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged = make_staged(tmpdir, "s2.h5")
            with patch("gwflow_ingest.fetch_to_staging", side_effect=[KeyError("boom"), staged]):
                phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)
            self.assertFalse(staged.exists())

        gwc.upload_gwflow_file.assert_called_once_with("f2", staged)
        self.assertEqual(state.get_failure_count(cur, key_for(path="/data/foo1.h5")), 1)
        self.assertEqual(state.get_failure_count(cur, key_for(path="/data/foo2.h5")), 0)

    def test_max_files_per_run_cap(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec(file_id=f"f{i}") for i in range(3)]
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged_files = [make_staged(tmpdir, f"s{i}.h5") for i in range(3)]
            with (
                patch.object(settings, "MAX_FILES_PER_RUN", 2),
                patch("gwflow_ingest.fetch_to_staging", side_effect=staged_files),
            ):
                phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)

        self.assertEqual(gwc.upload_gwflow_file.call_count, 2)

    def test_max_bytes_per_run_cap(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec(file_id=f"f{i}") for i in range(3)]
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged_files = [make_staged(tmpdir, f"s{i}.h5", content=b"x" * 10) for i in range(3)]
            with (
                patch.object(settings, "MAX_BYTES_PER_RUN", 10),
                patch("gwflow_ingest.fetch_to_staging", side_effect=staged_files),
            ):
                phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)

        self.assertEqual(gwc.upload_gwflow_file.call_count, 1)

    def test_backfill_bypasses_caps(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec(file_id=f"f{i}") for i in range(3)]
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged_files = [make_staged(tmpdir, f"s{i}.h5") for i in range(3)]
            with (
                patch.object(settings, "MAX_FILES_PER_RUN", 2),
                patch.object(settings, "BACKFILL", True),
                patch("gwflow_ingest.fetch_to_staging", side_effect=staged_files),
            ):
                phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)

        self.assertEqual(gwc.upload_gwflow_file.call_count, 3)

    def test_over_retry_keys_skipped(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec()]
        jc = MagicMock()
        cur = self.con.cursor()
        key = key_for()
        for _ in range(settings.MAX_RETRY_ATTEMPTS):
            state.record_failure(self.con, cur, key, "earlier failure")

        with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
            phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_gwflow_file.assert_not_called()

    def test_analysis_uid_none_uses_empty_key_and_uploads(self):
        rec = make_rec(analysis_uid=None)
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [rec]
        jc = MagicMock()
        cur = self.con.cursor()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged = make_staged(tmpdir)
            with patch("gwflow_ingest.fetch_to_staging", return_value=staged) as mock_fetch:
                phase_file_mirror(jc=jc, gwc_client=gwc, con=self.con)
            self.assertFalse(staged.exists())

        gwc.upload_gwflow_file.assert_called_once_with("f1", staged)
        self.assertEqual(mock_fetch.call_args.args[1]["analysis_uid"], "")
        self.assertEqual(state.get_failure_count(cur, key_for(analysis_uid=None)), 0)

    def test_con_none_creates_connection(self):
        gwc = MagicMock()
        gwc.get_gwflow_pending_files.return_value = [make_rec()]
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            staged = make_staged(tmpdir)
            with patch("gwflow_ingest.fetch_to_staging", return_value=staged):
                phase_file_mirror(jc=jc, gwc_client=gwc, con=None)

        gwc.upload_gwflow_file.assert_called_once_with("f1", staged)


class TestWithNormalizedUid(GWFlowTestBase):
    def test_dict_input_sets_analysis_uid(self):
        rec = make_rec(analysis_uid="old")
        out = _with_normalized_uid(rec, "new-uid")
        self.assertEqual(out["analysis_uid"], "new-uid")

    def test_object_input_sets_analysis_uid(self):
        rec = SimpleNamespace(**make_rec(analysis_uid="old"))
        out = _with_normalized_uid(rec, "new-uid")
        self.assertEqual(out.analysis_uid, "new-uid")

    def test_returns_shallow_copy_without_mutating_original(self):
        rec = make_rec(analysis_uid="old")
        out = _with_normalized_uid(rec, "new-uid")
        self.assertIsNot(out, rec)
        self.assertEqual(rec["analysis_uid"], "old")
        self.assertEqual(out["analysis_uid"], "new-uid")

    def test_object_input_does_not_mutate_original(self):
        rec = SimpleNamespace(**make_rec(analysis_uid="old"))
        out = _with_normalized_uid(rec, "new-uid")
        self.assertIsNot(out, rec)
        self.assertEqual(rec.analysis_uid, "old")
        self.assertEqual(out.analysis_uid, "new-uid")


if __name__ == "__main__":
    unittest.main()
