import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from gwdc_python.exceptions import GWDCUnknownException

try:
    from tests.base import GWFlowTestBase
except ImportError:
    from base import GWFlowTestBase

import settings
import state
from bilby_children import StageError, resolve_missing_path, stage_supporting_files
from gwflow_ingest import phase_bilby_children
from job_controller import FetchError

try:
    from tests.test_bilby_children import _bilby_analysis, _bilby_detail, _make_gwc, _write_fetch_files
except ImportError:
    from test_bilby_children import _bilby_analysis, _bilby_detail, _make_gwc, _write_fetch_files


class TestResolveMissingPath(unittest.TestCase):
    def test_absolute_path_returned_as_is(self):
        self.assertEqual(resolve_missing_path("/calib/cal1.txt", "", None), "/calib/cal1.txt")

    def test_relative_path_resolved_against_outdir(self):
        ini = "[default]\noutdir = /citscratch/pe\n"
        self.assertEqual(resolve_missing_path("dml/marginal.h5", ini, None), "/citscratch/pe/dml/marginal.h5")

    def test_relative_path_resolved_via_result_file_fallback(self):
        self.assertEqual(
            resolve_missing_path("dml/marginal.h5", "", "/citscratch/pe/result.h5"),
            "/citscratch/pe/dml/marginal.h5",
        )

    def test_returns_none_when_unresolvable(self):
        self.assertIsNone(resolve_missing_path("dml/marginal.h5", "", None))

    def test_outdir_in_default_section(self):
        ini = "[default]\noutdir = /citscratch/pe\nfoo = bar\n"
        self.assertEqual(resolve_missing_path("x/y.h5", ini, None), "/citscratch/pe/x/y.h5")

    def test_relative_outdir_ignored(self):
        ini = "[default]\noutdir = relative/pe\n"
        self.assertIsNone(resolve_missing_path("x/y.h5", ini, None))

    def test_malformed_ini_returns_none_for_outdir(self):
        self.assertIsNone(resolve_missing_path("x/y.h5", "not = valid ini", None))


class TestStageSupportingFiles(unittest.TestCase):
    def _make_tree(self, base):
        tree = Path(base) / "tree"
        for sub in ("data", "result", "results_page"):
            (tree / sub).mkdir(parents=True)
        (tree / "job_config_complete.ini").write_text("label = job\n")
        return tree

    def _make_src(self, base, name="cal1.txt", content="content"):
        src = Path(base) / "src" / name
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(content)
        return src

    def test_copies_staged_file_with_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._make_tree(tmp)
            src = self._make_src(tmp)
            stage_supporting_files(tree, ["/calib/cal1.txt"], {"/calib/cal1.txt": src})
            dest = tree / "calib" / "cal1.txt"
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.read_text(), "content")

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._make_tree(tmp)
            src = self._make_src(tmp)
            with self.assertRaises(StageError):
                stage_supporting_files(tree, ["../escape.txt"], {"../escape.txt": src})

    def test_rejects_nul_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._make_tree(tmp)
            src = self._make_src(tmp)
            with self.assertRaises(StageError):
                stage_supporting_files(tree, ["a\x00b.txt"], {"a\x00b.txt": src})

    def test_rejects_reserved_first_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._make_tree(tmp)
            src = self._make_src(tmp)
            for first in ("data", "result", "results_page"):
                p = f"/{first}/x.txt"
                with self.assertRaises(StageError):
                    stage_supporting_files(tree, [p], {p: src})

    def test_rejects_config_complete_ini_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._make_tree(tmp)
            src = self._make_src(tmp)
            with self.assertRaises(StageError):
                stage_supporting_files(
                    tree,
                    ["/calib/job_config_complete.ini"],
                    {"/calib/job_config_complete.ini": src},
                )

    def test_does_not_clobber_existing_on_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._make_tree(tmp)
            src = self._make_src(tmp)
            original = tree / "data" / "keep.txt"
            original.write_text("original")
            with self.assertRaises(StageError):
                stage_supporting_files(tree, ["/data/keep.txt"], {"/data/keep.txt": src})
            self.assertEqual(original.read_text(), "original")

    def test_skips_missing_paths_not_in_staged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tree = self._make_tree(tmp)
            src = self._make_src(tmp)
            stage_supporting_files(
                tree,
                ["/calib/cal1.txt", "/calib/absent.txt"],
                {"/calib/cal1.txt": src},
            )
            self.assertTrue((tree / "calib" / "cal1.txt").is_file())
            self.assertFalse((tree / "calib" / "absent.txt").exists())


