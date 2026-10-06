import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase

COMMAND = "bilbyui.management.commands.es_policy_validate"


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class EsPolicyValidateCommandTestCase(BilbyTestCase):
    def _field(self, failures=0):
        return SimpleNamespace(checked=10, failures=failures)

    def _visibility(self, ok=True):
        return SimpleNamespace(
            ok=ok,
            orm_public=8,
            es_public=8 if ok else 7,
            missing_in_es=[] if ok else [3],
            extra_in_es=[],
            classes={
                "equal": 1,
                "below": 5,
                "above": 0,
                "null_time": 1,
                "simulation": 1,
            },
        )

    def _shadow(self, ok=True):
        return SimpleNamespace(
            ok=ok,
            flag_drift=2,
            simulation=1,
            unknown_trigger=1,
            threshold_boundary=0,
            unexplained=0 if ok else 1,
            new_exposures=1,
            total_mismatches=4 if ok else 5,
        )

    def _run(self, *args, threshold=100.0, **kwargs):
        stdout = io.StringIO()
        with (
            mock.patch(f"{COMMAND}.collect_search_trigger_time_parity", return_value=self._field()) as field,
            mock.patch(f"{COMMAND}.collect_visibility_parity", return_value=self._visibility()) as visibility,
            mock.patch(f"{COMMAND}.collect_shadow_comparison", return_value=self._shadow()) as shadow,
            mock.patch(f"{COMMAND}.get_embargo_start", return_value=threshold) as embargo,
        ):
            try:
                code = call_command(
                    "es_policy_validate",
                    *args,
                    stdout=stdout,
                    **kwargs,
                )
            except CommandError as exc:
                code = exc.returncode
        return code, stdout.getvalue(), field, visibility, shadow, embargo

    def test_all_pass_exits_zero_and_all_runs_both_kinds(self):
        code, output, field, visibility, shadow, _ = self._run("--kind", "all")

        self.assertEqual(code, 0)
        self.assertEqual(
            field.call_args_list,
            [mock.call("bilby", batch=200), mock.call("gwflow", batch=200)],
        )
        self.assertEqual(
            visibility.call_args_list,
            [mock.call("bilby", 100.0, batch=200), mock.call("gwflow", 100.0, batch=200)],
        )
        self.assertEqual(shadow.call_count, 2)
        self.assertIn("bilby: field_parity=pass visibility_parity=pass shadow=pass", output)
        self.assertIn("gwflow: field_parity=pass visibility_parity=pass shadow=pass", output)

    def test_failed_check_sets_overall_fail_and_exits_one(self):
        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            stdout = io.StringIO()
            with (
                mock.patch(
                    f"{COMMAND}.collect_search_trigger_time_parity",
                    return_value=self._field(failures=1),
                ),
                mock.patch(
                    f"{COMMAND}.collect_visibility_parity",
                    return_value=self._visibility(),
                ),
                mock.patch(
                    f"{COMMAND}.collect_shadow_comparison",
                    return_value=self._shadow(),
                ),
            ):
                with self.assertRaises(CommandError) as caught:
                    call_command(
                        "es_policy_validate",
                        "--kind",
                        "bilby",
                        "--threshold",
                        "100",
                        "--report",
                        str(report_path),
                        stdout=stdout,
                    )
            report = json.loads(report_path.read_text())

        self.assertEqual(caught.exception.returncode, 1)
        self.assertEqual(report["overall"], "fail")
        self.assertIn("field_parity=fail", stdout.getvalue())

    def test_check_exception_is_reported_and_exits_one(self):
        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            with (
                mock.patch(
                    f"{COMMAND}.collect_search_trigger_time_parity",
                    side_effect=RuntimeError("ES unavailable"),
                ),
                mock.patch(f"{COMMAND}.collect_visibility_parity", return_value=self._visibility()),
                mock.patch(f"{COMMAND}.collect_shadow_comparison", return_value=self._shadow()),
            ):
                with self.assertRaises(CommandError) as caught:
                    call_command(
                        "es_policy_validate",
                        "--kind",
                        "bilby",
                        "--threshold",
                        "100",
                        "--report",
                        str(report_path),
                    )

            report = json.loads(report_path.read_text())
            self.assertEqual(caught.exception.returncode, 1)
            self.assertEqual(
                report["kinds"]["bilby"]["field_parity"],
                {"status": "error", "error": "ES unavailable"},
            )
            self.assertEqual(report["overall"], "fail")

    def test_invalid_batch_exits_two(self):
        for batch in (0, 201):
            with self.subTest(batch=batch):
                with self.assertRaises(CommandError) as caught:
                    call_command("es_policy_validate", "--batch", str(batch))
                self.assertEqual(caught.exception.returncode, 2)


    def test_non_finite_explicit_threshold_exits_two(self):
        for threshold in ("nan", "inf", "-inf"):
            with self.subTest(threshold=threshold):
                with self.assertRaisesRegex(CommandError, "--threshold must be finite") as caught:
                    call_command("es_policy_validate", f"--threshold={threshold}")
                self.assertEqual(caught.exception.returncode, 2)

    def test_kind_bilby_only_runs_bilby(self):
        code, _, field, visibility, shadow, _ = self._run(
            "--kind",
            "bilby",
            "--batch",
            "25",
        )

        self.assertEqual(code, 0)
        field.assert_called_once_with("bilby", batch=25)
        visibility.assert_called_once_with("bilby", 100.0, batch=25)
        shadow.assert_called_once_with("bilby", 100.0, batch=25)

    def test_explicit_threshold_is_used_without_fallback(self):
        code, _, _, visibility, shadow, embargo = self._run(
            "--kind",
            "bilby",
            "--threshold",
            "123.5",
        )

        self.assertEqual(code, 0)
        embargo.assert_not_called()
        visibility.assert_called_once_with("bilby", 123.5, batch=200)
        shadow.assert_called_once_with("bilby", 123.5, batch=200)

    def test_threshold_falls_back_to_embargo_start(self):
        code, _, _, visibility, shadow, embargo = self._run(
            "--kind",
            "bilby",
            threshold=456.0,
        )

        self.assertEqual(code, 0)
        embargo.assert_called_once_with()
        visibility.assert_called_once_with("bilby", 456.0, batch=200)
        shadow.assert_called_once_with("bilby", 456.0, batch=200)

    def test_unset_threshold_exits_two_without_running_checks(self):
        code, _, field, visibility, shadow, embargo = self._run(
            "--kind",
            "bilby",
            threshold=None,
        )

        self.assertEqual(code, 2)
        embargo.assert_called_once_with()
        field.assert_not_called()
        visibility.assert_not_called()
        shadow.assert_not_called()

    def test_report_writes_required_json_shape(self):
        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            code, _, _, _, _, _ = self._run(
                "--kind",
                "bilby",
                "--report",
                str(report_path),
                "--environment",
                "staging",
                "--release-id",
                "release-112",
            )
            report = json.loads(report_path.read_text())

        self.assertEqual(code, 0)
        self.assertEqual(
            set(report),
            {
                "environment",
                "release_id",
                "threshold",
                "timestamp",
                "indexes",
                "kinds",
                "overall",
            },
        )
        self.assertEqual(report["environment"], "staging")
        self.assertEqual(report["release_id"], "release-112")
        self.assertEqual(set(report["indexes"]), {"bilby", "gwflow"})
        self.assertEqual(set(report["kinds"]["bilby"]), {"field_parity", "visibility_parity", "shadow"})
        self.assertTrue(report["timestamp"].endswith("Z"))
        self.assertEqual(report["overall"], "pass")

    def test_json_prints_report_to_stdout(self):
        code, output, _, _, _, _ = self._run(
            "--kind",
            "bilby",
            "--json",
        )

        self.assertEqual(code, 0)
        json_start = output.index("{")
        report = json.loads(output[json_start:])
        self.assertEqual(report["overall"], "pass")
        self.assertEqual(set(report["kinds"]), {"bilby"})

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    def test_ignore_elastic_search_fails_without_running_checks(self):
        code, output, field, visibility, shadow, embargo = self._run("--kind", "all")

        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        field.assert_not_called()
        visibility.assert_not_called()
        shadow.assert_not_called()
        embargo.assert_not_called()

    def test_help_does_not_offer_skip_shadow(self):
        stdout = io.StringIO()
        with self.assertRaisesRegex(SystemExit, "0"):
            call_command("es_policy_validate", "--help", stdout=stdout)

        self.assertNotIn("--skip-shadow", stdout.getvalue())
