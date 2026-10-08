import copy
import random
import subprocess
import tarfile
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock, call, patch

try:
    from tests.base import GWFlowTestBase
except ImportError:
    from base import GWFlowTestBase

import settings
import state
from bilby_children import (
    SUPPORTED_BILBY_SOFTWARE,
    Rejection,
    StageError,
    _ini_outdir,
    _set_ini_label,
    _tree_relative_target,
    make_archive,
    resolve_event_id_for,
    select_bilby_analyses,
    synthesize_job_tree,
    validate_supported_software,
)
from gwflow_ingest import linked_analysis_uids, phase_bilby_children, phase_metadata, rec_for
from job_controller import ClusterOffline, FetchError

try:
    from tests.golden import build_superevent
except ImportError:
    from golden import build_superevent


class TestLinkedAnalysisUids(unittest.TestCase):
    def test_sc_1_builds_expected_uid_set(self):
        gwc = MagicMock()
        gwc.request.return_value = {
            "gwflow_linked_bilby_jobs": [
                {"id": "job-1", "gwflow_analysis_uid": "uid-a"},
                {"id": "job-2", "gwflow_analysis_uid": "uid-b"},
                {"id": "job-3", "gwflow_analysis_uid": "uid-a"},
            ]
        }

        self.assertEqual(linked_analysis_uids(gwc, "S_SC1"), {"uid-a", "uid-b"})
        gwc.get_gwflow_job.assert_not_called()

    def test_sc_2_absent_or_malformed_rows_raise(self):
        cases = [
            ({}, KeyError),
            ({"gwflow_linked_bilby_jobs": [{}]}, KeyError),
            ({"gwflow_linked_bilby_jobs": None}, TypeError),
        ]
        for response, exception in cases:
            with self.subTest(response=response):
                gwc = MagicMock()
                gwc.request.return_value = response
                with self.assertRaises(exception):
                    linked_analysis_uids(gwc, "S_SC2")

    def test_sc_3_uses_ingest_query_and_sname_variables(self):
        gwc = MagicMock()
        gwc.request.return_value = {"gwflow_linked_bilby_jobs": []}

        self.assertEqual(linked_analysis_uids(gwc, "S_SC3"), set())

        gwc.request.assert_called_once()
        kwargs = gwc.request.call_args.kwargs
        self.assertEqual(kwargs["variables"], {"sname": "S_SC3"})
        self.assertIn("gwflowLinkedBilbyJobs(sname: $sname)", kwargs["query"])
        self.assertIn("gwflowAnalysisUid", kwargs["query"])
        gwc.get_gwflow_job.assert_not_called()


