from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from bilbyui.models import GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase


class TestGWFlowESRetryCommand(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=20, primary_email="user20@example.com")

    def _make_job(self, sname="S230601ag", history_id="hist-001", age_hours=1):
        job = GWFlowJob.objects.create(
            sname=sname,
            user=self.user,
            current_history_id=history_id,
            current_history_timestamp=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
        )
        # Control last_updated (the ingest-update event the retry window is based
        # on). auto_now would overwrite it on save, so use a queryset update.
        GWFlowJob.objects.filter(pk=job.pk).update(last_updated=timezone.now() - timedelta(hours=age_hours))
        job.refresh_from_db()
        return job

    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command("gwflow_es_retry", *args, stdout=out, **kwargs)
        return out.getvalue()

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_process_termination_recovery(self, mock_update, mock_get_version):
        """A job whose DB commit succeeded but ES write never happened is recovered."""
        job = self._make_job()
        payload = {"ParameterEstimation": {"results": [{"uid": "pe-1", "review_status": "approved"}]}}
        mock_get_version.return_value = (payload, "live")

        output = self._run()

        mock_get_version.assert_called_once_with(job.sname, job.current_history_id)
        mock_update.assert_called_once()
        written_job, written_meta = mock_update.call_args.args
        self.assertEqual(written_job.id, job.id)
        self.assertEqual(written_meta, payload)
        self.assertIn("1 re-indexed, 0 skipped, 0 failed", output)

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_retry_after_newer_version(self, mock_update, mock_get_version):
        """Retry re-indexes the job's current (newer) authoritative version."""
        job = self._make_job(history_id="hist-002")
        newer_payload = {"ParameterEstimation": {"results": [{"uid": "pe-2", "review_status": "pending"}]}}
        mock_get_version.return_value = (newer_payload, "live")

        output = self._run()

        mock_get_version.assert_called_once_with(job.sname, "hist-002")
        mock_update.assert_called_once()
        self.assertEqual(mock_update.call_args.args[1], newer_payload)
        self.assertIn("1 re-indexed", output)

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_version_change_during_retry(self, mock_update, mock_get_version):
        """If the version tuple changes while the payload is fetched, skip the write."""
        job = self._make_job(history_id="hist-001")
        payload = {"ParameterEstimation": {"results": []}}
        mock_get_version.return_value = (payload, "live")

        def change_version(sname, sha):
            GWFlowJob.objects.filter(pk=job.pk).update(current_history_id="hist-002")
            return (payload, "live")

        mock_get_version.side_effect = change_version

        output = self._run()

        mock_update.assert_not_called()
        self.assertIn("skipped: version-changed", output)

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_exact_version_fetch_failure(self, mock_update, mock_get_version):
        """A portal fetch failure is recorded and no ES write occurs."""
        self._make_job()
        mock_get_version.return_value = (None, "down")

        with self.assertRaises(CommandError):
            self._run()

        mock_update.assert_not_called()

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_duplicate_delivery_idempotent(self, mock_update, mock_get_version):
        """Re-running the command writes idempotently by _id = job.id."""
        job = self._make_job()
        payload = {"ParameterEstimation": {"results": []}}
        mock_get_version.return_value = (payload, "live")

        self._run()
        self._run()

        self.assertEqual(mock_update.call_count, 2)
        for call in mock_update.call_args_list:
            self.assertEqual(call.args[0].id, job.id)
            self.assertEqual(call.args[1], payload)

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_hours_bounds_candidate_set(self, mock_update, mock_get_version):
        """Only jobs ingested within the --hours window are candidates."""
        recent = self._make_job(sname="S230601ag", age_hours=1)
        self._make_job(sname="S230601ah", age_hours=100)
        mock_get_version.return_value = ({"ParameterEstimation": {"results": []}}, "live")

        output = self._run("--hours", "24")

        self.assertEqual(mock_get_version.call_count, 1)
        mock_get_version.assert_called_once_with(recent.sname, recent.current_history_id)
        self.assertIn("1 re-indexed", output)

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_hours_includes_recently_updated_existing_job(self, mock_update, mock_get_version):
        """An old row whose ingest-update (last_updated) is recent is a candidate.

        Regression: candidate selection must be based on the ingest-update event
        (last_updated), not immutable row creation time (creation_time).
        """
        job = self._make_job(age_hours=100)
        GWFlowJob.objects.filter(pk=job.pk).update(last_updated=timezone.now())
        mock_get_version.return_value = ({"ParameterEstimation": {"results": []}}, "live")

        output = self._run("--hours", "24")

        mock_get_version.assert_called_once_with(job.sname, job.current_history_id)
        mock_update.assert_called_once()
        self.assertIn("1 re-indexed", output)

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_no_current_version_skipped(self, mock_update, mock_get_version):
        """A job with no current version is skipped without portal or ES calls."""
        self._make_job(history_id="")

        output = self._run()

        mock_get_version.assert_not_called()
        mock_update.assert_not_called()
        self.assertIn("skipped: no-current-version", output)

    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_invalid_metadata_fails(self, mock_update, mock_get_version):
        """Invalid metadata under #70 rules is recorded as a failure."""
        self._make_job()
        mock_get_version.return_value = ("not-an-object", "live")

        with self.assertRaises(CommandError):
            self._run()

        mock_update.assert_not_called()

    @override_settings(IGNORE_ELASTIC_SEARCH=False)
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.helpers.scan")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_es_client")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.get_version")
    @mock.patch("bilbyui.management.commands.gwflow_es_retry.gwflow_elastic_search_update")
    def test_no_doc_includes_missing(self, mock_update, mock_get_version, mock_es, mock_scan):
        """--no-doc adds jobs outside the hours window that have no ES document."""
        job = self._make_job(age_hours=100)
        mock_scan.return_value = iter([])
        mock_get_version.return_value = ({"ParameterEstimation": {"results": []}}, "live")

        output = self._run("--no-doc")

        mock_scan.assert_called_once()
        mock_get_version.assert_called_once_with(job.sname, job.current_history_id)
        self.assertIn("1 re-indexed", output)
