from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob, IniKeyValue
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.reindex import ReindexCounts, ReindexError

COMMAND = "bilbyui.management.commands.backfill_trigger_times"


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class TriggerTimeBackfillCommandTests(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()

    def make_bilby(self, name, trigger_time=None):
        return BilbyJob.objects.create(
            user=self.user,
            name=name,
            ini_string="",
            trigger_time=trigger_time,
        )

    def source(self, job, value, *, processed, index=0, key="trigger_time"):
        return IniKeyValue.objects.create(
            job=job,
            key=key,
            value=value,
            processed=processed,
            index=index,
        )

    def make_gwflow(self, sname, event=None, trigger_time=None):
        return GWFlowJob.objects.create(
            user=self.user,
            sname=sname,
            current_history_id=f"history-{sname}",
            event_id=event,
            trigger_time=trigger_time,
        )

    @staticmethod
    def metadata(value):
        return {
            "GraceDB": {
                "Events": [
                    {"State": "other", "GPSTime": 1.0},
                    {"State": "preferred", "GPSTime": value},
                ]
            }
        }

    def run_command(self, *args, portal=None):
        output = StringIO()
        portal = portal or (lambda _sname, _history: (self.metadata(100.0), "live"))
        with (
            mock.patch(f"{COMMAND}.get_version", side_effect=portal) as get_version,
            mock.patch(
                f"{COMMAND}.reindex_jobs",
                return_value=ReindexCounts(0, 0, 0),
            ) as reindex,
            mock.patch(f"{COMMAND}.verify_search_trigger_time") as verify,
        ):
            call_command("backfill_trigger_times", *args, stdout=output)
        return output.getvalue(), get_version, reindex, verify

    def test_dry_run_performs_no_database_or_es_writes(self):
        job = self.make_bilby("dry-run")
        self.source(job, "123.5", processed=True)

        output, _, reindex, verify = self.run_command(
            "--kind",
            "bilby",
        )

        job.refresh_from_db()
        self.assertIsNone(job.trigger_time)
        reindex.assert_not_called()
        verify.assert_not_called()
        self.assertIn("resolved=1", output)
        self.assertIn("updated=0", output)

    def test_bilby_apply_prefers_usable_processed_and_is_idempotent(self):
        job = self.make_bilby("matrix")
        rejected = self.source(job, "private-secret", processed=True, index=9)
        low = self.source(job, "120", processed=True, index=1)
        chosen = self.source(job, '"125.5"', processed=True, index=2)
        self.source(job, "999", processed=False, index=99)
        self.source(job, "222", processed=True, index=2)
        other_key = self.source(
            job,
            "888",
            processed=True,
            index=100,
            key="not_trigger_time",
        )

        with self.assertLogs(COMMAND, level="WARNING") as captured:
            _, _, reindex, verify = self.run_command("--kind", "bilby", "--apply")

        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 222.0)
        reindex.assert_called_once_with([job.id], "bilby")
        verify.assert_called_once_with("bilby")
        logs = "\n".join(captured.output)
        self.assertIn(f"source_row_id={rejected.id}", logs)
        self.assertNotIn("private-secret", logs)
        highest_id = IniKeyValue.objects.filter(job=job, value="222").get().id
        self.assertIn(
            f"source_row_ids={highest_id},{chosen.id},{low.id}",
            logs,
        )
        self.assertNotIn(str(other_key.id), logs)

        _, _, second_reindex, second_verify = self.run_command(
            "--kind",
            "bilby",
            "--apply",
        )
        second_reindex.assert_not_called()
        second_verify.assert_called_once_with("bilby")
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 222.0)

    def test_bilby_falls_back_to_raw_and_leaves_unresolved_null(self):
        fallback = self.make_bilby("fallback")
        unresolved = self.make_bilby("unresolved")
        self.source(fallback, "bad", processed=True)
        self.source(fallback, "42.25", processed=False)
        self.source(unresolved, "null", processed=True)

        output, _, reindex, _ = self.run_command("--kind", "bilby", "--apply")

        fallback.refresh_from_db()
        unresolved.refresh_from_db()
        self.assertEqual(fallback.trigger_time, 42.25)
        self.assertIsNone(unresolved.trigger_time)
        reindex.assert_called_once_with(
            [fallback.id, unresolved.id],
            "bilby",
        )
        self.assertIn("unresolved=1", output)

    def test_batch_boundaries_and_exclusive_resume(self):
        first = self.make_bilby("first")
        second = self.make_bilby("second")
        third = self.make_bilby("third")
        for job in (first, second, third):
            self.source(job, str(job.id + 100), processed=True)

        _, _, reindex, _ = self.run_command(
            "--kind",
            "bilby",
            "--batch",
            "1",
            "--after-id",
            str(first.id),
            "--apply",
        )

        self.assertEqual(
            reindex.call_args_list,
            [
                mock.call([second.id], "bilby"),
                mock.call([third.id], "bilby"),
            ],
        )
        first.refresh_from_db()
        self.assertIsNone(first.trigger_time)

    def test_non_null_rows_are_never_candidates_or_overwritten(self):
        existing = self.make_bilby("existing", trigger_time=77.0)
        self.source(existing, "999", processed=True)

        _, _, reindex, verify = self.run_command("--kind", "bilby", "--apply")

        existing.refresh_from_db()
        self.assertEqual(existing.trigger_time, 77.0)
        reindex.assert_not_called()
        verify.assert_called_once_with("bilby")

    def test_unresolved_candidate_is_reindexed_to_remove_stale_es_value(self):
        job = self.make_bilby("stale")
        self.source(job, "malformed", processed=True)

        _, _, reindex, _ = self.run_command("--kind", "bilby", "--apply")

        reindex.assert_called_once_with([job.id], "bilby")

    def test_reindex_failure_reports_previous_successful_cursor(self):
        first = self.make_bilby("page-one")
        second = self.make_bilby("page-two")
        self.source(first, "1", processed=True)
        self.source(second, "2", processed=True)
        output = StringIO()

        with (
            mock.patch(
                f"{COMMAND}.reindex_jobs",
                side_effect=[
                    ReindexCounts(1, 1, 0),
                    ReindexError("boom"),
                ],
            ),
            mock.patch(f"{COMMAND}.verify_search_trigger_time") as verify,
        ):
            with self.assertRaises(CommandError) as raised:
                call_command(
                    "backfill_trigger_times",
                    "--kind",
                    "bilby",
                    "--batch",
                    "1",
                    "--apply",
                    stdout=output,
                    stderr=output,
                )

        message = str(raised.exception)
        self.assertIn(f"last_fully_reindexed_id={first.id}", message)
        self.assertIn(f"failed_ids={second.id}", message)
        self.assertIn("es_reindex_reconcile", message)
        self.assertIn(f"--kind bilby --after-id {first.id}", message)
        self.assertNotIn("status=page_failed", message)
        verify.assert_not_called()
        second.refresh_from_db()
        self.assertEqual(second.trigger_time, 2.0)

    def test_write_page_classifies_every_resolution(self):
        successful = self.make_bilby("successful")
        conflict = self.make_bilby("conflict", trigger_time=999.0)
        same_value = self.make_bilby("same-value", trigger_time=20.0)
        deleted = self.make_bilby("deleted")
        deleted_id = deleted.id
        deleted.delete()

        command = __import__(COMMAND, fromlist=["Command"]).Command()
        updated, concurrent_ids, not_updated_ids, same_value_ids = command._write_page(
            "bilby",
            {
                successful.id: 10.0,
                conflict.id: 20.0,
                same_value.id: 20.0,
                deleted_id: 30.0,
            },
        )

        successful.refresh_from_db()
        self.assertEqual(successful.trigger_time, 10.0)
        self.assertEqual(updated, 1)
        self.assertEqual(concurrent_ids, [conflict.id])
        self.assertEqual(not_updated_ids, [deleted_id])
        self.assertEqual(same_value_ids, [same_value.id])
        self.assertEqual(
            updated + len(concurrent_ids) + len(not_updated_ids) + len(same_value_ids),
            4,
        )

    def test_write_page_same_value_keeps_pre_existing_lower_id_job(self):
        pre_existing = self.make_bilby("pre-existing", trigger_time=20.0)
        updated = self.make_bilby("updated", trigger_time=None)

        command = __import__(COMMAND, fromlist=["Command"]).Command()
        updated_count, concurrent_ids, not_updated_ids, same_value_ids = command._write_page(
            "bilby",
            {
                pre_existing.id: 20.0,
                updated.id: 20.0,
            },
        )

        updated.refresh_from_db()
        self.assertEqual(updated.trigger_time, 20.0)
        self.assertEqual(updated_count, 1)
        self.assertEqual(concurrent_ids, [])
        self.assertEqual(not_updated_ids, [])
        self.assertEqual(same_value_ids, [pre_existing.id])
        self.assertNotIn(updated.id, same_value_ids)

    def test_same_value_write_race_is_unchanged_not_concurrent(self):
        job = self.make_bilby("same-value-race")
        self.source(job, "10", processed=True)
        output = StringIO()

        with (
            mock.patch(
                f"{COMMAND}.Command._write_page",
                return_value=(0, [], [], [job.id]),
            ),
            mock.patch(
                f"{COMMAND}.reindex_jobs",
                return_value=ReindexCounts(0, 0, 0),
            ),
            mock.patch(f"{COMMAND}.verify_search_trigger_time"),
        ):
            call_command(
                "backfill_trigger_times",
                "--kind",
                "bilby",
                "--apply",
                stdout=output,
                stderr=output,
            )

        emitted = output.getvalue()
        self.assertIn(f"same_value kind=bilby job_ids={job.id}", emitted)
        self.assertNotIn("concurrent_change", emitted)
        self.assertIn(
            "scanned=1 resolved=1 unresolved=0 unchanged=1 updated=0",
            emitted,
        )

    def test_verifier_failure_is_command_error(self):
        job = self.make_bilby("verify")
        self.source(job, "10", processed=True)

        with (
            mock.patch(
                f"{COMMAND}.reindex_jobs",
                return_value=ReindexCounts(1, 1, 0),
            ),
            mock.patch(
                f"{COMMAND}.verify_search_trigger_time",
                side_effect=ReindexError("verification failed"),
            ),
        ):
            with self.assertRaises(CommandError) as raised:
                call_command("backfill_trigger_times", "--kind", "bilby", "--apply")

        self.assertIn("status=verification_failed", str(raised.exception))

    def test_gwflow_resolution_matrix_and_portal_boundary(self):
        usable_event = EventID.objects.create(
            event_id="GW200101_010101",
            gps_time=11.0,
        )
        zero_event = EventID.objects.create(
            event_id="GW200102_010101",
            gps_time=0.0,
        )
        bad_sentinel = EventID.objects.create(
            event_id="GW200103_010101",
            gps_time=1126259462.391,
        )
        allowed_sentinel = EventID.objects.create(
            event_id="GW150914_000000",
            gps_time=1126259462.391,
        )
        jobs = [
            self.make_gwflow("S200101a", usable_event),
            self.make_gwflow("S200102a", zero_event),
            self.make_gwflow("S200103a", bad_sentinel),
            self.make_gwflow("S150914a", allowed_sentinel),
            self.make_gwflow("S200104a"),
        ]
        values = {
            "S200102a": 22.0,
            "S200103a": 33.0,
            "S200104a": None,
        }

        def portal(sname, history_id):
            self.assertEqual(history_id, f"history-{sname}")
            value = values[sname]
            metadata = self.metadata(value) if value is not None else {"GraceDB": {"Events": []}}
            return metadata, "live"

        _, get_version, reindex, verify = self.run_command(
            "--kind",
            "gwflow",
            "--apply",
            portal=portal,
        )

        for job in jobs:
            job.refresh_from_db()
        self.assertEqual(
            [job.trigger_time for job in jobs],
            [11.0, 22.0, 33.0, 1126259462.391, None],
        )
        self.assertEqual(
            [call.args[0] for call in get_version.call_args_list],
            ["S200102a", "S200103a", "S200104a"],
        )
        reindex.assert_called_once_with([job.id for job in jobs], "gwflow")
        verify.assert_called_once_with("gwflow")

    def test_gwflow_metadata_uses_existing_preferred_event_semantics(self):
        job = self.make_gwflow("S200105a")
        metadata = {
            "raw_payload": {
                "GraceDB": {
                    "Events": [
                        {"GPSTime": 40.0},
                        {"state": "preferred", "GPSTime": "41.5"},
                    ]
                }
            }
        }

        self.run_command(
            "--kind",
            "gwflow",
            "--apply",
            portal=lambda _sname, _history: (metadata, "live"),
        )

        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 41.5)

    def test_gwflow_metadata_markers_remain_unresolved(self):
        for index, marker in enumerate((0.0, 1126259462.391)):
            with self.subTest(marker=marker):
                job = self.make_gwflow(f"S20020{index + 6}a")
                self.run_command(
                    "--kind",
                    "gwflow",
                    "--apply",
                    portal=lambda _sname, _history, value=marker: (
                        self.metadata(value),
                        "live",
                    ),
                )

                job.refresh_from_db()
                self.assertIsNone(job.trigger_time)

    def test_gwflow_portal_failure_makes_page_atomic(self):
        first = self.make_gwflow("S200106a")
        second = self.make_gwflow("S200107a")

        def portal(sname, _history):
            if sname == first.sname:
                return self.metadata(61.0), "live"
            return None, "down"

        with (
            mock.patch(f"{COMMAND}.get_version", side_effect=portal),
            mock.patch(f"{COMMAND}.reindex_jobs") as reindex,
            mock.patch(f"{COMMAND}.verify_search_trigger_time") as verify,
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "backfill_trigger_times",
                    "--kind",
                    "gwflow",
                )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.trigger_time)
        self.assertIsNone(second.trigger_time)
        reindex.assert_not_called()
        verify.assert_not_called()

    def test_gwflow_malformed_outer_payload_makes_page_atomic(self):
        job = self.make_gwflow("S200108a")

        with self.assertRaises(CommandError):
            self.run_command(
                "--kind",
                "gwflow",
                portal=lambda _sname, _history: (["not", "mapping"], "live"),
            )

        job.refresh_from_db()
        self.assertIsNone(job.trigger_time)

    def test_direct_updates_do_not_call_model_save(self):
        bilby = self.make_bilby("no-save")
        self.source(bilby, "70", processed=True)

        with mock.patch.object(BilbyJob, "save", autospec=True) as save:
            self.run_command("--kind", "bilby", "--apply")

        save.assert_not_called()

    def test_invalid_batch_is_rejected(self):
        for value in ("0", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(CommandError):
                    call_command(
                        "backfill_trigger_times",
                        "--kind",
                        "bilby",
                        "--batch",
                        value,
                    )
