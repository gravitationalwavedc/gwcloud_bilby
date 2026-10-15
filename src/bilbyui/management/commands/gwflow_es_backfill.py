import logging
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY
from bilbyui.utils.embargo import get_embargo_start
from bilbyui.utils.gwflow_es import _parse_portal_bool
from bilbyui.utils.gwflow_portal import (
    get_versions,
    resolve_current_version,
    resolve_event_id_for_superevent,
)
from bilbyui.utils.gwflow_version import normalise_libraries

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_CONFIG = 2

DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 2000
DEFAULT_MAX_RETRIES = 3
DEFAULT_PACING = 0.05


class PortalUnavailable(Exception):
    """Raised when portal transport is unavailable for a job."""


@dataclass
class RepairProposal:
    """A complete, write-free repair proposal for one GWFlow parent."""

    job: GWFlowJob
    available: bool
    reason: str | None
    trigger_time: float | None
    current_history_id: str
    current_history_timestamp: object
    event_id: object
    parent_fields: dict = field(default_factory=dict)
    child_ids: list[int] = field(default_factory=list)
    pointer_disagreement: bool = False
    containment_gap: bool = False

    @property
    def changed(self):
        return bool(self.parent_fields or self.child_ids)


class Command(BaseCommand):
    help = (
        "Backfill GWFlowJob libraries, current-history metadata, trigger times, "
        "event links, and child links from authoritative current state."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Perform portal reads and validation only; no DB, cache, or ES writes.",
        )
        parser.add_argument(
            "--resume-from",
            type=int,
            default=None,
            help="Resume from this job ID; records with id <= this are skipped.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=DEFAULT_BATCH_SIZE,
            help=f"Records per transaction batch (default {DEFAULT_BATCH_SIZE}, max {MAX_BATCH_SIZE}).",
        )
        parser.add_argument(
            "--max-retries",
            type=int,
            default=DEFAULT_MAX_RETRIES,
            help=f"Retries per batch with backoff (default {DEFAULT_MAX_RETRIES}).",
        )
        parser.add_argument(
            "--pacing",
            type=float,
            default=DEFAULT_PACING,
            help=f"Seconds to sleep between portal requests during normal processing (default {DEFAULT_PACING}).",
        )

    def execute(self, *args, **options):
        # Return the exit code from execute() without Django writing it to stdout.
        # A non-zero code is surfaced as a CommandError so run_from_argv sets the
        # process exit code (Django otherwise discards execute()'s return value).
        self._exit_code = EXIT_OK
        super().execute(*args, **options)
        if self._exit_code != EXIT_OK:
            raise CommandError(
                f"gwflow_es_backfill exited with code {self._exit_code}",
                returncode=self._exit_code,
            )
        return self._exit_code

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        resume_from = options["resume_from"]
        batch_size = options["batch_size"]
        max_retries = options["max_retries"]
        pacing = options["pacing"]

        if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
            self.stderr.write(
                self.style.ERROR(f"--batch-size must be between 1 and {MAX_BATCH_SIZE}, got {batch_size}")
            )
            self._exit_code = EXIT_CONFIG
            return

        if max_retries < 0:
            self.stderr.write(self.style.ERROR(f"--max-retries must be >= 0, got {max_retries}"))
            self._exit_code = EXIT_CONFIG
            return

        if pacing < 0:
            self.stderr.write(self.style.ERROR(f"--pacing must be >= 0, got {pacing}"))
            self._exit_code = EXIT_CONFIG
            return

        if not settings.CBCFLOW_PORTAL_URL or not settings.CBCFLOW_PORTAL_TOKEN:
            self.stderr.write(
                self.style.ERROR(
                    "CBCFLOW_PORTAL_URL and CBCFLOW_PORTAL_TOKEN must be configured to run gwflow_es_backfill."
                )
            )
            self._exit_code = EXIT_CONFIG
            return

        qs = GWFlowJob.objects.order_by("id")
        if resume_from is not None:
            qs = qs.filter(id__gt=resume_from)

        total = qs.count()
        self.stdout.write(
            f"Backfilling {total} GWFlowJob record(s) (dry_run={dry_run}, "
            f"batch_size={batch_size}, max_retries={max_retries}, resume_from={resume_from}, pacing={pacing})"
        )

        total_failures = 0
        batch_count = 0
        any_failure = False
        counts = {"scanned": 0, "changed": 0, "unavailable": 0}
        repaired = {"libraries": 0, "event_id": 0}
        before_counts = self._state_counts(qs)

        for start in range(0, total, batch_size):
            batch = list(qs[start : start + batch_size])
            batch_count += 1
            counts["scanned"] += len(batch)
            if batch_count % 50 == 0:
                self.stdout.write(f"Progress: {batch_count * batch_size} record(s) processed...")

            proposals = []
            failures = list(batch)
            for attempt in range(max_retries + 1):
                if not failures:
                    break
                remaining = []
                for job in failures:
                    try:
                        proposal = self._resolve_job(job)
                        proposals.append(proposal)
                    except PortalUnavailable:
                        remaining.append(job)
                    if pacing > 0:
                        time.sleep(pacing)
                failures = remaining
                if failures and attempt < max_retries:
                    time.sleep(self._backoff(attempt))

            for proposal in proposals:
                if proposal.changed:
                    counts["changed"] += 1
                if not proposal.available:
                    counts["unavailable"] += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Unavailable metadata for GWFlowJob {proposal.job.id} "
                            f"({proposal.job.sname}): {proposal.reason}"
                        )
                    )
                if proposal.containment_gap:
                    any_failure = True
                    self.stderr.write(
                        self.style.ERROR(
                            f"Containment gap for GWFlowJob {proposal.job.id} "
                            f"({proposal.job.sname}): unavailable metadata and stored "
                            f"trigger_time={proposal.job.trigger_time!r} is below EMBARGO_START_TIME"
                        )
                    )
                for name in ("libraries", "event_id"):
                    if name in proposal.parent_fields:
                        repaired[name] += 1

            if not dry_run and proposals:
                self._apply_proposals(proposals)

            for job in failures:
                self._record_failure(job)
            total_failures += len(failures)
            if failures:
                any_failure = True

            if not dry_run:
                last_id = batch[-1].id
                self.stdout.write(f"Last completed job ID: {last_id}")

        if not dry_run and not any_failure:
            cache.delete(LIBRARIES_CACHE_KEY)
            cache.delete(REVIEW_STATUSES_CACHE_KEY)
            self.stdout.write("Invalidated filter-option cache keys after successful backfill")

        label = "Would repair" if dry_run else "Repaired"
        after_counts = self._state_counts(qs)
        self.stdout.write(
            f"Backfill complete: {total} processed, {total_failures} failure(s). "
            f"{label}: {repaired['libraries']} libraries, {repaired['event_id']} event links."
        )
        self.stdout.write(
            f"Summary: scanned={counts['scanned']} changed={counts['changed']} "
            f"unavailable={counts['unavailable']}"
        )
        self.stdout.write(
            f"State before: {before_counts['event_linked']} event links, "
            f"{before_counts['with_libraries']} with libraries. "
            f"State after: {after_counts['event_linked']} event links, "
            f"{after_counts['with_libraries']} with libraries."
        )
        self._exit_code = EXIT_FAILURES if any_failure else EXIT_OK

    def _state_counts(self, qs):
        """Return comparable state totals for repaired fields."""
        return {
            "event_linked": qs.exclude(event_id=None).count(),
            "with_libraries": qs.exclude(libraries=[]).count(),
        }

    def _resolve_job(self, job):
        """Build a complete repair proposal without mutating persistent state."""
        current = resolve_current_version(job.sname)
        transport_failure = current.reason in {
            "versions fetch failed",
            "detail fetch failed",
        }
        if (
            current.versions_state == "down"
            or current.detail_state == "down"
            or transport_failure
        ):
            raise PortalUnavailable(job)

        # Library membership remains a separately repaired field. portal_get's
        # existing cache means this normally reuses the summary fetched by the
        # shared current-version resolver rather than issuing another request.
        versions_data, versions_state = get_versions(job.sname)
        if versions_state == "down" or versions_data is None:
            raise PortalUnavailable(job)

        fields = {}
        if not job.is_pruned:
            selected = None
            if isinstance(versions_data, list):
                selected = next(
                    (
                        version
                        for version in versions_data
                        if isinstance(version, dict) and _parse_portal_bool(version.get("is_current"))
                    ),
                    None,
                )
            libraries = normalise_libraries(selected.get("libraries")) if selected else []
            if libraries != job.libraries:
                fields["libraries"] = libraries

        threshold = get_embargo_start()
        stored_time_unresolved = threshold is not None and (
            job.trigger_time is None or job.trigger_time < threshold
        )
        resolved_event = resolve_event_id_for_superevent(job.sname)
        # Fail closed (docs/SECURITY.md P0 rule 6): when authoritative metadata is
        # unavailable we cannot prove an existing embargo-relevant link is safe to
        # clear, so retain it and force the row to be reported as a containment gap.
        retains_protective_link = (
            not current.available
            and stored_time_unresolved
            and resolved_event is None
            and job.event_id_id is not None
        )
        event = job.event_id if retains_protective_link else resolved_event
        if job.event_id_id != (event.pk if event else None):
            fields["event_id"] = event

        pointer_disagreement = False
        if current.available:
            pointer_disagreement = (
                job.current_history_id != current.current_history_id
                or job.current_history_timestamp != current.current_history_timestamp
            )
            authoritative = {
                "trigger_time": current.trigger_time,
                "current_history_id": current.current_history_id,
                "current_history_timestamp": current.current_history_timestamp,
            }
            for name, value in authoritative.items():
                if getattr(job, name) != value:
                    fields[name] = value

        event_id = event.pk if event else None
        child_ids = list(
            BilbyJob.objects.filter(gwflow_job=job)
            .exclude(event_id_id=event_id)
            .values_list("pk", flat=True)
        )

        containment_gap = (
            not current.available
            and threshold is not None
            and job.trigger_time is not None
            and job.trigger_time < threshold
        ) or retains_protective_link

        if pointer_disagreement:
            self.stderr.write(
                self.style.WARNING(
                    f"Pointer disagreement for GWFlowJob {job.id} ({job.sname}): "
                    f"stored=({job.current_history_id!r}, {job.current_history_timestamp!r}) "
                    f"selected=({current.current_history_id!r}, {current.current_history_timestamp!r})"
                )
            )

        return RepairProposal(
            job=job,
            available=current.available,
            reason=current.reason,
            trigger_time=current.trigger_time if current.available else job.trigger_time,
            current_history_id=(
                current.current_history_id if current.available else job.current_history_id
            ),
            current_history_timestamp=(
                current.current_history_timestamp
                if current.available
                else job.current_history_timestamp
            ),
            event_id=event,
            parent_fields=fields,
            child_ids=child_ids,
            pointer_disagreement=pointer_disagreement,
            containment_gap=containment_gap,
        )

    def _apply_proposals(self, proposals):
        """Apply parent and child repairs in one transaction for the batch."""
        dirty = [proposal for proposal in proposals if proposal.parent_fields]
        with transaction.atomic():
            if dirty:
                field_names = sorted(
                    {
                        name
                        for proposal in dirty
                        for name in proposal.parent_fields
                    }
                )
                for proposal in dirty:
                    for name, value in proposal.parent_fields.items():
                        setattr(proposal.job, name, value)
                GWFlowJob.objects.bulk_update(
                    [proposal.job for proposal in dirty],
                    field_names,
                )

            for proposal in proposals:
                if proposal.child_ids:
                    BilbyJob.objects.filter(pk__in=proposal.child_ids).update(
                        event_id=proposal.event_id
                    )

    def _backoff(self, attempt):
        return min(2**attempt, 10)

    def _record_failure(self, job):
        logger.error(
            "gwflow_es_backfill: permanent failure for GWFlowJob %s (%s)",
            job.id,
            job.sname,
        )
        self.stderr.write(
            self.style.ERROR(
                f"Permanent failure for GWFlowJob {job.id} ({job.sname})"
            )
        )
