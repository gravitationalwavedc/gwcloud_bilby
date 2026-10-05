import io
import json
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError

from bilbyui.management.commands.cleanup_test_eventids import build_inventory
from bilbyui.models import (
    BilbyJob,
    EventID,
    GWFlowFile,
    GWFlowJob,
    SupportingFile,
)
from bilbyui.tests.testcases import BilbyTestCase


class TestCleanupTestEventIDs(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()
        self.first = EventID.objects.create(
            event_id="GW111111_222222",
            trigger_id="S111111a",
            nickname="test-one",
            gps_time=0.0,
        )
        self.second = EventID.objects.create(
            event_id="GW222222_111111",
            trigger_id="S222222a",
            nickname="test-two",
            gps_time=0.0,
        )
        self.direct_bilby = self._bilby("direct", event_id=self.first)
        self.direct_gwflow = GWFlowJob.objects.create(
            sname="S111111a",
            user=self.user,
            event_id=self.first,
        )
        self.gwflow_child = self._bilby("gwflow-child", gwflow_job=self.direct_gwflow)
        SupportingFile.objects.create(
            job=self.direct_bilby,
            file_type=SupportingFile.PRIOR,
            key="prior",
            file_name="prior.txt",
        )
        GWFlowFile.objects.create(
            job=self.direct_gwflow,
            path="result.hdf5",
            file_name="result.hdf5",
        )

    def _bilby(self, name, **kwargs):
        return BilbyJob.objects.create(
            user=self.user,
            name=name,
            ini_string="",
            **kwargs,
        )

    def _dry_run(self):
        output = io.StringIO()
        call_command("cleanup_test_eventids", stdout=output)
        digest = next(
            line.split("=", 1)[1] for line in output.getvalue().splitlines() if line.startswith("inventory_sha256=")
        )
        inventory_line = next(
            line.split("=", 1)[1] for line in output.getvalue().splitlines() if line.startswith("cleanup_inventory=")
        )
        return output.getvalue(), json.loads(inventory_line), digest

    def test_inventory_is_complete_and_dry_run_writes_nothing(self):
        before = {
            "events": EventID.objects.count(),
            "bilby": BilbyJob.objects.count(),
            "gwflow": GWFlowJob.objects.count(),
        }

        output, inventory, _digest = self._dry_run()

        target = inventory["targets"][0]
        self.assertEqual(target["event"]["id"], self.first.id)
        self.assertEqual(target["event"]["trigger_id"], "S111111a")
        self.assertEqual(target["event"]["nickname"], "test-one")
        self.assertEqual(target["event"]["gps_time"], 0.0)
        self.assertEqual(
            [row["id"] for row in target["direct_bilby_children"]],
            [self.direct_bilby.id],
        )
        self.assertEqual(
            [row["id"] for row in target["direct_gwflow_children"]],
            [self.direct_gwflow.id],
        )
        self.assertEqual(
            [row["id"] for row in target["gwflow_bilby_children"]],
            [self.gwflow_child.id],
        )
        self.assertEqual(
            target["direct_bilby_children"][0]["cascade_owned_counts"]["bilbyui.supportingfile"],
            1,
        )
        self.assertEqual(
            target["direct_gwflow_children"][0]["cascade_owned_counts"]["bilbyui.gwflowfile"],
            1,
        )
        self.assertIn("mode=dry-run writes=0 reindex=0", output)
        self.assertEqual(EventID.objects.count(), before["events"])
        self.assertEqual(BilbyJob.objects.count(), before["bilby"])
        self.assertEqual(GWFlowJob.objects.count(), before["gwflow"])

    def test_digest_is_deterministic(self):
        first_output, first_inventory, first_digest = self._dry_run()
        second_output, second_inventory, second_digest = self._dry_run()

        self.assertEqual(first_digest, second_digest)
        self.assertEqual(first_inventory, second_inventory)
        self.assertEqual(first_output, second_output)

    def test_digest_drift_aborts_without_mutation(self):
        _output, _inventory, digest = self._dry_run()
        self._bilby("late-child", event_id=self.second)

        with self.assertRaisesMessage(CommandError, "cleanup inventory changed"):
            call_command(
                "cleanup_test_eventids",
                apply=True,
                expected_inventory_sha256=digest,
            )

        self.assertTrue(EventID.objects.filter(pk=self.first.pk).exists())
        self.assertTrue(EventID.objects.filter(pk=self.second.pk).exists())

    @mock.patch("bilbyui.management.commands.cleanup_test_eventids.reindex_jobs")
    def test_default_apply_detaches_and_retains_all_children(self, reindex):
        _output, _inventory, digest = self._dry_run()

        call_command(
            "cleanup_test_eventids",
            apply=True,
            expected_inventory_sha256=digest,
        )

        self.assertFalse(EventID.objects.filter(pk=self.first.pk).exists())
        self.assertFalse(EventID.objects.filter(pk=self.second.pk).exists())
        self.direct_bilby.refresh_from_db()
        self.direct_gwflow.refresh_from_db()
        self.gwflow_child.refresh_from_db()
        self.assertIsNone(self.direct_bilby.event_id_id)
        self.assertIsNone(self.direct_gwflow.event_id_id)
        self.assertEqual(self.gwflow_child.gwflow_job_id, self.direct_gwflow.id)
        reindex.assert_has_calls(
            [
                mock.call(
                    sorted([self.direct_bilby.id, self.gwflow_child.id]),
                    "bilby",
                ),
                mock.call([self.direct_gwflow.id], "gwflow"),
            ]
        )

    @mock.patch("bilbyui.management.commands.cleanup_test_eventids.reindex_jobs")
    def test_optional_deletion_is_exact_and_preserves_gwflow_bilby_children(self, reindex):
        unrelated = self._bilby("unrelated")
        _output, _inventory, digest = self._dry_run()

        call_command(
            "cleanup_test_eventids",
            apply=True,
            delete_child_jobs=True,
            expected_inventory_sha256=digest,
        )

        self.assertFalse(BilbyJob.objects.filter(pk=self.direct_bilby.pk).exists())
        self.assertFalse(GWFlowJob.objects.filter(pk=self.direct_gwflow.pk).exists())
        self.assertFalse(SupportingFile.objects.filter(job_id=self.direct_bilby.pk).exists())
        self.assertFalse(GWFlowFile.objects.filter(job_id=self.direct_gwflow.pk).exists())
        self.gwflow_child.refresh_from_db()
        self.assertIsNone(self.gwflow_child.gwflow_job_id)
        self.assertTrue(BilbyJob.objects.filter(pk=unrelated.pk).exists())
        reindex.assert_has_calls(
            [
                mock.call([self.gwflow_child.id], "bilby"),
                mock.call([], "gwflow"),
            ]
        )

    def test_apply_rolls_back_all_deletions_on_failure(self):
        _output, _inventory, digest = self._dry_run()
        original_delete = EventID.objects.filter(id__in=[self.first.id, self.second.id]).delete

        with mock.patch("bilbyui.management.commands.cleanup_test_eventids.EventID.objects.filter") as filter_mock:
            filter_mock.return_value.delete.side_effect = RuntimeError("delete failed")
            with self.assertRaisesMessage(RuntimeError, "delete failed"):
                call_command(
                    "cleanup_test_eventids",
                    apply=True,
                    expected_inventory_sha256=digest,
                )

        self.assertTrue(EventID.objects.filter(pk=self.first.pk).exists())
        self.assertTrue(EventID.objects.filter(pk=self.second.pk).exists())
        self.assertTrue(BilbyJob.objects.filter(pk=self.direct_bilby.pk).exists())
        self.assertTrue(GWFlowJob.objects.filter(pk=self.direct_gwflow.pk).exists())
        self.assertTrue(callable(original_delete))

    @mock.patch(
        "bilbyui.management.commands.cleanup_test_eventids.reindex_jobs",
        side_effect=RuntimeError("ES unavailable"),
    )
    def test_reindex_failure_reports_surviving_ids_after_commit(self, _reindex):
        _output, _inventory, digest = self._dry_run()

        with self.assertRaisesMessage(CommandError, "run es_reindex_reconcile") as caught:
            call_command(
                "cleanup_test_eventids",
                apply=True,
                expected_inventory_sha256=digest,
            )

        message = str(caught.exception)
        self.assertIn(str(self.direct_bilby.id), message)
        self.assertIn(str(self.gwflow_child.id), message)
        self.assertIn(str(self.direct_gwflow.id), message)
        self.assertFalse(EventID.objects.filter(pk=self.first.pk).exists())

    @mock.patch("bilbyui.management.commands.cleanup_test_eventids.reindex_jobs")
    def test_successful_rerun_is_idempotent(self, reindex):
        _output, _inventory, digest = self._dry_run()
        call_command(
            "cleanup_test_eventids",
            apply=True,
            expected_inventory_sha256=digest,
        )
        reindex.reset_mock()
        output = io.StringIO()

        call_command(
            "cleanup_test_eventids",
            apply=True,
            expected_inventory_sha256=digest,
            stdout=output,
        )

        self.assertIn("status=already_complete targets_absent=2", output.getvalue())
        reindex.assert_not_called()

    def test_partial_absence_and_state_drift_abort(self):
        EventID.objects.filter(pk=self.second.pk).delete()
        _inventory, _canonical, digest = build_inventory(
            EventID.objects.filter(event_id__in=("GW111111_222222", "GW222222_111111"))
        )
        with self.assertRaisesMessage(CommandError, "partially absent"):
            call_command(
                "cleanup_test_eventids",
                apply=True,
                expected_inventory_sha256=digest,
            )

        EventID.objects.create(event_id="GW222222_111111", gps_time=1.0)
        _inventory, _canonical, digest = build_inventory(
            EventID.objects.filter(event_id__in=("GW111111_222222", "GW222222_111111"))
        )
        with self.assertRaisesMessage(CommandError, "gps_time=0.0"):
            call_command(
                "cleanup_test_eventids",
                apply=True,
                expected_inventory_sha256=digest,
            )

    def test_delete_children_requires_apply_and_apply_requires_digest(self):
        with self.assertRaisesMessage(CommandError, "--delete-child-jobs requires --apply"):
            call_command("cleanup_test_eventids", delete_child_jobs=True)
        with self.assertRaisesMessage(
            CommandError,
            "--apply requires --expected-inventory-sha256",
        ):
            call_command("cleanup_test_eventids", apply=True)
