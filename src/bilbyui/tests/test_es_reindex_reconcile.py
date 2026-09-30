from io import StringIO
from unittest import mock

from django.core.management import CommandError, call_command

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.reindex import ReindexCounts, ReindexError


class EsReindexReconcileCommandTests(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.ini = create_test_ini_string({"detectors": "['H1']"})

    def make_bilby(self, name):
        return BilbyJob.objects.create(
            user=self.user,
            name=name,
            private=False,
            ini_string=self.ini,
        )

    def make_gwflow(self, sname):
        return GWFlowJob.objects.create(user=self.user, sname=sname)

    def run_command(self, *args):
        output = StringIO()
        with (
            mock.patch(
                "bilbyui.management.commands.es_reindex_reconcile.reindex_jobs",
                return_value=ReindexCounts(0, 0, 0),
            ) as reindex,
            mock.patch(
                "bilbyui.management.commands.es_reindex_reconcile.verify_search_trigger_time"
            ) as verify,
        ):
            call_command("es_reindex_reconcile", *args, stdout=output)
        return output.getvalue(), reindex, verify

    def test_omitted_kind_processes_bilby_then_gwflow(self):
        bilby = self.make_bilby("bilby")
        gwflow = self.make_gwflow("S230601aa")

        _, reindex, verify = self.run_command("--batch", "1")

        self.assertEqual(
            reindex.call_args_list,
            [
                mock.call([bilby.id], "bilby"),
                mock.call([gwflow.id], "gwflow"),
            ],
        )
        self.assertEqual(
            verify.call_args_list,
            [mock.call("bilby"), mock.call("gwflow")],
        )

    def test_kind_processes_only_selected_kind(self):
        self.make_bilby("bilby")
        gwflow = self.make_gwflow("S230601ab")

        _, reindex, verify = self.run_command("--kind", "gwflow")

        reindex.assert_called_once_with([gwflow.id], "gwflow")
        verify.assert_called_once_with("gwflow")

    def test_default_batch_is_200_and_pages_by_ascending_id(self):
        jobs = [self.make_gwflow(f"S230602{i:03d}") for i in range(201)]

        _, reindex, _ = self.run_command("--kind", "gwflow")

        self.assertEqual(len(reindex.call_args_list), 2)
        self.assertEqual(reindex.call_args_list[0], mock.call([job.id for job in jobs[:200]], "gwflow"))
        self.assertEqual(reindex.call_args_list[1], mock.call([jobs[-1].id], "gwflow"))

    def test_after_id_is_exclusive_but_verification_is_complete(self):
        first = self.make_gwflow("S230603aa")
        second = self.make_gwflow("S230603ab")
        third = self.make_gwflow("S230603ac")

        _, reindex, verify = self.run_command(
            "--kind",
            "gwflow",
            "--after-id",
            str(second.id),
        )

        reindex.assert_called_once_with([third.id], "gwflow")
        self.assertNotIn(first.id, reindex.call_args.args[0])
        verify.assert_called_once_with("gwflow")

    def test_checkpoint_printed_only_after_complete_page_success(self):
        first = self.make_gwflow("S230604aa")
        second = self.make_gwflow("S230604ab")
        output = StringIO()

        with (
            mock.patch(
                "bilbyui.management.commands.es_reindex_reconcile.reindex_jobs",
                side_effect=[
                    ReindexCounts(1, 1, 0),
                    ReindexError("failed"),
                ],
            ),
            mock.patch(
                "bilbyui.management.commands.es_reindex_reconcile.verify_search_trigger_time"
            ) as verify,
        ):
            with self.assertRaises(CommandError) as raised:
                call_command(
                    "es_reindex_reconcile",
                    "--kind",
                    "gwflow",
                    "--batch",
                    "1",
                    stdout=output,
                )

        self.assertEqual(output.getvalue(), f"kind=gwflow last_successful_id={first.id}\n")
        self.assertNotIn(f"last_successful_id={second.id}", output.getvalue())
        self.assertIn(f"failed_ids={second.id}", str(raised.exception))
        self.assertIn("status=reindex_failed", str(raised.exception))
        verify.assert_not_called()

    def test_restart_from_printed_checkpoint_processes_only_later_rows(self):
        first = self.make_gwflow("S230605aa")
        second = self.make_gwflow("S230605ab")
        third = self.make_gwflow("S230605ac")

        output, _, _ = self.run_command("--kind", "gwflow", "--batch", "2")
        self.assertIn(f"kind=gwflow last_successful_id={second.id}", output)

        _, reindex, _ = self.run_command(
            "--kind",
            "gwflow",
            "--after-id",
            str(second.id),
        )
        reindex.assert_called_once_with([third.id], "gwflow")
        self.assertNotIn(first.id, reindex.call_args.args[0])

    def test_rerunning_page_is_idempotent_stable_id_input(self):
        jobs = [self.make_gwflow("S230606aa"), self.make_gwflow("S230606ab")]

        _, first_run, _ = self.run_command("--kind", "gwflow")
        _, second_run, _ = self.run_command("--kind", "gwflow")

        expected = mock.call([job.id for job in jobs], "gwflow")
        self.assertEqual(first_run.call_args, expected)
        self.assertEqual(second_run.call_args, expected)

    def test_verification_failure_exits_nonzero(self):
        output = StringIO()
        with (
            mock.patch(
                "bilbyui.management.commands.es_reindex_reconcile.reindex_jobs"
            ) as reindex,
            mock.patch(
                "bilbyui.management.commands.es_reindex_reconcile.verify_search_trigger_time",
                side_effect=ReindexError(
                    "verification failed kind=gwflow checked=1 failures=1"
                ),
            ),
        ):
            with self.assertRaises(CommandError) as raised:
                call_command(
                    "es_reindex_reconcile",
                    "--kind",
                    "gwflow",
                    stdout=output,
                )

        reindex.assert_not_called()
        self.assertIn("verification failed kind=gwflow", str(raised.exception))

    def test_invalid_batch_values_are_rejected_before_writing(self):
        for value in ("0", "201"):
            with self.subTest(value=value):
                with (
                    mock.patch(
                        "bilbyui.management.commands.es_reindex_reconcile.reindex_jobs"
                    ) as reindex,
                    mock.patch(
                        "bilbyui.management.commands.es_reindex_reconcile.verify_search_trigger_time"
                    ) as verify,
                ):
                    with self.assertRaises(CommandError):
                        call_command(
                            "es_reindex_reconcile",
                            "--kind",
                            "bilby",
                            "--batch",
                            value,
                        )
                reindex.assert_not_called()
                verify.assert_not_called()

    def test_bilby_query_uses_required_select_related(self):
        job = self.make_bilby("bilby-related")
        command_path = "bilbyui.management.commands.es_reindex_reconcile"
        original = BilbyJob.objects.select_related

        with (
            mock.patch.object(
                BilbyJob.objects,
                "select_related",
                wraps=original,
            ) as select_related,
            mock.patch(
                f"{command_path}.reindex_jobs",
                return_value=ReindexCounts(1, 1, 0),
            ),
            mock.patch(f"{command_path}.verify_search_trigger_time"),
        ):
            call_command("es_reindex_reconcile", "--kind", "bilby")

        select_related.assert_called_once_with(
            "event_id",
            "gwflow_job__event_id",
        )
        self.assertTrue(BilbyJob.objects.filter(id=job.id).exists())

    def test_gwflow_query_uses_required_select_related(self):
        self.make_gwflow("S230607aa")
        command_path = "bilbyui.management.commands.es_reindex_reconcile"
        original = GWFlowJob.objects.select_related

        with (
            mock.patch.object(
                GWFlowJob.objects,
                "select_related",
                wraps=original,
            ) as select_related,
            mock.patch(
                f"{command_path}.reindex_jobs",
                return_value=ReindexCounts(1, 1, 0),
            ),
            mock.patch(f"{command_path}.verify_search_trigger_time"),
        ):
            call_command("es_reindex_reconcile", "--kind", "gwflow")

        select_related.assert_called_once_with("event_id")
