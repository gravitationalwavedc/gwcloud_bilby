from datetime import UTC, datetime
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import override_settings

from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY
from bilbyui.tests.testcases import BilbyTestCase

PORTAL_SETTINGS = {
    "CBCFLOW_PORTAL_URL": "https://portal.example.com",
    "CBCFLOW_PORTAL_TOKEN": "token",
}

TS = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


def current_version(libraries=None, commit_sha="sha1", commit_timestamp=TS, is_current=True):
    return {
        "libraries": libraries if libraries is not None else ["cbc-workflow-o4a"],
        "commit_sha": commit_sha,
        "commit_timestamp": commit_timestamp,
        "is_current": is_current,
    }


def versions(*version_dicts):
    return list(version_dicts)


def make_job(sname="S230601ag", libraries=None, **kwargs):
    return GWFlowJob.objects.create(
        sname=sname,
        user_id=1,
        libraries=libraries if libraries is not None else [],
        **kwargs,
    )


@override_settings(IGNORE_ELASTIC_SEARCH=True, **PORTAL_SETTINGS)
class GwflowEsBackfillCommandTestCase(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()

    def setUp(self):
        cache.clear()

    def _run(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()
        with mock.patch("bilbyui.management.commands.gwflow_es_backfill.get_versions") as m:
            m.side_effect = kwargs.pop("get_versions_side_effect", None)
            m.return_value = kwargs.pop("get_versions_return", (versions(current_version()), "live"))
            try:
                exit_code = call_command(
                    "gwflow_es_backfill", *args, stdout=out, stderr=err, **kwargs
                )
            except CommandError as e:
                exit_code = e.returncode
        return exit_code, out.getvalue(), err.getvalue()

    def test_populated_libraries_persisted(self):
        job = make_job()
        self._run()
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["cbc-workflow-o4a"])
        self.assertEqual(job.current_history_id, "sha1")
        self.assertEqual(job.current_history_timestamp, TS)

    def test_empty_libraries_persisted(self):
        job = make_job()
        self._run(get_versions_return=(versions(current_version(libraries=[])), "live"))
        job.refresh_from_db()
        self.assertEqual(job.libraries, [])

    def test_whitespace_only_values_dropped(self):
        job = make_job()
        self._run(
            get_versions_return=(
                versions(current_version(libraries=["lib", "   ", "\t", ""])),
                "live",
            )
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["lib"])

    def test_values_are_trimmed(self):
        job = make_job()
        self._run(
            get_versions_return=(versions(current_version(libraries=[" lib "])), "live")
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["lib"])

    def test_non_string_values_dropped(self):
        job = make_job()
        self._run(
            get_versions_return=(
                versions(current_version(libraries=["lib", 123, None, {"a": 1}])),
                "live",
            )
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["lib"])

    def test_order_preserved(self):
        job = make_job()
        self._run(
            get_versions_return=(versions(current_version(libraries=["b", "a", "c"])), "live")
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["b", "a", "c"])

    def test_changed_membership_updates_libraries(self):
        job = make_job(libraries=["old-lib"])
        self._run(
            get_versions_return=(
                versions(current_version(libraries=["new-lib", "kept"])),
                "live",
            )
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["new-lib", "kept"])

    def test_removed_membership_removes_stale_libraries(self):
        job = make_job(libraries=["stale-lib", "kept"])
        self._run(
            get_versions_return=(versions(current_version(libraries=["kept"])), "live")
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["kept"])

    def test_null_timestamp_when_no_current_version(self):
        job = make_job(libraries=["old"])
        self._run(
            get_versions_return=(
                versions(current_version(is_current=False, commit_timestamp=TS)),
                "live",
            )
        )
        job.refresh_from_db()
        self.assertIsNone(job.current_history_timestamp)
        self.assertEqual(job.current_history_id, "")
        self.assertEqual(job.libraries, [])

    def test_valid_timestamp_persisted(self):
        job = make_job()
        self._run(
            get_versions_return=(
                versions(current_version(commit_timestamp="2024-01-01T12:00:00")),
                "live",
            )
        )
        job.refresh_from_db()
        self.assertEqual(job.current_history_timestamp, TS)

    def test_malformed_timestamp_becomes_null(self):
        job = make_job()
        self._run(
            get_versions_return=(
                versions(current_version(commit_timestamp="not-a-date")),
                "live",
            )
        )
        job.refresh_from_db()
        self.assertIsNone(job.current_history_timestamp)

    def test_idempotent(self):
        job = make_job()
        self._run()
        self._run()
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["cbc-workflow-o4a"])
        self.assertEqual(job.current_history_id, "sha1")

    def test_pruned_row_keeps_last_known_libraries(self):
        job = make_job(libraries=["last-known"], is_pruned=True)
        self._run(
            get_versions_return=(versions(current_version(libraries=["new"])), "live")
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, ["last-known"])

    def test_cache_invalidation_after_successful_backfill(self):
        make_job()
        cache.set(LIBRARIES_CACHE_KEY, ["x"])
        cache.set(REVIEW_STATUSES_CACHE_KEY, ["y"])
        self._run()
        self.assertIsNone(cache.get(LIBRARIES_CACHE_KEY))
        self.assertIsNone(cache.get(REVIEW_STATUSES_CACHE_KEY))

    def test_cache_not_invalidated_on_dry_run(self):
        make_job()
        cache.set(LIBRARIES_CACHE_KEY, ["x"])
        cache.set(REVIEW_STATUSES_CACHE_KEY, ["y"])
        self._run("--dry-run")
        self.assertEqual(cache.get(LIBRARIES_CACHE_KEY), ["x"])
        self.assertEqual(cache.get(REVIEW_STATUSES_CACHE_KEY), ["y"])

    def test_dry_run_does_not_write_db(self):
        job = make_job(libraries=[])
        self._run("--dry-run")
        job.refresh_from_db()
        self.assertEqual(job.libraries, [])
        self.assertEqual(job.current_history_id, "")
        self.assertIsNone(job.current_history_timestamp)

    def test_dry_run_does_not_print_resume_checkpoint(self):
        """Dry-run commits no batch, so no resume checkpoint is printed."""
        make_job(sname="S230601ag")
        _, out, _ = self._run("--dry-run")
        self.assertNotIn("Last completed job ID:", out)

    def test_resume_from_skips_lower_ids(self):
        job1 = make_job(sname="S230601ag")
        job2 = make_job(sname="S230602ag")

        def side_effect(sname):
            if sname == "S230601ag":
                return versions(current_version(libraries=["one"])), "live"
            return versions(current_version(libraries=["two"])), "live"

        self._run("--resume-from", str(job1.id), get_versions_side_effect=side_effect)
        job1.refresh_from_db()
        job2.refresh_from_db()
        self.assertEqual(job1.libraries, [])
        self.assertEqual(job2.libraries, ["two"])

    def test_portal_down_records_failure_and_returns_1(self):
        job = make_job()
        exit_code, _, err = self._run(
            get_versions_return=(None, "down"),
        )
        job.refresh_from_db()
        self.assertEqual(job.libraries, [])
        self.assertEqual(exit_code, 1)
        self.assertIn("Permanent failure", err)

    def test_config_missing_returns_2(self):
        make_job()
        out = StringIO()
        err = StringIO()
        with override_settings(CBCFLOW_PORTAL_URL=None, CBCFLOW_PORTAL_TOKEN=None):
            with self.assertRaises(CommandError) as ctx:
                call_command("gwflow_es_backfill", stdout=out, stderr=err)
        self.assertEqual(ctx.exception.returncode, 2)
        self.assertIn("must be configured", err.getvalue())

    def test_batch_size_above_max_returns_2(self):
        out = StringIO()
        err = StringIO()
        with self.assertRaises(CommandError) as ctx:
            call_command("gwflow_es_backfill", "--batch-size", "5000", stdout=out, stderr=err)
        self.assertEqual(ctx.exception.returncode, 2)
        self.assertIn("must be between 1 and 2000", err.getvalue())

    def test_prints_last_completed_job_id(self):
        make_job(sname="S230601ag")
        make_job(sname="S230602ag")
        _, out, _ = self._run()
        self.assertIn("Last completed job ID:", out)