class TestSelectBilbyAnalyses(unittest.TestCase):
    file_systems = ("OzStar", "CIT", "LDAS")

    def detail(self):
        detail = build_superevent("S000001a")
        detail["analyses"] = [detail["analyses"][0]]
        return detail

    def analysis(self):
        return self.detail()["analyses"][0]

    def select(self, detail=None, file_systems=None):
        return select_bilby_analyses(
            "S000001a",
            detail if detail is not None else self.detail(),
            self.file_systems if file_systems is None else file_systems,
        )

    def relationship(self, role, path, *, file_system="OzStar", md5sum="abc", url=None):
        return {
            "direction": "output",
            "role": role,
            "file": {
                "name": Path(path).name,
                "description": role,
                "md5sum": md5sum,
                "last_modified": None,
                "locations": [
                    {
                        "file_system": file_system,
                        "path": path,
                        "url": url,
                    }
                ],
            },
        }

    def test_te_1_eligible_golden_analysis(self):
        selected, rejected = self.select()
        self.assertEqual(rejected, [])
        self.assertEqual(len(selected), 1)
        self.assertEqual(
            selected[0],
            {
                "uid": "pe_1",
                "config_file": {
                    "path": "/ozstar/S000001a/pe_1.ini",
                    "md5_sum": "0123456789abcdef0123456789abcdef",
                },
                "result_file": {
                    "path": "/ozstar/S000001a/pe_1_result.hdf5",
                    "md5_sum": None,
                },
                "pesummary_result_file": None,
                "software": "bilby_pipe",
            },
        )

    def test_te_2_to_5_configuration_and_config_role_counts(self):
        cases = []

        zero_config = self.detail()
        zero_config["analyses"][0]["configurations"] = []
        cases.append(("TE-2 zero configuration", zero_config, 0, 0, None))

        multiple_config = self.detail()
        multiple_config["analyses"][0]["configurations"] *= 2
        cases.append(("TE-3 multiple configurations", multiple_config, 0, 1, "multiple pe configurations"))

        zero_role = self.detail()
        zero_role["analyses"][0]["input_files"] = []
        cases.append(("TE-4 zero config roles", zero_role, 0, 0, None))

        multiple_role = self.detail()
        multiple_role["analyses"][0]["input_files"] *= 2
        cases.append(("TE-5 multiple config roles", multiple_role, 0, 1, "multiple config relationships"))

        precedence_zero = self.detail()
        precedence_zero["analyses"][0]["configurations"] = []
        precedence_zero["analyses"][0]["input_files"] *= 2
        cases.append(("TE-2 precedence", precedence_zero, 0, 0, None))

        precedence_multiple = self.detail()
        precedence_multiple["analyses"][0]["configurations"] *= 2
        precedence_multiple["analyses"][0]["input_files"] = []
        cases.append(("TE-3 precedence", precedence_multiple, 0, 1, "multiple pe configurations"))

        for name, detail, selected_count, rejection_count, reason in cases:
            with self.subTest(name=name):
                selected, rejected = self.select(detail)
                self.assertEqual(len(selected), selected_count)
                self.assertEqual(len(rejected), rejection_count)
                if reason:
                    self.assertEqual(rejected[0].reason, reason)

    def test_te_6_7_8_9_10_software_truth_table(self):
        cases = [
            ("TE-6 unsupported", {"name": "pycbc"}, 0),
            ("TE-7 null", None, 0),
            ("TE-8 absent", Ellipsis, 1),
            ("TE-9 string", "bilby", 1),
            ("TE-9 list", [], 1),
            ("TE-9 integer", 1, 1),
            ("TE-9 boolean", True, 1),
            ("TE-10 missing name", {}, 1),
            ("TE-10 non-string name", {"name": 1}, 1),
        ]
        for name, software, rejection_count in cases:
            with self.subTest(name=name):
                detail = self.detail()
                analysis = detail["analyses"][0]
                if software is Ellipsis:
                    del analysis["software"]
                else:
                    analysis["software"] = software
                selected, rejected = self.select(detail)
                self.assertEqual(selected, [])
                self.assertEqual(len(rejected), rejection_count)

    def test_te_11_required_fields(self):
        mutations = [
            ("uid", None),
            ("status", None),
            ("status", "unknown"),
            ("deprecated", None),
            ("deprecated", 1),
            ("input_files", None),
            ("output_files", None),
            ("configurations", None),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                detail = self.detail()
                detail["analyses"][0][field] = value
                selected, rejected = self.select(detail)
                self.assertEqual(selected, [])
                self.assertEqual(len(rejected), 1)
                self.assertIn(field, rejected[0].reason)

    def test_te_12_event_validation_is_ignored(self):
        detail = build_superevent("S000001a")
        detail["analyses"] = [detail["analyses"][1]]
        self.assertEqual(self.select(detail), ([], []))

    def test_te_13_14_malformed_analysis_rows(self):
        cases = [
            {},
            {"type": 1},
            {"type": "unknown"},
            None,
            "analysis",
            [],
        ]
        for row in cases:
            with self.subTest(row=row):
                detail = self.detail()
                detail["analyses"] = [row]
                selected, rejected = self.select(detail)
                self.assertEqual(selected, [])
                self.assertEqual(len(rejected), 1)
                self.assertEqual(rejected[0].reason, "malformed analysis type")

    def test_te_15_duplicate_eligible_uid_rejects_whole_update(self):
        detail = self.detail()
        detail["analyses"].append(copy.deepcopy(detail["analyses"][0]))
        selected, rejected = self.select(detail)
        self.assertEqual(selected, [])
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].analysis_uid, "pe_1")
        self.assertEqual(rejected[0].reason, "duplicate eligible uid")

    def test_te_16_exact_case_sensitive_allowlist(self):
        unsupported = [
            "Bilby",
            "bilby_PIPE",
            "pybilby",
            "bilby-pipe",
            "bilby ",
            "bilby_pipe2",
            "",
        ]
        for name in unsupported:
            with self.subTest(name=name):
                detail = self.detail()
                detail["analyses"][0]["software"]["name"] = name
                self.assertEqual(self.select(detail), ([], []))

        for name in ("bilby", "BILBY", "bilby_pipe"):
            with self.subTest(name=name):
                detail = self.detail()
                detail["analyses"][0]["software"]["name"] = name
                selected, rejected = self.select(detail)
                self.assertEqual(len(selected), 1)
                self.assertEqual(rejected, [])

    def test_te_17_allowlist_constant_and_validation(self):
        self.assertEqual(SUPPORTED_BILBY_SOFTWARE, {"bilby", "BILBY", "bilby_pipe"})
        validate_supported_software()

        invalid_values = [set(), frozenset({"bilby"}), {"bilby", ""}, {"bilby", 1}]
        for value in invalid_values:
            with self.subTest(value=value):
                with patch("bilby_children.SUPPORTED_BILBY_SOFTWARE", value):
                    with self.assertRaises(SystemExit) as raised:
                        validate_supported_software()
                    self.assertEqual(raised.exception.code, 1)

    def test_tf_1_to_9_role_selection_matrix(self):
        for role, array_name, output_name, required in (
            ("config", "input_files", "config_file", True),
            ("result", "output_files", "result_file", False),
            ("pesummary", "output_files", "pesummary_result_file", False),
        ):
            with self.subTest(role=role, count=0):
                detail = self.detail()
                analysis = detail["analyses"][0]
                analysis[array_name] = [item for item in analysis[array_name] if item["role"] != role]
                selected, rejected = self.select(detail)
                if required:
                    self.assertEqual((selected, rejected), ([], []))
                else:
                    self.assertEqual(rejected, [])
                    self.assertIsNone(selected[0][output_name])

            with self.subTest(role=role, count=1):
                detail = self.detail()
                analysis = detail["analyses"][0]
                relationship = self.relationship(role, f"/ozstar/{role}.dat")
                relationship["direction"] = "input" if required else "output"
                analysis[array_name] = [item for item in analysis[array_name] if item["role"] != role] + [relationship]
                selected, rejected = self.select(detail)
                self.assertEqual(rejected, [])
                self.assertEqual(selected[0][output_name]["path"], f"/ozstar/{role}.dat")

            with self.subTest(role=role, count=2):
                detail = self.detail()
                analysis = detail["analyses"][0]
                relationship = self.relationship(role, f"/ozstar/{role}.dat")
                relationship["direction"] = "input" if required else "output"
                analysis[array_name] = [copy.deepcopy(relationship), copy.deepcopy(relationship)]
                selected, rejected = self.select(detail)
                self.assertEqual(selected, [])
                self.assertEqual(len(rejected), 1)
                self.assertEqual(rejected[0].role, role)

    def test_tf_wrong_case_and_filename_do_not_match(self):
        for role in ("Config", "RESULT"):
            with self.subTest(role=role):
                detail = self.detail()
                analysis = detail["analyses"][0]
                analysis["input_files"][0]["role"] = role
                analysis["input_files"][0]["file"]["name"] = "config.ini"
                self.assertEqual(self.select(detail), ([], []))

    def test_tf_optional_inaccessible_is_null_and_warned(self):
        detail = self.detail()
        analysis = detail["analyses"][0]
        analysis["output_files"] = [self.relationship("result", "/remote/result.h5", file_system="REMOTE")]
        with self.assertLogs("gwflow_ingest.bilby_children", level="WARNING") as logs:
            selected, rejected = self.select(detail)
        self.assertEqual(rejected, [])
        self.assertIsNone(selected[0]["result_file"])
        self.assertIn("role=result", "\n".join(logs.output))
        self.assertIn("REMOTE", "\n".join(logs.output))

    def test_tl_1_to_7_accessible_location_ordering(self):
        cases = [
            (
                "TL-1 rank beats path",
                [
                    {"file_system": "CIT", "path": "/a", "url": None},
                    {"file_system": "OzStar", "path": "/z", "url": None},
                ],
                self.file_systems,
                "/z",
                False,
            ),
            (
                "TL-2 path tie-break",
                [
                    {"file_system": "OzStar", "path": "/m/2", "url": None},
                    {"file_system": "OzStar", "path": "/m/1", "url": None},
                ],
                self.file_systems,
                "/m/1",
                False,
            ),
            (
                "TL-3 url tie-break",
                [
                    {"file_system": "OzStar", "path": "/m/1", "url": "https://h/2"},
                    {"file_system": "OzStar", "path": "/m/1", "url": "https://h/1"},
                ],
                self.file_systems,
                "/m/1",
                False,
            ),
            (
                "TL-4 unconfigured",
                [{"file_system": "REMOTE", "path": "/remote", "url": None}],
                self.file_systems,
                None,
                True,
            ),
            (
                "TL-5 empty path",
                [
                    {"file_system": "OzStar", "path": "", "url": None},
                    {"file_system": "CIT", "path": "/cit", "url": None},
                ],
                self.file_systems,
                "/cit",
                False,
            ),
            (
                "TL-6 whitespace path",
                [
                    {"file_system": "OzStar", "path": "   ", "url": None},
                    {"file_system": "CIT", "path": "/cit", "url": None},
                ],
                self.file_systems,
                "/cit",
                False,
            ),
            (
                "TL-7 empty configured tuple",
                [{"file_system": "OzStar", "path": "/ozstar", "url": None}],
                (),
                None,
                True,
            ),
        ]
        for name, locations, file_systems, expected, rejected_expected in cases:
            with self.subTest(name=name):
                detail = self.detail()
                detail["analyses"][0]["input_files"][0]["file"]["locations"] = locations
                selected, rejected = self.select(detail, file_systems)
                self.assertEqual(bool(rejected), rejected_expected)
                if expected is not None:
                    self.assertEqual(selected[0]["config_file"]["path"], expected)

        detail = self.detail()
        locations = detail["analyses"][0]["input_files"][0]["file"]["locations"]
        first = self.select(detail)
        locations.reverse()
        second = self.select(detail)
        self.assertEqual(first, second)

    def test_tc_1_to_4_checksum_translation(self):
        for checksum in ("abc", None):
            with self.subTest(checksum=checksum):
                detail = self.detail()
                detail["analyses"][0]["input_files"][0]["file"]["md5sum"] = checksum
                selected, rejected = self.select(detail)
                self.assertEqual(rejected, [])
                self.assertEqual(selected[0]["config_file"]["md5_sum"], checksum)
                self.assertNotIn("md5sum", selected[0]["config_file"])

        for wrong_key in ("md5_sum", "checksum"):
            with self.subTest(wrong_key=wrong_key):
                detail = self.detail()
                file_data = detail["analyses"][0]["input_files"][0]["file"]
                checksum = file_data.pop("md5sum")
                file_data[wrong_key] = checksum
                selected, rejected = self.select(detail)
                self.assertEqual(selected, [])
                self.assertEqual(len(rejected), 1)
                self.assertIn("md5sum", rejected[0].reason)

    def test_td_1_to_3_deterministic_rerun_and_ordering(self):
        detail = self.detail()
        analysis = detail["analyses"][0]
        analysis["output_files"].append(self.relationship("pesummary", "/ozstar/summary.html", md5sum=None))
        first = self.select(detail)
        second = self.select(copy.deepcopy(detail))
        self.assertEqual(first, second)

        shuffled = copy.deepcopy(detail)
        random.Random(117).shuffle(shuffled["analyses"][0]["input_files"][0]["file"]["locations"])
        random.Random(118).shuffle(shuffled["analyses"][0]["output_files"])
        self.assertEqual(first, self.select(shuffled))

        selected, rejected = first
        self.assertEqual(rejected, [])
        self.assertEqual(selected[0]["result_file"]["path"], "/ozstar/S000001a/pe_1_result.hdf5")
        self.assertEqual(selected[0]["pesummary_result_file"]["path"], "/ozstar/summary.html")

    def test_tr_1_rejection_fields(self):
        detail = self.detail()
        detail["analyses"][0]["input_files"][0]["file"]["locations"] = [
            {"file_system": "REMOTE_B", "path": "/b", "url": None},
            {"file_system": "REMOTE_A", "path": "/a", "url": None},
        ]
        selected, rejected = self.select(detail)
        self.assertEqual(selected, [])
        self.assertEqual(
            rejected,
            [
                Rejection(
                    sname="S000001a",
                    analysis_uid="pe_1",
                    role="config",
                    available_file_systems=("REMOTE_A", "REMOTE_B"),
                    reason="no accessible location",
                    index=0,
                )
            ],
        )

    def test_tr_2_uidless_row_fail_key(self):
        detail = self.detail()
        detail["analyses"] = [{"type": "pe"}]
        selected, rejected = self.select(detail)
        self.assertEqual(selected, [])
        self.assertEqual(rejected[0].fail_key, "bilby:S000001a/analyses[0]")

    def test_tr_3_rejection_is_frozen(self):
        rejection = Rejection("S1", "pe_1", "config", (), "reason")
        with self.assertRaises(FrozenInstanceError):
            rejection.reason = "changed"

    def test_detail_shape_safety_net(self):
        for detail in (None, {}, {"analyses": None}):
            with self.subTest(detail=detail):
                selected, rejected = select_bilby_analyses(
                    "S000001a",
                    detail,
                    self.file_systems,
                )
                self.assertEqual(selected, [])
                self.assertEqual(len(rejected), 1)
                self.assertEqual(rejected[0].reason, "detail analyses must be an array")


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

    def test_backslash_in_name_treated_literally(self):
        text = "label = old\nfoo = bar\n"
        self.assertEqual(_set_ini_label(text, "S1--a\\1b"), "label = S1--a\\1b\nfoo = bar\n")


