import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from tests.base import GWFlowTestBase
except ImportError:
    from base import GWFlowTestBase

import settings
import state
from bilby_children import (
    _set_ini_label,
    find_bilby_pe_analyses,
    make_archive,
    resolve_event_id_for,
    synthesize_job_tree,
)
from gwflow_ingest import phase_bilby_children, phase_metadata, rec_for
from job_controller import ClusterOffline, FetchError


class TestFindBilbyPeAnalyses(unittest.TestCase):
    def _good_result(self, **overrides):
        result = {
            "uid": "uid-1",
            "inference_software": "BILBY",
            "config_file": {"path": "/data/cfg.ini", "file_size": 10},
            "result_file": {"path": "/data/result.hdf5"},
            "pesummary_result_file": {"path": "/data/summary.html"},
        }
        result.update(overrides)
        return result

    def test_bilby_with_config_file_kept(self):
        detail = {"pe": {"results": [self._good_result()]}}
        analyses = find_bilby_pe_analyses(detail)
        self.assertEqual(len(analyses), 1)
        a = analyses[0]
        self.assertEqual(a["uid"], "uid-1")
        self.assertEqual(a["config_file"], {"path": "/data/cfg.ini", "file_size": 10})
        self.assertEqual(a["result_file"], {"path": "/data/result.hdf5"})
        self.assertEqual(a["pesummary_result_file"], {"path": "/data/summary.html"})
        self.assertEqual(a["software"], "BILBY")

    def test_non_bilby_software_skipped(self):
        detail = {"pe": {"results": [self._good_result(inference_software="lalinf")]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_bilby_case_insensitive_software_kept(self):
        detail = {"pe": {"results": [self._good_result(inference_software="bilby_pipe")]}}
        self.assertEqual(len(find_bilby_pe_analyses(detail)), 1)

    def test_missing_config_file_skipped(self):
        detail = {"pe": {"results": [self._good_result(config_file=None)]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_config_file_without_path_skipped(self):
        detail = {"pe": {"results": [self._good_result(config_file={"file_size": 10})]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_malformed_result_file_skipped(self):
        detail = {"pe": {"results": [self._good_result(result_file="not-a-dict")]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_result_file_without_path_skipped(self):
        detail = {"pe": {"results": [self._good_result(result_file={"file_size": 10})]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_malformed_pesummary_result_file_skipped(self):
        detail = {"pe": {"results": [self._good_result(pesummary_result_file="nope")]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_pesummary_result_file_without_path_skipped(self):
        detail = {"pe": {"results": [self._good_result(pesummary_result_file={})]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_none_result_files_kept(self):
        detail = {"pe": {"results": [self._good_result(result_file=None, pesummary_result_file=None)]}}
        self.assertEqual(len(find_bilby_pe_analyses(detail)), 1)

    def test_missing_uid_skipped(self):
        detail = {"pe": {"results": [self._good_result(uid="")]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_non_string_uid_skipped(self):
        detail = {"pe": {"results": [self._good_result(uid=None)]}}
        self.assertEqual(find_bilby_pe_analyses(detail), [])

    def test_missing_pe_section_returns_empty(self):
        self.assertEqual(find_bilby_pe_analyses({"foo": "bar"}), [])

    def test_non_dict_detail_returns_empty(self):
        self.assertEqual(find_bilby_pe_analyses(None), [])
        self.assertEqual(find_bilby_pe_analyses(["not a dict"]), [])
        self.assertEqual(find_bilby_pe_analyses("string"), [])

    def test_non_dict_pe_returns_empty(self):
        self.assertEqual(find_bilby_pe_analyses({"pe": "nope"}), [])
        self.assertEqual(find_bilby_pe_analyses({"pe": ["list"]}), [])
        self.assertEqual(find_bilby_pe_analyses({"pe": None}), [])

    def test_non_list_results_returns_empty(self):
        self.assertEqual(find_bilby_pe_analyses({"pe": {"results": "nope"}}), [])
        self.assertEqual(find_bilby_pe_analyses({"pe": {"results": {"0": "thing"}}}), [])

    def test_non_dict_result_entries_skipped(self):
        detail = {"pe": {"results": ["string", None, self._good_result()]}}
        self.assertEqual(len(find_bilby_pe_analyses(detail)), 1)

    def test_multiple_results_filtered(self):
        detail = {
            "pe": {
                "results": [
                    self._good_result(uid="uid-a", inference_software="bilby"),
                    self._good_result(uid="uid-b", inference_software="lalinf"),
                    self._good_result(uid="uid-c", inference_software="BILBY"),
                    self._good_result(uid="uid-d", config_file=None),
                ]
            }
        }
        kept_uids = [a["uid"] for a in find_bilby_pe_analyses(detail)]
        self.assertEqual(kept_uids, ["uid-a", "uid-c"])


class TestSetIniLabel(unittest.TestCase):
    def test_existing_label_replaced_case_insensitive(self):
        text = "label = old\nfoo = bar\n"
        self.assertEqual(_set_ini_label(text, "new"), "label = new\nfoo = bar\n")

    def test_existing_label_replaced_uppercase(self):
        text = "LABEL=old\nfoo = bar\n"
        self.assertEqual(_set_ini_label(text, "new"), "label = new\nfoo = bar\n")

    def test_existing_label_replaced_with_whitespace_tolerance(self):
        text = "label    = old\nfoo = bar\n"
        self.assertEqual(_set_ini_label(text, "new"), "label = new\nfoo = bar\n")

    def test_existing_label_in_default_section_replaced(self):
        text = "[default]\nlabel = old\nfoo = bar\n"
        out = _set_ini_label(text, "new")
        self.assertIn("label = new\n", out)
        self.assertNotIn("label = old", out)
        self.assertIn("[default]\n", out)
        self.assertIn("foo = bar\n", out)

    def test_missing_label_prepended(self):
        text = "foo = bar\nbaz = qux\n"
        out = _set_ini_label(text, "new")
        self.assertTrue(out.startswith("label = new\n"))
        self.assertIn("foo = bar\n", out)
        self.assertIn("baz = qux\n", out)

    def test_empty_text_prepends(self):
        out = _set_ini_label("", "new")
        self.assertEqual(out, "label = new\n")

    def test_only_first_existing_label_replaced(self):
        text = "label = first\nlabel = second\n"
        self.assertEqual(_set_ini_label(text, "new"), "label = new\nlabel = second\n")

    def test_comment_on_label_line_replaced(self):
        text = "label = old  # keep me? no\nfoo = bar\n"
        out = _set_ini_label(text, "new")
        self.assertIn("label = new\n", out)
        self.assertNotIn("label = old", out)


class TestSynthesizeJobTree(unittest.TestCase):
    def _write(self, path: Path, content: str = "x"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_creates_three_subdirs_when_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            synthesize_job_tree(workdir, name="S260101a--uid1", ini_text="[default]\n", result_files=[])
            for sub in ("data", "result", "results_page"):
                self.assertTrue((workdir / sub).is_dir(), f"missing dir: {sub}")

    def test_writes_config_complete_ini_with_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            synthesize_job_tree(workdir, name="S260101a--uid1", ini_text="[default]\n", result_files=[])
            ini = workdir / "S260101a--uid1_config_complete.ini"
            self.assertTrue(ini.is_file())

    def test_ini_label_overridden_to_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            synthesize_job_tree(
                workdir,
                name="S260101a--uid1",
                ini_text="[default]\nlabel = something_old\nfoo = bar\n",
                result_files=[],
            )
            content = (workdir / "S260101a--uid1_config_complete.ini").read_text()
            self.assertIn("label = S260101a--uid1\n", content)
            self.assertNotIn("something_old", content)

    def test_ini_label_prepended_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            synthesize_job_tree(workdir, name="newjob", ini_text="foo = bar\n", result_files=[])
            content = (workdir / "newjob_config_complete.ini").read_text()
            self.assertTrue(content.startswith("label = newjob\n"))
            self.assertIn("foo = bar\n", content)

    def test_primary_hdf5_result_renamed_to_result_hdf5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            staging = Path(tmpdir) / "staging"
            primary = self._write(staging / "pe_result.hdf5", "hdf5-data")
            synthesize_job_tree(workdir, name="j", ini_text="", result_files=[primary])
            self.assertTrue((workdir / "result" / "result.hdf5").is_file())
            self.assertFalse((workdir / "result" / "pe_result.hdf5").exists())

    def test_primary_h5_result_renamed_to_result_hdf5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            staging = Path(tmpdir) / "staging"
            primary = self._write(staging / "result.h5", "h5-data")
            synthesize_job_tree(workdir, name="j", ini_text="", result_files=[primary])
            self.assertTrue((workdir / "result" / "result.hdf5").is_file())

    def test_primary_hdf5_uppercase_suffix_renamed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            staging = Path(tmpdir) / "staging"
            primary = self._write(staging / "result.HDF5", "hdf5-data")
            synthesize_job_tree(workdir, name="j", ini_text="", result_files=[primary])
            self.assertTrue((workdir / "result" / "result.hdf5").is_file())

    def test_primary_non_hdf5_result_keeps_basename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            staging = Path(tmpdir) / "staging"
            primary = self._write(staging / "pesummary.html", "html-data")
            synthesize_job_tree(workdir, name="j", ini_text="", result_files=[primary])
            self.assertTrue((workdir / "result" / "pesummary.html").is_file())

    def test_secondary_results_keep_basename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            staging = Path(tmpdir) / "staging"
            primary = self._write(staging / "result.hdf5", "hdf5-data")
            secondary = self._write(staging / "summary.html", "html-data")
            tertiary = self._write(staging / "extra.json", "json-data")
            synthesize_job_tree(workdir, name="j", ini_text="", result_files=[primary, secondary, tertiary])
            self.assertTrue((workdir / "result" / "result.hdf5").is_file())
            self.assertTrue((workdir / "result" / "summary.html").is_file())
            self.assertTrue((workdir / "result" / "extra.json").is_file())

    def test_returns_workdir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "job"
            ret = synthesize_job_tree(workdir, name="j", ini_text="", result_files=[])
            self.assertEqual(ret, workdir)


class TestMakeArchive(unittest.TestCase):
    def test_produces_valid_tar_gz_with_dot_root_member(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tree = Path(tmpdir) / "tree"
            (tree / "data").mkdir(parents=True)
            (tree / "result").mkdir()
            (tree / "results_page").mkdir()
            (tree / "myjob_config_complete.ini").write_text("label = myjob\n")
            (tree / "result" / "result.hdf5").write_bytes(b"x")
            (tree / "result" / "summary.html").write_text("h")

            dest = Path(tmpdir) / "out.tar.gz"
            make_archive(tree, dest)
            self.assertTrue(dest.is_file())
            self.assertTrue(dest.stat().st_size > 0)

            with tarfile.open(dest, "r:gz") as tar:
                names = tar.getnames()
            self.assertIn(".", names)
            self.assertIn("./myjob_config_complete.ini", names)
            self.assertIn("./result/result.hdf5", names)
            self.assertIn("./result/summary.html", names)

    def test_extractable_with_django_tar_dot_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tree = Path(tmpdir) / "tree"
            (tree / "data").mkdir(parents=True)
            (tree / "result").mkdir()
            (tree / "results_page").mkdir()
            (tree / "myjob_config_complete.ini").write_text("label = myjob\n")
            (tree / "result" / "result.hdf5").write_bytes(b"x")

            dest = Path(tmpdir) / "out.tar.gz"
            make_archive(tree, dest)

            staging = Path(tmpdir) / "staging"
            staging.mkdir()
            proc = subprocess.run(
                ["tar", "-xvf", str(dest), "."],
                capture_output=True,
                cwd=staging,
            )
            self.assertEqual(proc.returncode, 0, f"tar failed: {proc.stderr.decode()}")
            for sub in ("data", "result", "results_page"):
                self.assertTrue((staging / sub).is_dir(), f"missing {sub} after extract")
            self.assertTrue((staging / "myjob_config_complete.ini").is_file())

    def test_includes_empty_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tree = Path(tmpdir) / "tree"
            tree.mkdir()
            (tree / "data").mkdir()
            (tree / "result").mkdir()
            (tree / "results_page").mkdir()
            (tree / "j_config_complete.ini").write_text("")

            dest = Path(tmpdir) / "out.tar.gz"
            make_archive(tree, dest)

            with tarfile.open(dest, "r:gz") as tar:
                members = tar.getmembers()
            arcnames = [m.name for m in members]
            for sub in ("data", "result", "results_page"):
                self.assertIn(f"./{sub}", arcnames, f"empty dir {sub} not in archive")

    def test_arcnames_relative_to_tree_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tree = Path(tmpdir) / "deep" / "tree"
            tree.mkdir(parents=True)
            (tree / "data").mkdir()
            (tree / "j_config_complete.ini").write_text("")

            dest = Path(tmpdir) / "out.tar.gz"
            make_archive(tree, dest)

            with tarfile.open(dest, "r:gz") as tar:
                names = tar.getnames()
            for name in names:
                self.assertFalse(name.startswith("/"), f"arcname {name!r} is not relative")
                self.assertFalse(".." in Path(name).parts, f"arcname {name!r} escapes")

    def test_returns_dest_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tree = Path(tmpdir) / "tree"
            tree.mkdir()
            dest = Path(tmpdir) / "x.tar.gz"
            ret = make_archive(tree, dest)
            self.assertEqual(ret, dest)


class TestResolveEventIdFor(unittest.TestCase):
    def test_preferred_event_field_used(self):
        detail = {
            "gracedb": {
                "preferred_event": "EVT-A",
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5},
                    {"uid": "EVT-B", "gps_time": 1111111111.0},
                ],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_preferred_event_uid_alias_used(self):
        detail = {
            "gracedb": {
                "preferred_event_uid": "EVT-B",
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5},
                    {"uid": "EVT-B", "gps_time": 1111111111.0},
                ],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-B", 1111111111.0))

    def test_is_preferred_event_used(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5},
                    {"uid": "EVT-B", "gps_time": 1111111111.0, "is_preferred": True},
                ]
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-B", 1111111111.0))

    def test_is_preferred_string_true(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5, "is_preferred": "true"},
                ]
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_preferred_field_used(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5},
                    {"uid": "EVT-B", "gps_time": 1111111111.0, "preferred": "yes"},
                ]
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-B", 1111111111.0))

    def test_first_event_fallback(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5},
                    {"uid": "EVT-B", "gps_time": 1111111111.0},
                ]
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_missing_gps_time_returns_none(self):
        detail = {"gracedb": {"events": [{"uid": "EVT-A"}]}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_non_numeric_gps_returns_none(self):
        detail = {"gracedb": {"events": [{"uid": "EVT-A", "gps_time": "not-a-number"}]}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_gpstime_alias_used(self):
        detail = {"gracedb": {"events": [{"uid": "EVT-A", "gpstime": 1234567890.5}]}}
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_gracedb_preferred_event_gps_fallback(self):
        detail = {
            "gracedb": {
                "preferred_event_gps": 1234567890.5,
                "events": [{"uid": "EVT-A"}],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_gracedb_gps_time_fallback(self):
        detail = {
            "gracedb": {
                "gps_time": 1234567890.5,
                "events": [{"uid": "EVT-A"}],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_missing_uid_returns_none(self):
        detail = {"gracedb": {"events": [{"gps_time": 1234567890.5}]}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_empty_uid_returns_none(self):
        detail = {"gracedb": {"events": [{"uid": "", "gps_time": 1234567890.5}]}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_missing_gracedb_section_returns_none(self):
        self.assertIsNone(resolve_event_id_for("S1", {"foo": "bar"}))

    def test_non_dict_gracedb_returns_none(self):
        self.assertIsNone(resolve_event_id_for("S1", {"gracedb": "nope"}))
        self.assertIsNone(resolve_event_id_for("S1", {"gracedb": None}))

    def test_GraceDB_caps_alias(self):
        detail = {
            "GraceDB": {
                "events": [{"uid": "EVT-A", "gps_time": 1234567890.5}],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_Empty_events_returns_none(self):
        detail = {"gracedb": {"events": []}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_Events_alias_used(self):
        detail = {
            "gracedb": {
                "Events": [{"uid": "EVT-A", "gps_time": 1234567890.5}],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_non_dict_detail_returns_none(self):
        self.assertIsNone(resolve_event_id_for("S1", None))
        self.assertIsNone(resolve_event_id_for("S1", ["not a dict"]))


def _bilby_analysis(
    uid="uid1",
    config_path="/data/pe/config.ini",
    result_path="/data/pe/result.h5",
    summary_path=None,
    software="bilby",
):
    return {
        "uid": uid,
        "inference_software": software,
        "config_file": {"path": config_path, "file_size": 100, "md5_sum": ""},
        "result_file": {"path": result_path, "file_size": 200, "md5_sum": ""} if result_path else None,
        "pesummary_result_file": ({"path": summary_path, "file_size": 50, "md5_sum": ""} if summary_path else None),
    }


def _bilby_detail(sname="S1", analyses=None, gracedb=None):
    detail = {
        "sname": sname,
        "raw_payload": {"sname": sname},
        "pe": {"results": analyses if analyses is not None else []},
    }
    if gracedb is not None:
        detail["gracedb"] = gracedb
    return detail


def _make_gwc(job=None, uploaded_id="job-id-1"):
    gwc = MagicMock()
    if job is None:
        job = MagicMock()
        job.bilby_jobs = None
    gwc.get_gwflow_job.return_value = job
    uploaded = MagicMock()
    uploaded.id = uploaded_id
    gwc.upload_job_archive.return_value = uploaded
    return gwc, uploaded


def _write_fetch_files(base, names_and_content):
    paths = []
    for name, content in names_and_content:
        p = Path(base) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content)
        else:
            p.write_bytes(content)
        paths.append(p)
    return paths


class TestPhaseBilbyChildrenOrchestrator(GWFlowTestBase):
    def _seed_changed_sname(self, sname):
        cur = self.con.cursor()
        state.record_changed_sname(self.con, cur, sname)

    def test_clients_not_wired_skips_without_calling_anything(self):
        portal = MagicMock()

        phase_bilby_children(portal_client=portal, gwc_client=None, jc=MagicMock(), con=self.con)
        portal.get_superevent.assert_not_called()

        phase_bilby_children(portal_client=portal, gwc_client=MagicMock(), jc=None, con=self.con)
        portal.get_superevent.assert_not_called()

        phase_bilby_children(portal_client=portal, gwc_client=None, jc=None, con=self.con)
        portal.get_superevent.assert_not_called()

    def test_happy_path_uploads_and_cleans_staging(self):
        sname = "S_HAPPY"
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
                upload_args, upload_kwargs = gwc.upload_job_archive.call_args
                self.assertEqual(upload_kwargs["description"], f"gwflow {sname} PE uid1")
                self.assertTrue(upload_kwargs["public"])
                archive_path = upload_kwargs["job_archive"]
                self.assertEqual(archive_path.name, "uid1.tar.gz")
                self.assertTrue(str(archive_path).startswith(staging))
                self.assertEqual(archive_path.parent.name, sname)

                first_fetch_args = mock_fetch.call_args_list[0].args
                self.assertEqual(first_fetch_args[0], jc)
                self.assertEqual(first_fetch_args[1]["sname"], sname)
                self.assertEqual(first_fetch_args[1]["analysis_uid"], "uid1")
                self.assertEqual(first_fetch_args[1]["path"], "/data/pe/config.ini")

                gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded.id, sname, "uid1")

                self.assertFalse((Path(staging) / sname / "uid1").exists())
                self.assertFalse((Path(staging) / sname / "uid1.tar.gz").exists())

    def test_event_id_best_effort_called(self):
        sname = "S_EV"
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        gracedb = {
            "preferred_event": "EVT-A",
            "events": [{"uid": "EVT-A", "gps_time": 1234567890.5}],
        }
        detail = _bilby_detail(sname=sname, analyses=[analysis], gracedb=gracedb)
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
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]),
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        gwc.create_event_id.assert_called_once_with("EVT-A", 1234567890.5, trigger_id=sname)
        uploaded.set_event_id.assert_called_once_with("EVT-A")

    def test_event_id_failure_logged_not_fatal(self):
        sname = "S_EVFAIL"
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        gracedb = {
            "preferred_event": "EVT-A",
            "events": [{"uid": "EVT-A", "gps_time": 1234567890.5}],
        }
        detail = _bilby_detail(sname=sname, analyses=[analysis], gracedb=gracedb)
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, uploaded = _make_gwc()
        gwc.create_event_id.side_effect = RuntimeError("event id error")
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", "label = old\n")])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]),
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_called_once()

    def test_idempotent_rerun_skips_linked(self):
        sname = "S_IDEMP"
        analysis = _bilby_analysis(uid="uid1")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail

        job = MagicMock()
        bilby = MagicMock(gwflow_analysis_uid="uid1")
        job.bilby_jobs = [bilby]
        gwc, _ = _make_gwc(job=job)
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()
        gwc.link_bilby_job_to_gwflow.assert_not_called()

    def test_stale_linked_child_row_cleared(self):
        sname = "S_STALE"
        analysis = _bilby_analysis(uid="uid1")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        cur = self.con.cursor()
        state.ensure_pending(self.con, cur, f"bilby:{sname}")
        state.record_failure(self.con, cur, f"bilby:{sname}/uid1", "link timeout", job_ref="orphan-1")

        portal = MagicMock()
        portal.get_superevent.return_value = detail

        job = MagicMock()
        bilby = MagicMock(gwflow_analysis_uid="uid1")
        job.bilby_jobs = [bilby]
        gwc, _ = _make_gwc(job=job)
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 0)
        self.assertIsNone(state.get_failure_job_ref(cur, f"bilby:{sname}/uid1"))
        marker = cur.execute("SELECT 1 FROM job_errors WHERE job_id = ?", (f"bilby:{sname}",)).fetchone()
        self.assertIsNone(marker)
        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()
        gwc.link_bilby_job_to_gwflow.assert_not_called()

    def test_non_bilby_ignored(self):
        sname = "S_NONBILBY"
        analysis = _bilby_analysis(uid="uid1", software="pycbc")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()

    def test_missing_config_file_ignored(self):
        sname = "S_NOCFG"
        analysis = _bilby_analysis(uid="uid1")
        analysis["config_file"] = None
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()

    def test_missing_uid_ignored(self):
        sname = "S_NOUID"
        analysis = _bilby_analysis(uid="")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()

    def test_per_analysis_failure_continues(self):
        sname = "S_PERF"
        a1 = _bilby_analysis(uid="uid1", config_path="/data/pe/c1.ini", result_path="/data/pe/r1.h5")
        a2 = _bilby_analysis(uid="uid2", config_path="/data/pe/c2.ini", result_path="/data/pe/r2.h5")
        detail = _bilby_detail(sname=sname, analyses=[a1, a2])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        cur = self.con.cursor()
        key_a1 = f"bilby:{sname}/uid1"
        key_a2 = f"bilby:{sname}/uid2"

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                c2 = _write_fetch_files(fetch_dir, [("c2.ini", "label = old\n")])[0]
                r2 = _write_fetch_files(fetch_dir, [("r2.h5", b"x")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[FetchError("fetch failure"), c2, r2]),
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(state.get_failure_count(cur, key_a1), 1)
        self.assertEqual(state.get_failure_count(cur, key_a2), 0)
        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        self.assertEqual(gwc.link_bilby_job_to_gwflow.call_count, 1)

    def test_over_retry_skipped(self):
        sname = "S_RETRY"
        analysis = _bilby_analysis(uid="uid1")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        cur = self.con.cursor()
        key = f"bilby:{sname}/uid1"
        for _ in range(settings.MAX_RETRY_ATTEMPTS):
            state.record_failure(self.con, cur, key, "earlier failure")

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()

    def test_cluster_offline_defers_remaining(self):
        sname = "S_OFFLINE"
        a1 = _bilby_analysis(uid="uid1")
        a2 = _bilby_analysis(uid="uid2")
        detail = _bilby_detail(sname=sname, analyses=[a1, a2])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging", side_effect=ClusterOffline("offline")) as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(mock_fetch.call_count, 1)
        gwc.upload_job_archive.assert_not_called()

    def test_cap_honoured(self):
        sname = "S_CAP"
        a1 = _bilby_analysis(uid="uid1", config_path="/data/pe/c1.ini", result_path="/data/pe/r1.h5")
        a2 = _bilby_analysis(uid="uid2", config_path="/data/pe/c2.ini", result_path="/data/pe/r2.h5")
        detail = _bilby_detail(sname=sname, analyses=[a1, a2])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                c1 = _write_fetch_files(fetch_dir, [("c1.ini", "label = old\n")])[0]
                r1 = _write_fetch_files(fetch_dir, [("r1.h5", b"x")])[0]
                _c2 = _write_fetch_files(fetch_dir, [("c2.ini", "label = old\n")])[0]
                _r2 = _write_fetch_files(fetch_dir, [("r2.h5", b"x")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[c1, r1, _c2, _r2]),
                    patch.object(settings, "STAGING_DIR", staging),
                    patch.object(settings, "MAX_FILES_PER_RUN", 1),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(gwc.upload_job_archive.call_count, 1)

    def test_failed_child_retried_without_portal_change(self):
        sname = "S_RETRY2"
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        cur = self.con.cursor()
        state.record_failure(self.con, cur, f"bilby:{sname}/uid1", "earlier failure")

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, uploaded = _make_gwc()
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", "label = old\n")])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]),
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded.id, sname, "uid1")
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 0)
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}"), 0)

    def test_link_failure_orphan_links_persisted_job_ref(self):
        sname = "S_ORPHAN"
        analysis = _bilby_analysis(uid="uid1", config_path="/data/pe/config.ini", result_path="/data/pe/result.h5")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc(uploaded_id="orphan-1")
        gwc.link_bilby_job_to_gwflow.side_effect = RuntimeError("graphql down")
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", "label = old\n")])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]),
                    patch.object(settings, "STAGING_DIR", staging),
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 1)
        self.assertEqual(state.get_failure_job_ref(cur, f"bilby:{sname}/uid1"), "orphan-1")
        self.assertEqual(gwc.upload_job_archive.call_count, 1)

        gwc.link_bilby_job_to_gwflow.side_effect = None
        with tempfile.TemporaryDirectory() as staging:
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                with patch.object(settings, "STAGING_DIR", staging):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        gwc.link_bilby_job_to_gwflow.assert_called_with("orphan-1", sname, "uid1")
        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        mock_fetch.assert_not_called()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}/uid1"), 0)

    def test_sname_marker_persists_for_kill_recovery(self):
        sname = "S_KILL"
        analysis = _bilby_analysis(uid="uid1")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc()
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging", side_effect=ClusterOffline("offline")):
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        cur = self.con.cursor()
        marker = cur.execute("SELECT 1 FROM job_errors WHERE job_id = ?", (f"bilby:{sname}",)).fetchone()
        self.assertIsNotNone(marker)

        no_child_sname = "S_NOKIDS"
        self._seed_changed_sname(no_child_sname)
        portal2 = MagicMock()
        portal2.get_superevent.side_effect = lambda s: _bilby_detail(sname=s, analyses=[])
        gwc2, _ = _make_gwc()
        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging"):
                phase_bilby_children(portal_client=portal2, gwc_client=gwc2, jc=jc, con=self.con)

        marker2 = cur.execute("SELECT 1 FROM job_errors WHERE job_id = ?", (f"bilby:{no_child_sname}",)).fetchone()
        self.assertIsNone(marker2)

    def test_detail_fetch_failure_retried(self):
        sname = "S_DETAIL"
        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.side_effect = RuntimeError("portal down")
        gwc, _ = _make_gwc()
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        cur = self.con.cursor()
        self.assertEqual(state.get_failure_count(cur, f"bilby:{sname}"), 1)
        bare = cur.execute("SELECT 1 FROM job_errors WHERE job_id = ?", (sname,)).fetchone()
        self.assertIsNone(bare)

    def test_phase_metadata_records_changed_snames(self):
        portal = MagicMock()
        portal.iter_changed.return_value = [
            {
                "sname": "S1",
                "commit_timestamp": "2026-01-01T10:00:00Z",
                "schema_version": "1.0",
                "commit_sha": "sha1",
            },
        ]
        portal.get_superevent.return_value = {"sname": "S1", "raw_payload": {}}
        portal.iter_current_snames.return_value = ["S1"]
        gwc = MagicMock()
        gwc.get_gwflow_job_list.return_value = []

        cur = self.con.cursor()
        phase_metadata(portal_client=portal, gwc_client=gwc, con=self.con)

        self.assertEqual(state.get_changed_snames(cur), ["S1"])

    def test_phase_metadata_clears_changed_snames_per_run(self):
        portal = MagicMock()
        portal.iter_changed.return_value = []
        portal.iter_current_snames.return_value = []
        gwc = MagicMock()
        gwc.get_gwflow_job_list.return_value = []

        cur = self.con.cursor()
        state.record_changed_sname(self.con, cur, "STALE")
        self.assertEqual(state.get_changed_snames(cur), ["STALE"])

        phase_metadata(portal_client=portal, gwc_client=gwc, con=self.con)

        self.assertEqual(state.get_changed_snames(cur), [])

    def test_end_to_end_compatible_with_a17(self):
        sname = "S_A17"
        detail = {
            "sname": sname,
            "raw_payload": {"sname": sname, "event": "GW260101"},
            "libraries": [{"name": "bilby"}],
        }
        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc = MagicMock()
        gwc.get_gwflow_job.return_value = MagicMock()
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        gwc.upload_job_archive.assert_not_called()
        gwc.link_bilby_job_to_gwflow.assert_not_called()

    def test_portal_client_none_creates_default(self):
        sname = "S_PDEFAULT"
        analysis = _bilby_analysis(uid="uid1")
        detail = _bilby_detail(sname=sname, analyses=[analysis])
        self._seed_changed_sname(sname)

        gwc, _ = _make_gwc()
        jc = MagicMock()

        with patch("gwflow_ingest.PortalClient") as mock_portal_cls:
            mock_portal = MagicMock()
            mock_portal.get_superevent.return_value = detail
            mock_portal_cls.return_value = mock_portal

            with tempfile.TemporaryDirectory() as staging:
                with tempfile.TemporaryDirectory() as fetch_dir:
                    ini = _write_fetch_files(fetch_dir, [("config.ini", "label = old\n")])[0]
                    result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]

                    with (
                        patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]),
                        patch.object(settings, "STAGING_DIR", staging),
                    ):
                        phase_bilby_children(gwc_client=gwc, jc=jc, con=self.con)

            mock_portal_cls.assert_called_once()
            mock_portal.get_superevent.assert_called_once_with(sname)
            self.assertEqual(gwc.upload_job_archive.call_count, 1)


class TestRecForHelper(unittest.TestCase):
    def test_builds_pending_file_shape(self):
        file_ref = {"path": "/data/pe/config.ini", "md5_sum": "abc123", "file_size": 100}
        result = rec_for(file_ref, "S1", "uid1")
        self.assertEqual(
            result,
            {
                "sname": "S1",
                "analysis_uid": "uid1",
                "path": "/data/pe/config.ini",
                "file_name": "config.ini",
                "md5_sum": "abc123",
            },
        )

    def test_missing_md5_defaults_to_empty_string(self):
        file_ref = {"path": "/data/x.h5"}
        result = rec_for(file_ref, "S1", "uid1")
        self.assertEqual(result["md5_sum"], "")

    def test_none_md5_defaults_to_empty_string(self):
        file_ref = {"path": "/data/x.h5", "md5_sum": None}
        result = rec_for(file_ref, "S1", "uid1")
        self.assertEqual(result["md5_sum"], "")


if __name__ == "__main__":
    unittest.main()
