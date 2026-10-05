"""Repair historical EventID GPS sentinel values from direct Bilby children."""

from collections import defaultdict
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bilbyui.models import BilbyJob, EventID
from bilbyui.utils.reindex import reindex_affected_event
from bilbyui.utils.search_trigger_time import normalize_trigger

_SENTINEL = 1126259462.391
_LEGITIMATE_EVENT = "GW150914_000000"
_TEST_EVENTS = ("GW111111_222222", "GW222222_111111")
_BACKUP = "gwcloud:/home/lewis/eventid_backup_20260929-040906.sql"
_AGREEMENT_ABS_TOLERANCE = 2.0


def _positive_integer(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CommandError("--batch must be a positive integer") from exc
    if parsed <= 0:
        raise CommandError("--batch must be a positive integer")
    return parsed


def _nonnegative_integer(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CommandError("--after-id must be a non-negative integer") from exc
    if parsed < 0:
        raise CommandError("--after-id must be a non-negative integer")
    return parsed


@dataclass(frozen=True)
class RepairProposal:
    event_id: int
    event_name: str
    child_count: int
    usable_count: int
    action: str
    value: float | None
    reason: str
    rejected_child_ids: tuple[int, ...]
    conflict_child_ids: tuple[int, ...]

    @property
    def changed(self):
        return self.action in {"SET_VALUE", "SET_NULL"}


def _precondition_failures():
    failures = []
    sentinel_rows = list(EventID.objects.filter(gps_time=_SENTINEL).order_by("id").values_list("id", "event_id"))
    if len(sentinel_rows) != 1:
        failures.append(f"check=sole_sentinel expected_count=1 observed_count={len(sentinel_rows)}")
    elif sentinel_rows[0][1] != _LEGITIMATE_EVENT:
        failures.append(f"check=sentinel_identity expected={_LEGITIMATE_EVENT} observed={sentinel_rows[0][1]}")

    legitimate = EventID.objects.filter(event_id=_LEGITIMATE_EVENT).values_list(
        "gps_time",
        flat=True,
    )
    legitimate_values = list(legitimate)
    if not legitimate_values:
        failures.append(f"check=legitimate_row expected={_LEGITIMATE_EVENT}:{_SENTINEL} observed=missing")
    elif legitimate_values[0] != _SENTINEL:
        failures.append(
            "check=legitimate_row "
            f"expected={_LEGITIMATE_EVENT}:{_SENTINEL} "
            f"observed={_LEGITIMATE_EVENT}:{legitimate_values[0]}"
        )

    for name in _TEST_EVENTS:
        values = list(EventID.objects.filter(event_id=name).values_list("gps_time", flat=True))
        if not values:
            failures.append(f"check=test_row name={name} expected=0.0 observed=missing")
        elif values[0] != 0.0:
            failures.append(f"check=test_row name={name} expected=0.0 observed={values[0]}")
    return failures


def _resolve_page(events):
    event_ids = [event.id for event in events]
    children = defaultdict(list)
    for child_id, event_id, raw_value in (
        BilbyJob.objects.filter(event_id_id__in=event_ids)
        .order_by("event_id_id", "id")
        .values_list("id", "event_id_id", "trigger_time")
    ):
        children[event_id].append((child_id, raw_value))

    proposals = []
    for event in events:
        child_rows = children[event.id]
        if event.event_id.startswith("GW150914"):
            proposals.append(
                RepairProposal(
                    event.id,
                    event.event_id,
                    len(child_rows),
                    0,
                    "KEEP_LEGITIMATE",
                    _SENTINEL,
                    "legitimate_event_prefix",
                    (),
                    (),
                )
            )
            continue

        usable = []
        rejected = []
        for child_id, raw_value in child_rows:
            value = normalize_trigger(raw_value)
            if value is None:
                rejected.append(child_id)
            else:
                usable.append((child_id, value))

        if not usable:
            proposals.append(
                RepairProposal(
                    event.id,
                    event.event_id,
                    len(child_rows),
                    0,
                    "SET_NULL",
                    None,
                    "no_recoverable_child_trigger",
                    tuple(rejected),
                    (),
                )
            )
            continue

        representative = min(value for _child_id, value in usable)
        conflicting = tuple(
            child_id for child_id, value in usable if abs(value - representative) > _AGREEMENT_ABS_TOLERANCE
        )
        if conflicting:
            proposals.append(
                RepairProposal(
                    event.id,
                    event.event_id,
                    len(child_rows),
                    len(usable),
                    "REPORT_CONFLICT",
                    _SENTINEL,
                    "conflicting_child_triggers",
                    tuple(rejected),
                    conflicting,
                )
            )
        else:
            proposals.append(
                RepairProposal(
                    event.id,
                    event.event_id,
                    len(child_rows),
                    len(usable),
                    "SET_VALUE",
                    representative,
                    "child_triggers_agree",
                    tuple(rejected),
                    (),
                )
            )
    return proposals


class Command(BaseCommand):
    help = "Repair historical EventID GPS sentinel values."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Read and report only (the default).",
        )
        mode.add_argument(
            "--apply",
            action="store_true",
            help="Apply conditional database updates and reindex changed events.",
        )
        parser.add_argument("--batch", type=_positive_integer, default=500)
        parser.add_argument(
            "--after-id",
            type=_nonnegative_integer,
            default=0,
            help="Exclusive EventID cursor.",
        )

    def _write_proposal(self, proposal):
        for child_id in proposal.rejected_child_ids:
            self.stdout.write(
                f"trigger_source_rejected kind=event-repair child_job_id={child_id} reason=non_finite_child_trigger"
            )
        if proposal.conflict_child_ids:
            child_ids = ",".join(map(str, proposal.conflict_child_ids))
            self.stdout.write(
                f"event_repair_conflict id={proposal.event_id} event_id={proposal.event_name} child_ids={child_ids}"
            )
        value = "none" if proposal.value is None else repr(proposal.value)
        self.stdout.write(
            "event_repair_proposal "
            f"id={proposal.event_id} event_id={proposal.event_name} "
            f"child_count={proposal.child_count} usable_count={proposal.usable_count} "
            f"action={proposal.action} value={value} reason={proposal.reason}"
        )

    def handle(self, *_args, **options):
        apply = options["apply"]
        mode = "apply" if apply else "dry-run"
        batch = _positive_integer(options["batch"])
        cursor = _nonnegative_integer(options["after_id"])
        last_fully_reindexed_id = cursor

        self.stdout.write(
            f"event_repair_start mode={mode} batch={batch} after_id={cursor} "
            f"agreement_abs_tolerance={_AGREEMENT_ABS_TOLERANCE} rel_tolerance=0"
        )
        self.stdout.write(f"backup_reminder path={_BACKUP} action=operator_confirm_before_apply")

        failures = _precondition_failures()
        for failure in failures:
            self.stdout.write(f"precondition_failed {failure}")
        if apply and failures:
            raise CommandError("EventID repair preconditions failed before writes: " + "; ".join(failures))

        totals = {
            "kept": 0,
            "set_value": 0,
            "set_null": 0,
            "conflicts": 0,
            "applied": 0,
            "reindexed": 0,
            "failed": 0,
        }

        while True:
            events = list(EventID.objects.filter(gps_time=_SENTINEL, id__gt=cursor).order_by("id")[:batch])
            if not events:
                break

            proposals = _resolve_page(events)
            for proposal in proposals:
                self._write_proposal(proposal)
                if proposal.action == "KEEP_LEGITIMATE":
                    totals["kept"] += 1
                elif proposal.action == "SET_VALUE":
                    totals["set_value"] += 1
                elif proposal.action == "SET_NULL":
                    totals["set_null"] += 1
                elif proposal.action == "REPORT_CONFLICT":
                    totals["conflicts"] += 1

            changed = [proposal for proposal in proposals if proposal.changed]
            if apply and changed:
                grouped = defaultdict(list)
                for proposal in changed:
                    grouped[proposal.value].append(proposal.event_id)

                try:
                    with transaction.atomic():
                        for destination, ids in grouped.items():
                            updated = EventID.objects.filter(
                                id__in=ids,
                                gps_time=_SENTINEL,
                            ).update(gps_time=destination)
                            if updated != len(ids):
                                raise CommandError(
                                    "conditional update drift; page rolled back "
                                    f"ids={','.join(map(str, sorted(ids)))} "
                                    f"expected={len(ids)} updated={updated} "
                                    f"last_fully_reindexed_id={last_fully_reindexed_id}"
                                )
                except CommandError:
                    totals["failed"] += len(changed)
                    raise

                totals["applied"] += len(changed)
                for proposal in sorted(changed, key=lambda item: item.event_id):
                    try:
                        reindex_affected_event(proposal.event_id)
                    except Exception as exc:
                        totals["failed"] += 1
                        raise CommandError(
                            "event reindex failed after database commit "
                            f"failed_event_id={proposal.event_id} "
                            f"last_fully_reindexed_id={last_fully_reindexed_id}; "
                            "--after-id resumes DB repair only and does not recover "
                            'indexing; recovery="python manage.py '
                            'es_reindex_reconcile --kind bilby" and '
                            '"python manage.py es_reindex_reconcile --kind gwflow", '
                            "or Issue #112 full-corpus reindex"
                        ) from exc
                    totals["reindexed"] += 1
                    last_fully_reindexed_id = proposal.event_id

            cursor = events[-1].id
            if not apply:
                last_fully_reindexed_id = cursor
            elif not changed:
                last_fully_reindexed_id = cursor
            self.stdout.write(
                "page_complete kind=event-repair "
                f"last_successful_id={last_fully_reindexed_id} "
                f"scanned={len(events)} changed={len(changed)}"
            )

        self.stdout.write(
            "event_repair_summary "
            + " ".join(f"{key}={value}" for key, value in totals.items())
            + f" last_fully_reindexed_id={last_fully_reindexed_id}"
        )