class TestIniOutdir(unittest.TestCase):
    def test_empty_ini_returns_none(self):
        self.assertIsNone(_ini_outdir(""))
        self.assertIsNone(_ini_outdir(None))

    def test_malformed_ini_returns_none(self):
        self.assertIsNone(_ini_outdir("[unclosed\noutdir = /data"))

    def test_no_outdir_option_returns_none(self):
        ini = "[default]\nlabel = job\nfoo = bar\n"
        self.assertIsNone(_ini_outdir(ini))

    def test_relative_outdir_returns_none(self):
        ini = "[default]\noutdir = relative/path\n"
        self.assertIsNone(_ini_outdir(ini))

    def test_absolute_outdir_returned(self):
        ini = "[default]\noutdir = /data/out\n"
        self.assertEqual(_ini_outdir(ini), "/data/out")

    def test_absolute_outdir_in_later_section_returned(self):
        ini = "[default]\nfoo = bar\n[pe]\noutdir = /data/pe\n"
        self.assertEqual(_ini_outdir(ini), "/data/pe")

    def test_percent_in_value_not_treated_as_interpolation(self):
        ini = "[default]\noutdir = /data/%s/out\n"
        self.assertEqual(_ini_outdir(ini), "/data/%s/out")


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

    def test_is_preferred_string_upper(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5, "is_preferred": "TRUE"},
                ]
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))

    def test_is_preferred_numeric_one(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5, "is_preferred": "1"},
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

    def test_preferred_field_yes_upper(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1234567890.5},
                    {"uid": "EVT-B", "gps_time": 1111111111.0, "preferred": "Yes"},
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

    def test_boolean_gps_returns_none(self):
        detail = {"gracedb": {"events": [{"uid": "EVT-A", "gps_time": True}]}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_nan_gps_returns_none(self):
        detail = {"gracedb": {"events": [{"uid": "EVT-A", "gps_time": "nan"}]}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_inf_gps_returns_none(self):
        detail = {"gracedb": {"events": [{"uid": "EVT-A", "gps_time": "inf"}]}}
        self.assertIsNone(resolve_event_id_for("S1", detail))

    def test_oversized_integer_gps_returns_none(self):
        detail = {"gracedb": {"events": [{"uid": "EVT-A", "gps_time": 10**400}]}}
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

    def test_state_preferred_selects_correct_event(self):
        events = [{"uid": f"EVT-{i}", "gps_time": 1000.0 + i, "state": "neighbor"} for i in range(4)]
        events.append({"uid": "EVT-4", "gps_time": 1004.0, "state": "preferred"})
        detail = {"gracedb": {"events": events}}
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-4", 1004.0))

    def test_capitalized_state_preferred_selects_correct_event(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1000.0, "State": "neighbor"},
                    {"uid": "EVT-B", "gps_time": 2000.0, "State": "Preferred"},
                ],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-B", 2000.0))

    def test_state_preferred_takes_priority_over_first_event(self):
        detail = {
            "gracedb": {
                "events": [
                    {"uid": "EVT-A", "gps_time": 1000.0},
                    {"uid": "EVT-B", "gps_time": 2000.0},
                    {"uid": "EVT-C", "gps_time": 3000.0, "state": "preferred"},
                ],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-C", 3000.0))

    def test_preferred_uid_takes_priority_over_state(self):
        detail = {
            "gracedb": {
                "preferred_event": "EVT-B",
                "events": [
                    {"uid": "EVT-A", "gps_time": 1000.0, "state": "preferred"},
                    {"uid": "EVT-B", "gps_time": 2000.0, "state": "neighbor"},
                ],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-B", 2000.0))

    def test_UID_alias_in_preferred_uid_match(self):
        detail = {
            "gracedb": {
                "preferred_event": "EVT-A",
                "events": [
                    {"UID": "EVT-A", "gps_time": 1234567890.5},
                ],
            }
        }
        self.assertEqual(resolve_event_id_for("S1", detail), ("EVT-A", 1234567890.5))


def _canonical_file_relationship(role, path, *, direction, md5sum=""):
    return {
        "direction": direction,
        "role": role,
        "file": {
            "name": Path(path).name,
            "description": role,
            "md5sum": md5sum,
            "last_modified": None,
            "locations": [
                {
                    "file_system": "fs_a",
                    "path": path,
                    "url": None,
                }
            ],
        },
    }


def _bilby_analysis(
    uid="uid1",
    config_path="/data/pe/config.ini",
    result_path="/data/pe/result.h5",
    summary_path=None,
    software="bilby",
):
    input_files = []
    if config_path:
        input_files.append(
            _canonical_file_relationship(
                "config",
                config_path,
                direction="input",
            )
        )

    output_files = []
    if result_path:
        output_files.append(
            _canonical_file_relationship(
                "result",
                result_path,
                direction="output",
            )
        )
    if summary_path:
        output_files.append(
            _canonical_file_relationship(
                "pesummary",
                summary_path,
                direction="output",
            )
        )

    return {
        "uid": uid,
        "type": "pe",
        "status": "complete",
        "deprecated": False,
        "software": {"name": software},
        "configurations": [
            {
                "uid": f"{uid}:configuration",
                "type": "pe",
            }
        ],
        "input_files": input_files,
        "output_files": output_files,
    }


def _bilby_detail(sname="S1", analyses=None, gracedb=None):
    detail = {
        "sname": sname,
        "raw_payload": {"sname": sname},
        "analyses": analyses if analyses is not None else [],
    }
    if gracedb is not None:
        # Deferred resolve_event_id_for residue still consumes this legacy key.
        detail["gracedb"] = gracedb
    return detail


def _make_gwc(linked_uids=(), uploaded_id="job-id-1"):
    gwc = MagicMock()
    gwc.request.return_value = {
        "gwflow_linked_bilby_jobs": [
            {"id": f"linked-{index}", "gwflow_analysis_uid": uid} for index, uid in enumerate(linked_uids, start=1)
        ]
    }
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

    def test_event_id_created_after_structural_parent_link_without_identifier_child_link(self):
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

        gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded.id, sname, "uid1")
        gwc.create_event_id.assert_called_once_with("EVT-A", 1234567890.5, trigger_id=sname)
        self.assertLess(
            gwc.mock_calls.index(call.link_bilby_job_to_gwflow(uploaded.id, sname, "uid1")),
            gwc.mock_calls.index(call.create_event_id("EVT-A", 1234567890.5, trigger_id=sname)),
        )
        uploaded.set_event_id.assert_not_called()

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
        gwc.create_event_id.side_effect = RuntimeError("conflict: EVT-A belongs to another superevent")
        jc = MagicMock()

        with tempfile.TemporaryDirectory() as staging:
            with tempfile.TemporaryDirectory() as fetch_dir:
                ini = _write_fetch_files(fetch_dir, [("config.ini", "label = old\n")])[0]
                result = _write_fetch_files(fetch_dir, [("result.h5", b"x")])[0]

                with (
                    patch("gwflow_ingest.fetch_to_staging", side_effect=[ini, result]),
                    patch.object(settings, "STAGING_DIR", staging),
                    self.assertLogs("gwflow_ingest", level="WARNING") as logs,
                ):
                    phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        self.assertEqual(gwc.upload_job_archive.call_count, 1)
        gwc.link_bilby_job_to_gwflow.assert_called_once_with(uploaded.id, sname, "uid1")
        gwc.create_event_id.assert_called_once_with("EVT-A", 1234567890.5, trigger_id=sname)
        uploaded.set_event_id.assert_not_called()
        self.assertIn("event id creation failed", "\n".join(logs.output))
        self.assertIn("conflict: EVT-A belongs to another superevent", "\n".join(logs.output))

    def test_si_4a_unscoped_linked_read_prevents_duplicate_upload(self):
        sname = "S_HIDDEN_LINKED"
        detail = _bilby_detail(sname=sname, analyses=[_bilby_analysis(uid="uid-hidden")])
        self._seed_changed_sname(sname)

        portal = MagicMock()
        portal.get_superevent.return_value = detail
        gwc, _ = _make_gwc(linked_uids=("uid-hidden",))
        gwc.get_gwflow_job.return_value = MagicMock(bilby_jobs=[])
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()
        gwc.link_bilby_job_to_gwflow.assert_not_called()
        gwc.get_gwflow_job.assert_not_called()
        gwc.request.assert_called_once()

    def test_idempotent_rerun_skips_linked(self):
        sname = "S_IDEMP"
        analysis = _bilby_analysis(uid="uid1")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        self._seed_changed_sname(sname)
        portal = MagicMock()
        portal.get_superevent.return_value = detail

        gwc, _ = _make_gwc(linked_uids=("uid1",))
        jc = MagicMock()

        with patch.object(settings, "STAGING_DIR", tempfile.mkdtemp()):
            with patch("gwflow_ingest.fetch_to_staging") as mock_fetch:
                phase_bilby_children(portal_client=portal, gwc_client=gwc, jc=jc, con=self.con)

        mock_fetch.assert_not_called()
        gwc.upload_job_archive.assert_not_called()
        gwc.link_bilby_job_to_gwflow.assert_not_called()
        gwc.get_gwflow_job.assert_not_called()

    def test_stale_linked_child_row_cleared(self):
        sname = "S_STALE"
        analysis = _bilby_analysis(uid="uid1")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        cur = self.con.cursor()
        state.ensure_pending(self.con, cur, f"bilby:{sname}")
        state.record_failure(self.con, cur, f"bilby:{sname}/uid1", "link timeout", job_ref="orphan-1")

        portal = MagicMock()
        portal.get_superevent.return_value = detail

        gwc, _ = _make_gwc(linked_uids=("uid1",))
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
        gwc.get_gwflow_job.assert_not_called()

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
        analysis["input_files"] = []
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

    def test_missing_uid_rejected(self):
        sname = "S_NOUID"
        analysis = _bilby_analysis(uid="")
        detail = _bilby_detail(sname=sname, analyses=[analysis])

        selected, rejected = select_bilby_analyses(
            sname,
            detail,
            settings.ACCESSIBLE_FILE_SYSTEMS,
        )

        self.assertEqual(selected, [])
        self.assertTrue(rejected)
        self.assertIsNone(rejected[0].analysis_uid)
        self.assertIn("uid", rejected[0].reason)

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
                "record_timestamp": "2026-01-01T10:00:00Z",
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
            "analyses": [],
            "input_files": [],
            "output_files": [],
            "configurations": [],
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


class TestTreeRelativeTarget(unittest.TestCase):
    def test_absolute_path_stripped_to_relative(self):
        self.assertEqual(_tree_relative_target("/pe/config.ini"), "pe/config.ini")

    def test_relative_path_returned_as_is(self):
        self.assertEqual(_tree_relative_target("pe/config.ini"), "pe/config.ini")

    def test_empty_path_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("")
        with self.assertRaises(StageError):
            _tree_relative_target("/")

    def test_dot_only_path_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("/.")
        with self.assertRaises(StageError):
            _tree_relative_target(".")

    def test_nul_byte_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("pe/config\x00.ini")

    def test_parent_traversal_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("../escape.ini")
        with self.assertRaises(StageError):
            _tree_relative_target("pe/../../escape.ini")

    def test_reserved_top_level_data_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("data/x.h5")

    def test_reserved_top_level_result_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("result/result.hdf5")

    def test_reserved_top_level_results_page_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("results_page/index.html")

    def test_config_complete_ini_collision_raises(self):
        with self.assertRaises(StageError):
            _tree_relative_target("S1_config_complete.ini")

    def test_valid_nested_path_returned(self):
        self.assertEqual(_tree_relative_target("pe/extra/support.txt"), "pe/extra/support.txt")


if __name__ == "__main__":
    unittest.main()