class TestPhaseBilbyChildrenMissingFiles(GWFlowTestBase):
    def _seed_changed_sname(self, sname):
        cur = self.con.cursor()
        state.record_changed_sname(self.con, cur, sname)

    def test_full_flow_fetches_stages_and_reuploads(self):
        sname = "S_A20"
        outdir = "/citscratch/pe"
        ini_text = f"[default]\noutdir = {outdir}\n"
        missing = ["/calib/cal1.txt", "/calib/cal2.txt", "dml/marginal.h5"]
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, uploaded = _make_gwc()
        jc = MagicMock()

        captured_names = []
        upload_calls = [0]

        def upload(description=None, job_archive=None, public=None):
            upload_calls[0] += 1
            if upload_calls[0] == 1:
                raise GWDCUnknownException("missing", extensions={"missing_files": missing})
            with tarfile.open(job_archive, "r:gz") as tar:
                captured_names.extend(tar.getnames())
            return uploaded

        gwc.upload_job_archive.side_effect = upload

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", ini_text)])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]
                cal1 = _write_fetch_files(fetch_dir, [("cal1.txt", "c1")])[0]
                cal2 = _write_fetch_files(fetch_dir, [("cal2.txt", "c2")])[0]
                dml = _write_fetch_files(fetch_dir, [("marginal.h5", b"d")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result, cal1, cal2, dml]) as mock_fetch,
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(mock_fetch.call_count, 5)
        self.assertEqual(gwc.upload_job_archive.call_count, 2)
        gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded.id, sname, "uid1")
        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 0)

        self.assertIn("./calib/cal1.txt", captured_names)
        self.assertIn("./calib/cal2.txt", captured_names)
        self.assertIn("./dml/marginal.h5", captured_names)

        self.assertFalse((Path(staging) / sname / "uid1").exists())
        self.assertFalse((Path(staging) / sname / "uid1.tar.gz").exists())

    def test_fetch_failure_records_failure_no_reupload(self):
        sname = "S_A20FETCH"
        ini_text = "[default]\noutdir = /citscratch/pe\n"
        missing = ["/calib/cal1.txt", "/calib/cal2.txt"]
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        def upload(description=None, job_archive=None, public=None):
            raise GWDCUnknownException("missing", extensions={"missing_files": missing})

        gwc.upload_job_archive.side_effect = upload

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", ini_text)])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]
                cal1 = _write_fetch_files(fetch_dir, [("cal1.txt", "c1")])[0]

                with (
                    patch(
                        "gwflow_ingest.fetch_to_staging", side_effect=[ini, result, cal1, FetchError("fetch failed")]
                    ),
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_not_called()
        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 1)

    def test_unresolvable_relative_path_records_failure(self):
        sname = "S_A20UNRES"
        ini_text = "[default]\nfoo = bar\n"
        missing = ["dml/marginal.h5"]
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path=None)
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        def upload(description=None, job_archive=None, public=None):
            raise GWDCUnknownException("missing", extensions={"missing_files": missing})

        gwc.upload_job_archive.side_effect = upload

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", ini_text)])[0]
                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini]) as mock_fetch,
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(mock_fetch.call_count, 1)
        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_not_called()
        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 1)

    def test_relative_path_fallback_uses_remote_result_file(self):
        sname = "S_A20FALLBACK"
        ini_text = "[default]\nfoo = bar\n"
        missing = ["dml/marginal.h5"]
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, uploaded = _make_gwc()
        jc = MagicMock()

        upload_calls = [0]

        def upload(description=None, job_archive=None, public=None):
            upload_calls[0] += 1
            if upload_calls[0] == 1:
                raise GWDCUnknownException("missing", extensions={"missing_files": missing})
            return uploaded

        gwc.upload_job_archive.side_effect = upload

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", ini_text)])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]
                dml = _write_fetch_files(fetch_dir, [("marginal.h5", b"d")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result, dml]) as mock_fetch,
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(mock_fetch.call_count, 3)
        self.assertEqual(gwc.upload_job_archive.call_count, 2)
        gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded.id, sname, "uid1")
        fetch_paths = [call.args[1]["path"] for call in mock_fetch.call_args_list]
        self.assertIn("/data/pe/dml/marginal.h5", fetch_paths)
        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 0)

    def test_traversal_path_records_failure_no_upload(self):
        sname = "S_A20TRAV"
        ini_text = "[default]\noutdir = /citscratch/pe\n"
        missing = ["../escape.txt"]
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        def upload(description=None, job_archive=None, public=None):
            raise GWDCUnknownException("missing", extensions={"missing_files": missing})

        gwc.upload_job_archive.side_effect = upload

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", ini_text)])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]
                esc = _write_fetch_files(fetch_dir, [("escape.txt", "e")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result, esc]),
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_not_called()
        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 1)

    def test_gwdc_unknown_without_missing_files_records_failure(self):
        sname = "S_A20NOMISS"
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        def upload(description=None, job_archive=None, public=None):
            raise GWDCUnknownException("boom")

        gwc.upload_job_archive.side_effect = upload

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", "label = old\n")])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]
                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]) as mock_fetch,
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_not_called()
        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 1)

    def test_success_path_no_missing_files_unchanged(self):
        sname = "S_A20OK"
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, uploaded = _make_gwc()
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", "label = old\n")])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]
                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]) as mock_fetch,
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded.id, sname, "uid1")


if __name__ == "__main__":
    unittest.main()
