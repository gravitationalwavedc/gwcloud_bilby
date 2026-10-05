import io
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models.query import QuerySet

from bilbyui.management.commands.repair_eventid_gps_time import (
    _AGREEMENT_ABS_TOLERANCE,
    _SENTINEL,
    Command,
)
from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.testcases import BilbyTestCase

_COMMAND = "bilbyui.management.commands.repair_eventid_gps_time"


class TestRepairEventIDGPSTime(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()
        self.legitimate = self._event("GW150914_000000", _SENTINEL)
        self.test_one = self._event("GW111111_222222", 0.0)
        self.test_two = self._event("GW222222_111111", 0.0)

    def _event(self, name, gps_time):
        return EventID.objects.create(event_id=name, gps_time=gps_time)

    def _job(self, event, trigger_time, suffix):
        return BilbyJob.objects.create(
            user=self.user,
            name=f"repair-{event.id}-{suffix}",
            ini_string="",
            event_id=event,
            trigger_time=trigger_time,
        )

    def _run(self, **options):
        output = io.StringIO()
        call_command(
            "repair_eventid_gps_time",
            stdout=output,
            **options,
        )
        return output.getvalue()

    def _candidate(self, name="GW230101_010101"):
        return self._event(name, _SENTINEL)

    def _apply_without_production_guard(self, **options):
        with mock.patch(f"{_COMMAND}._precondition_failures", return_value=[]):
            return self._run(apply=True, **options)

    def test_cli_contract_and_default_dry_run(self):
        output = self._run()

        self.assertEqual(_AGREEMENT_ABS_TOLERANCE, 2.0)
        self.assertIn("mode=dry-run", output)
        self.assertIn("agreement_abs_tolerance=2.0 rel_tolerance=0", output)
        self.assertIn(
            "gwcloud:/home/lewis/eventid_backup_20260929-040906.sql",
            output,
        )
        parser = Command().create_parser("manage.py", "repair_eventid_gps_time")
        with self.assertRaises(CommandError):
            parser.parse_args(["--dry-run", "--apply"])
        with self.assertRaises(CommandError):
            self._run(batch=0)
        with self.assertRaises(CommandError):
            self._run(after_id=-1)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_dry_run_reports_candidates_and_writes_nothing(self, reindex):
        candidate = self._candidate()
        usable = self._job(candidate, 100.0, "usable")
        rejected = self._job(candidate, None, "rejected")

        with mock.patch(f"{_COMMAND}._precondition_failures", return_value=[]):
            output = self._run(dry_run=True)

        candidate.refresh_from_db()
        self.assertEqual(candidate.gps_time, _SENTINEL)
        reindex.assert_not_called()
        self.assertIn(f"id={candidate.id} event_id={candidate.event_id}", output)
        self.assertIn("child_count=2 usable_count=1", output)
        self.assertIn("action=SET_VALUE value=100.0", output)
        self.assertIn(
            f"kind=event-repair child_job_id={rejected.id} "
            "reason=non_finite_child_trigger",
            output,
        )
        self.assertNotIn("source_row_id", output)
        self.assertNotIn("raw_value", output)
        self.assertIn(str(usable.id), str(usable.id))

    def test_dry_run_reports_precondition_drift_without_aborting(self):
        self.test_one.delete()

        output = self._run(dry_run=True)

        self.assertIn(
            "precondition_failed check=test_row "
            "name=GW111111_222222 expected=0.0 observed=missing",
            output,
        )
        self.legitimate.refresh_from_db()
        self.assertEqual(self.legitimate.gps_time, _SENTINEL)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_apply_uses_minimum_and_reindexes_changed_event(self, reindex):
        candidate = self._candidate()
        self._job(candidate, 101.5, "later")
        self._job(candidate, 100.0, "minimum")

        output = self._apply_without_production_guard()

        candidate.refresh_from_db()
        self.assertEqual(candidate.gps_time, 100.0)
        reindex.assert_called_once_with(candidate.id)
        self.assertIn("set_value=1", output)
        self.assertIn("applied=1", output)
        self.assertIn("reindexed=1", output)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_exact_two_second_boundary_agrees(self, reindex):
        candidate = self._candidate()
        self._job(candidate, 200.0, "minimum")
        self._job(candidate, 202.0, "boundary")

        self._apply_without_production_guard()

        candidate.refresh_from_db()
        self.assertEqual(candidate.gps_time, 200.0)
        reindex.assert_called_once_with(candidate.id)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_conflict_over_two_seconds_sets_null(self, reindex):
        candidate = self._candidate()
        first = self._job(candidate, 200.0, "minimum")
        second = self._job(candidate, 202.000001, "conflict")

        output = self._apply_without_production_guard()

        candidate.refresh_from_db()
        self.assertIsNone(candidate.gps_time)
        self.assertIn("reason=conflicting_child_triggers", output)
        self.assertIn(f"child_ids={second.id}", output)
        self.assertNotIn(f"child_ids={first.id},", output)
        reindex.assert_called_once_with(candidate.id)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_no_evidence_sets_null(self, reindex):
        candidate = self._candidate()
        rejected = self._job(candidate, None, "none")

        output = self._apply_without_production_guard()

        candidate.refresh_from_db()
        self.assertIsNone(candidate.gps_time)
        self.assertIn("reason=no_recoverable_child_trigger", output)
        self.assertIn(f"child_job_id={rejected.id}", output)
        self.assertNotIn("source_row_id", output)
        reindex.assert_called_once_with(candidate.id)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_legitimate_prefix_is_retained(self, reindex):
        prefix = self._candidate("GW150914_123456")
        self._job(prefix, 900.0, "ignored")

        output = self._apply_without_production_guard()

        prefix.refresh_from_db()
        self.legitimate.refresh_from_db()
        self.assertEqual(prefix.gps_time, _SENTINEL)
        self.assertEqual(self.legitimate.gps_time, _SENTINEL)
        self.assertIn("action=KEEP_LEGITIMATE", output)
        reindex.assert_not_called()

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_apply_is_idempotent(self, reindex):
        candidate = self._candidate()
        self._job(candidate, 300.0, "only")

        self._apply_without_production_guard()
        reindex.reset_mock()
        output = self._apply_without_production_guard()

        candidate.refresh_from_db()
        self.assertEqual(candidate.gps_time, 300.0)
        reindex.assert_not_called()
        self.assertIn("applied=0", output)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_event_save_is_never_called_and_queryset_update_is_used(self, reindex):
        candidate = self._candidate()
        self._job(candidate, 400.0, "only")
        original_update = QuerySet.update

        with (
            mock.patch.object(EventID, "save", side_effect=AssertionError("save called")),
            mock.patch.object(
                QuerySet,
                "update",
                autospec=True,
                side_effect=lambda queryset, **kwargs: original_update(
                    queryset,
                    **kwargs,
                ),
            ) as update,
        ):
            self._apply_without_production_guard()

        self.assertTrue(update.called)
        candidate.refresh_from_db()
        self.assertEqual(candidate.gps_time, 400.0)
        reindex.assert_called_once_with(candidate.id)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_batch_after_id_and_reindex_order(self, reindex):
        first = self._candidate("GW230101_010101")
        second = self._candidate("GW230102_010101")
        third = self._candidate("GW230103_010101")
        for number, event in enumerate((first, second, third), start=1):
            self._job(event, 500.0 + number, str(number))

        self._apply_without_production_guard(batch=1, after_id=first.id)

        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(first.gps_time, _SENTINEL)
        self.assertEqual(second.gps_time, 502.0)
        self.assertEqual(third.gps_time, 503.0)
        self.assertEqual(
            reindex.call_args_list,
            [mock.call(second.id), mock.call(third.id)],
        )

    @mock.patch(
        f"{_COMMAND}.reindex_affected_event",
        side_effect=[None, RuntimeError("ES unavailable")],
    )
    def test_reindex_failure_reports_last_fully_reindexed_cursor(self, reindex):
        first = self._candidate("GW230101_010101")
        second = self._candidate("GW230102_010101")
        self._job(first, 600.0, "first")
        self._job(second, 601.0, "second")

        with self.assertRaises(CommandError) as raised:
            self._apply_without_production_guard(batch=2)

        message = str(raised.exception)
        self.assertIn(f"failed_event_id={second.id}", message)
        self.assertIn(f"last_fully_reindexed_id={first.id}", message)
        self.assertIn("--after-id resumes DB repair only", message)
        self.assertIn("es_reindex_reconcile --kind bilby", message)
        self.assertIn("es_reindex_reconcile --kind gwflow", message)
        self.assertIn("Issue #112 full-corpus reindex", message)
        self.assertNotIn("resume_with=--after-id", message)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.gps_time, 600.0)
        self.assertEqual(second.gps_time, 601.0)
        self.assertEqual(
            reindex.call_args_list,
            [mock.call(first.id), mock.call(second.id)],
        )

    def test_multiple_sentinels_abort_before_write(self):
        candidate = self._candidate()
        self._job(candidate, 700.0, "only")

        with (
            mock.patch.object(QuerySet, "update") as update,
            self.assertRaisesMessage(CommandError, "check=sole_sentinel"),
        ):
            self._run(apply=True)

        update.assert_not_called()
        candidate.refresh_from_db()
        self.assertEqual(candidate.gps_time, _SENTINEL)

    def test_wrong_sentinel_identity_aborts_before_write(self):
        EventID.objects.filter(pk=self.legitimate.pk).update(gps_time=1.0)
        wrong = self._candidate()

        with self.assertRaisesMessage(CommandError, "check=sentinel_identity"):
            self._run(apply=True)

        wrong.refresh_from_db()
        self.assertEqual(wrong.gps_time, _SENTINEL)

    def test_missing_legitimate_row_aborts_before_write(self):
        self.legitimate.delete()

        with self.assertRaisesMessage(CommandError, "check=legitimate_row"):
            self._run(apply=True)

    def test_missing_test_row_aborts_before_write(self):
        self.test_one.delete()

        with self.assertRaisesMessage(
            CommandError,
            "name=GW111111_222222 expected=0.0 observed=missing",
        ):
            self._run(apply=True)

    def test_zero_drifted_test_row_aborts_before_write(self):
        EventID.objects.filter(pk=self.test_two.pk).update(gps_time=1.0)

        with self.assertRaisesMessage(
            CommandError,
            "name=GW222222_111111 expected=0.0 observed=1.0",
        ):
            self._run(apply=True)

    @mock.patch(f"{_COMMAND}.reindex_affected_event")
    def test_exact_production_preconditions_permit_apply(self, reindex):
        output = self._run(apply=True)

        self.legitimate.refresh_from_db()
        self.assertEqual(self.legitimate.gps_time, _SENTINEL)
        self.assertIn("kept=1", output)
        self.assertIn("applied=0", output)
        reindex.assert_not_called()
