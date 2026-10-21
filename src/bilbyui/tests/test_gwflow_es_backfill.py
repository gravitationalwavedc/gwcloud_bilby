from datetime import UTC, datetime
from io import StringIO
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import visible_to_user
from bilbyui.utils.gwflow_portal import GWFlowCurrentVersion

PORTAL_SETTINGS = {
    "CBCFLOW_PORTAL_URL": "https://portal.example.com",
    "CBCFLOW_PORTAL_TOKEN": "token",
}
TS = datetime(2025, 8, 1, 12, 0, tzinfo=UTC)
OLD_TS = datetime(2023, 10, 13, 12, 0, tzinfo=UTC)
THRESHOLD = 1421884818.0
CURRENT_GPS = 1438044067.054443
OLD_GPS = 1381222535.0


def current_summary(libraries=None, *, commit_sha="sha-current", is_current=True):
    return {
        "libraries": ["cbc-workflow-o4c"] if libraries is None else libraries,
        "commit_sha": commit_sha,
        "record_timestamp": TS,
        "is_current": is_current,
    }


def available_current(
    *,
    trigger_time=CURRENT_GPS,
    history_id="sha-current",
    timestamp=TS,
):
    return GWFlowCurrentVersion(
        available=True,
        trigger_time=trigger_time,
        current_history_id=history_id,
        current_history_timestamp=timestamp,
        versions_state="live",
        detail_state="live",
    )


def unavailable_current(
    reason="detail has no usable finite trigger time",
    *,
    versions_state="live",
    detail_state="live",
):
    return GWFlowCurrentVersion(
        available=False,
        reason=reason,
        versions_state=versions_state,
        detail_state=detail_state,
    )


@override_settings(
    IGNORE_ELASTIC_SEARCH=True,
    EMBARGO_START_TIME=THRESHOLD,
    **PORTAL_SETTINGS,
)
class GwflowEsBackfillCommandTestCase(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()

    def setUp(self):
        cache.clear()

    def make_parent(self, sname="S250801h", **kwargs):
        return GWFlowJob.objects.create(
            sname=sname,
            user=self.user,
            libraries=kwargs.pop("libraries", []),
            **kwargs,
        )

    def make_child(self, parent, name="repair-child", **kwargs):
        return BilbyJob.objects.create(
            user=self.user,
            name=name,
            ini_string="[data]\ndetectors = ['H1']\n",
            gwflow_job=parent,
            **kwargs,
        )

    def run_command(
        self,
        *args,
        current=None,
        current_side_effect=None,
        versions_return=None,
        versions_side_effect=None,
        event_side_effect=None,
        **kwargs,
    ):
        out = StringIO()
        err = StringIO()
        kwargs.setdefault("pacing", 0)
        kwargs.setdefault("max_retries", 0)
        current = current if current is not None else available_current()
        versions_return = versions_return or ([current_summary()], "live")

        with (
            mock.patch(
                "bilbyui.management.commands.gwflow_es_backfill.resolve_current_version",
                return_value=current,
                side_effect=current_side_effect,
            ),
            mock.patch(
                "bilbyui.management.commands.gwflow_es_backfill.get_versions",
                return_value=versions_return,
                side_effect=versions_side_effect,
            ),
            mock.patch(
                "bilbyui.management.commands.gwflow_es_backfill.resolve_event_id_for_superevent",
                side_effect=event_side_effect,
            ) as resolve_event,
        ):
            if event_side_effect is None:
                resolve_event.side_effect = lambda sname: EventID.objects.filter(trigger_id=sname).first()
            try:
                result = call_command(
                    "gwflow_es_backfill",
                    *args,
                    stdout=out,
                    stderr=err,
                    **kwargs,
                )
            except CommandError as exc:
                result = exc.returncode
        return result, out.getvalue(), err.getvalue()

    def test_apply_repairs_parent_pointer_trigger_link_and_child_atomically(self):
        foreign = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
            nickname="original-owner",
        )
        owned = EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        parent = self.make_parent(
            trigger_time=OLD_GPS,
            current_history_id="sha-old",
            current_history_timestamp=OLD_TS,
            event_id=foreign,
        )
        child = self.make_child(parent, event_id=foreign)

        code, out, err = self.run_command()

        self.assertEqual(code, 0)
        self.assertIn("Pointer disagreement for GWFlowJob", err)
        self.assertIn("Summary: scanned=1 changed=1 unavailable=0", out)
        parent.refresh_from_db()
        child.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(parent.trigger_time, CURRENT_GPS)
        self.assertEqual(parent.current_history_id, "sha-current")
        self.assertEqual(parent.current_history_timestamp, TS)
        self.assertEqual(parent.event_id, owned)
        self.assertEqual(child.event_id, owned)
        self.assertEqual(foreign.trigger_id, "S231013ab")
        self.assertEqual(foreign.gps_time, OLD_GPS)
        self.assertEqual(foreign.nickname, "original-owner")

    def test_dry_run_reports_counts_without_db_child_or_cache_writes(self):
        foreign = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
        )
        EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        parent = self.make_parent(
            trigger_time=OLD_GPS,
            current_history_id="sha-old",
            current_history_timestamp=OLD_TS,
            event_id=foreign,
        )
        child = self.make_child(parent, event_id=foreign)
        cache.set(LIBRARIES_CACHE_KEY, ["old"])
        cache.set(REVIEW_STATUSES_CACHE_KEY, ["old"])

        with (
            mock.patch("bilbyui.management.commands.gwflow_es_backfill.GWFlowJob.objects.bulk_update") as bulk_update,
            mock.patch("bilbyui.management.commands.gwflow_es_backfill.cache.delete") as cache_delete,
        ):
            code, out, _ = self.run_command("--dry-run")

        self.assertEqual(code, 0)
        self.assertIn("Summary: scanned=1 changed=1 unavailable=0", out)
        self.assertNotIn("Last completed job ID:", out)
        bulk_update.assert_not_called()
        cache_delete.assert_not_called()
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.trigger_time, OLD_GPS)
        self.assertEqual(parent.current_history_id, "sha-old")
        self.assertEqual(parent.event_id, foreign)
        self.assertEqual(child.event_id, foreign)
        self.assertEqual(cache.get(LIBRARIES_CACHE_KEY), ["old"])
        self.assertEqual(cache.get(REVIEW_STATUSES_CACHE_KEY), ["old"])

    def test_child_only_correction_counts_one_changed_parent(self):
        owned = EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        stale = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
        )
        parent = self.make_parent(
            trigger_time=CURRENT_GPS,
            current_history_id="sha-current",
            current_history_timestamp=TS,
            event_id=owned,
            libraries=["cbc-workflow-o4c"],
        )
        child = self.make_child(parent, event_id=stale)

        code, out, _ = self.run_command()

        self.assertEqual(code, 0)
        self.assertIn("Summary: scanned=1 changed=1 unavailable=0", out)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.event_id, owned)
        self.assertEqual(child.event_id, owned)

    def test_unavailable_preserves_metadata_but_reconciles_parent_and_child_link(self):
        foreign = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
        )
        owned = EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        parent = self.make_parent(
            trigger_time=CURRENT_GPS,
            current_history_id="sha-stored",
            current_history_timestamp=OLD_TS,
            event_id=foreign,
        )
        child = self.make_child(parent, event_id=foreign)

        code, out, err = self.run_command(current=unavailable_current())

        self.assertEqual(code, 0)
        self.assertIn("Summary: scanned=1 changed=1 unavailable=1", out)
        self.assertIn("Unavailable metadata", err)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.trigger_time, CURRENT_GPS)
        self.assertEqual(parent.current_history_id, "sha-stored")
        self.assertEqual(parent.current_history_timestamp, OLD_TS)
        self.assertEqual(parent.event_id, owned)
        self.assertEqual(child.event_id, owned)

    def test_unavailable_retains_protective_link_and_reports_gap(self):
        for index, trigger_time in enumerate((None, OLD_GPS)):
            with self.subTest(trigger_time=trigger_time):
                foreign = EventID.objects.create(
                    event_id=f"G70010{index}",
                    trigger_id=f"S23101{index}ab",
                    gps_time=CURRENT_GPS,
                )
                parent = self.make_parent(
                    sname=f"S25081{index}h",
                    trigger_time=trigger_time,
                    current_history_id="sha-stored",
                    current_history_timestamp=OLD_TS,
                    event_id=foreign,
                )

                with mock.patch(
                    "bilbyui.management.commands.gwflow_es_backfill.GWFlowJob.objects.bulk_update"
                ) as bulk_update:
                    dry_code, dry_out, dry_err = self.run_command(
                        "--dry-run",
                        current=unavailable_current(),
                        event_side_effect=lambda _sname: None,
                    )

                self.assertEqual(dry_code, 1)
                self.assertIn("unavailable=1", dry_out)
                self.assertIn(
                    f"Containment gap for GWFlowJob {parent.id}",
                    dry_err,
                )
                bulk_update.assert_not_called()
                parent.refresh_from_db()
                self.assertEqual(parent.event_id, foreign)

                apply_code, apply_out, apply_err = self.run_command(
                    current=unavailable_current(),
                    event_side_effect=lambda _sname: None,
                )

                self.assertEqual(apply_code, 1)
                self.assertIn("unavailable=1", apply_out)
                self.assertIn(
                    f"Containment gap for GWFlowJob {parent.id}",
                    apply_err,
                )
                parent.refresh_from_db()
                self.assertEqual(parent.event_id, foreign)
                self.assertFalse(
                    visible_to_user(
                        GWFlowJob.objects.filter(pk=parent.pk),
                        AnonymousUser(),
                        "GWFlowJob",
                    ).exists()
                )

                parent.delete()
                foreign.delete()

    def test_unavailable_below_threshold_is_reported_and_exits_nonzero(self):
        parent = self.make_parent(
            trigger_time=OLD_GPS,
            current_history_id="sha-stored",
            current_history_timestamp=OLD_TS,
        )

        code, out, err = self.run_command(current=unavailable_current())

        self.assertEqual(code, 1)
        self.assertIn("Summary: scanned=1 changed=1 unavailable=1", out)
        self.assertIn(f"Containment gap for GWFlowJob {parent.id}", err)
        parent.refresh_from_db()
        self.assertEqual(parent.trigger_time, OLD_GPS)
        self.assertEqual(parent.current_history_id, "sha-stored")
        self.assertEqual(parent.current_history_timestamp, OLD_TS)

    def test_second_run_is_noop_and_does_not_bulk_update(self):
        owned = EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        parent = self.make_parent(
            trigger_time=OLD_GPS,
            current_history_id="sha-old",
            current_history_timestamp=OLD_TS,
        )
        child = self.make_child(parent)

        first_code, first_out, _ = self.run_command()
        self.assertEqual(first_code, 0)
        self.assertIn("changed=1", first_out)

        with mock.patch("bilbyui.management.commands.gwflow_es_backfill.GWFlowJob.objects.bulk_update") as bulk_update:
            second_code, second_out, _ = self.run_command()

        self.assertEqual(second_code, 0)
        self.assertIn("Summary: scanned=1 changed=0 unavailable=0", second_out)
        bulk_update.assert_not_called()
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.event_id, owned)
        self.assertEqual(child.event_id, owned)

    def test_parent_and_child_writes_roll_back_together(self):
        owned = EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        foreign = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
        )
        parent = self.make_parent(
            trigger_time=OLD_GPS,
            current_history_id="sha-old",
            current_history_timestamp=OLD_TS,
            event_id=foreign,
        )
        self.make_child(parent, event_id=foreign)

        with mock.patch(
            "bilbyui.management.commands.gwflow_es_backfill.BilbyJob.objects.filter",
            side_effect=RuntimeError("forced child write failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "forced child write failure"):
                self.run_command(event_side_effect=lambda _sname: owned)

        parent.refresh_from_db()
        self.assertEqual(parent.trigger_time, OLD_GPS)
        self.assertEqual(parent.current_history_id, "sha-old")
        self.assertEqual(parent.event_id, foreign)

    def test_apply_failure_after_parent_bulk_update_rolls_back_parent(self):
        owned = EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        foreign = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
        )
        parent = self.make_parent(
            trigger_time=OLD_GPS,
            current_history_id="sha-old",
            current_history_timestamp=OLD_TS,
            event_id=foreign,
        )
        self.make_child(parent, event_id=foreign)

        original_apply = __import__(
            "bilbyui.management.commands.gwflow_es_backfill",
            fromlist=["Command"],
        ).Command._apply_proposals

        def failing_apply(command, proposals):
            from django.db import transaction

            with transaction.atomic():
                proposal = proposals[0]
                for name, value in proposal.parent_fields.items():
                    setattr(proposal.job, name, value)
                GWFlowJob.objects.bulk_update(
                    [proposal.job],
                    list(proposal.parent_fields),
                )
                raise RuntimeError("forced write failure")

        with mock.patch(
            "bilbyui.management.commands.gwflow_es_backfill.Command._apply_proposals",
            autospec=True,
            side_effect=failing_apply,
        ):
            with self.assertRaisesRegex(RuntimeError, "forced write failure"):
                self.run_command(event_side_effect=lambda _sname: owned)

        self.assertIsNotNone(original_apply)
        parent.refresh_from_db()
        self.assertEqual(parent.trigger_time, OLD_GPS)
        self.assertEqual(parent.current_history_id, "sha-old")
        self.assertEqual(parent.event_id, foreign)

    def test_no_same_owner_event_clears_parent_and_child_links(self):
        foreign = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
        )
        parent = self.make_parent(
            trigger_time=CURRENT_GPS,
            current_history_id="sha-current",
            current_history_timestamp=TS,
            event_id=foreign,
            libraries=["cbc-workflow-o4c"],
        )
        child = self.make_child(parent, event_id=foreign)

        code, out, _ = self.run_command()

        self.assertEqual(code, 0)
        self.assertIn("changed=1", out)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertIsNone(parent.event_id)
        self.assertIsNone(child.event_id)

    def test_unrelated_parent_child_and_original_owner_remain_unchanged(self):
        original = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_GPS,
            nickname="original",
        )
        owned = EventID.objects.create(
            event_id="G642577",
            trigger_id="S250801h",
            gps_time=CURRENT_GPS,
        )
        target = self.make_parent(
            sname="S250801h",
            trigger_time=OLD_GPS,
            event_id=original,
        )
        unrelated = self.make_parent(
            sname="S231013ab",
            trigger_time=OLD_GPS,
            current_history_id="unrelated-pointer",
            current_history_timestamp=OLD_TS,
            event_id=original,
            libraries=["legacy"],
        )
        unrelated_child = self.make_child(
            unrelated,
            name="unrelated-child",
            event_id=original,
        )

        def current_for(sname):
            if sname == "S250801h":
                return available_current()
            return available_current(
                trigger_time=OLD_GPS,
                history_id="unrelated-pointer",
                timestamp=OLD_TS,
            )

        def versions_for(sname):
            libraries = ["cbc-workflow-o4c"] if sname == "S250801h" else ["legacy"]
            return [current_summary(libraries=libraries)], "live"

        code, _, _ = self.run_command(
            current_side_effect=current_for,
            versions_side_effect=versions_for,
        )

        self.assertEqual(code, 0)
        target.refresh_from_db()
        unrelated.refresh_from_db()
        unrelated_child.refresh_from_db()
        original.refresh_from_db()
        self.assertEqual(target.event_id, owned)
        self.assertEqual(unrelated.event_id, original)
        self.assertEqual(unrelated.trigger_time, OLD_GPS)
        self.assertEqual(unrelated.current_history_id, "unrelated-pointer")
        self.assertEqual(unrelated_child.event_id, original)
        self.assertEqual(original.trigger_id, "S231013ab")
        self.assertEqual(original.gps_time, OLD_GPS)
        self.assertEqual(original.nickname, "original")

    def test_libraries_are_normalised_and_pruned_rows_keep_last_known(self):
        normal = self.make_parent(sname="S250801h")
        pruned = self.make_parent(
            sname="S250802a",
            libraries=["last-known"],
            is_pruned=True,
        )

        def versions_for(sname):
            if sname == normal.sname:
                return [current_summary(libraries=[" lib ", "", "   ", 123, None, "second"])], "live"
            return [current_summary(libraries=["new"])], "live"

        code, _, _ = self.run_command(versions_side_effect=versions_for)

        self.assertEqual(code, 0)
        normal.refresh_from_db()
        pruned.refresh_from_db()
        self.assertEqual(normal.libraries, ["lib", "second"])
        self.assertEqual(pruned.libraries, ["last-known"])

    def test_string_false_current_flag_does_not_select(self):
        parent = self.make_parent(sname="S250801h", libraries=["old"])

        code, _, _ = self.run_command(
            versions_return=([current_summary(is_current="false")], "live"),
        )

        self.assertEqual(code, 0)
        parent.refresh_from_db()
        self.assertEqual(parent.libraries, [])

    def test_pointer_disagreement_is_reported(self):
        parent = self.make_parent(
            trigger_time=CURRENT_GPS,
            current_history_id="sha-old",
            current_history_timestamp=OLD_TS,
        )

        code, _, err = self.run_command()

        self.assertEqual(code, 0)
        self.assertIn(f"Pointer disagreement for GWFlowJob {parent.id}", err)

    def test_portal_transport_failure_retries_and_returns_one(self):
        parent = self.make_parent(trigger_time=CURRENT_GPS)
        down = unavailable_current(
            "versions response is not a list",
            versions_state="down",
            detail_state=None,
        )

        code, out, err = self.run_command(
            current=down,
            versions_return=(None, "down"),
            max_retries=1,
        )

        self.assertEqual(code, 1)
        self.assertIn("failure(s)", out)
        self.assertIn(f"Permanent failure for GWFlowJob {parent.id}", err)

    def test_resolver_transport_exception_reason_uses_failure_path(self):
        parent = self.make_parent(trigger_time=CURRENT_GPS)
        failed = unavailable_current(
            "detail fetch failed",
            versions_state="live",
            detail_state=None,
        )

        code, out, err = self.run_command(
            current=failed,
            max_retries=1,
        )

        self.assertEqual(code, 1)
        self.assertIn("failure(s)", out)
        self.assertIn(f"Permanent failure for GWFlowJob {parent.id}", err)

    def test_cache_invalidated_only_after_successful_apply(self):
        self.make_parent(trigger_time=CURRENT_GPS)
        cache.set(LIBRARIES_CACHE_KEY, ["x"])
        cache.set(REVIEW_STATUSES_CACHE_KEY, ["y"])

        code, _, _ = self.run_command()

        self.assertEqual(code, 0)
        self.assertIsNone(cache.get(LIBRARIES_CACHE_KEY))
        self.assertIsNone(cache.get(REVIEW_STATUSES_CACHE_KEY))

    def test_resume_from_skips_lower_ids(self):
        skipped = self.make_parent(sname="S250801h", trigger_time=OLD_GPS)
        processed = self.make_parent(sname="S250802a", trigger_time=OLD_GPS)

        code, out, _ = self.run_command("--resume-from", str(skipped.id))

        self.assertEqual(code, 0)
        self.assertIn("Summary: scanned=1 changed=1 unavailable=0", out)
        skipped.refresh_from_db()
        processed.refresh_from_db()
        self.assertEqual(skipped.trigger_time, OLD_GPS)
        self.assertEqual(processed.trigger_time, CURRENT_GPS)

    def test_pacing_sleeps_between_rows(self):
        self.make_parent(trigger_time=CURRENT_GPS)
        with mock.patch("bilbyui.management.commands.gwflow_es_backfill.time.sleep") as sleep:
            self.run_command(pacing=0.1)
        sleep.assert_any_call(0.1)

    def test_config_missing_returns_two(self):
        self.make_parent()
        out = StringIO()
        err = StringIO()
        with override_settings(
            CBCFLOW_PORTAL_URL=None,
            CBCFLOW_PORTAL_TOKEN=None,
        ):
            with self.assertRaises(CommandError) as context:
                call_command("gwflow_es_backfill", stdout=out, stderr=err)
        self.assertEqual(context.exception.returncode, 2)
        self.assertIn("must be configured", err.getvalue())

    def test_invalid_options_return_two(self):
        for args, expected in (
            (("--batch-size", "5000"), "must be between 1 and 2000"),
            (("--max-retries", "-1"), "--max-retries must be >= 0"),
            (("--pacing", "-1"), "--pacing must be >= 0"),
        ):
            with self.subTest(args=args):
                out = StringIO()
                err = StringIO()
                with self.assertRaises(CommandError) as context:
                    call_command(
                        "gwflow_es_backfill",
                        *args,
                        stdout=out,
                        stderr=err,
                    )
                self.assertEqual(context.exception.returncode, 2)
                self.assertIn(expected, err.getvalue())
