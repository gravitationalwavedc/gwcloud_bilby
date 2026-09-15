import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from bilbyui.models import EventID, GWFlowJob
from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY
from bilbyui.utils.embargo import gwflow_ligo_only_from_metadata
from bilbyui.utils.gwflow_portal import get_superevent, get_versions
from bilbyui.utils.gwflow_version import (
    normalise_current_history_timestamp,
    normalise_libraries,
)

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_CONFIG = 2

DEFAULT_BATCH_SIZE = 500
MAX_BATCH_SIZE = 2000
DEFAULT_MAX_RETRIES = 3
DEFAULT_PACING = 0.05


class PortalUnavailable(Exception):
    """Raised when the portal is down or returns no data for a job."""


class Command(BaseCommand):
    help = (
        "Backfill GWFlowJob libraries, current_history_timestamp, ligo_only, and "
        "event links from the cbcflow portal's authoritative current state."
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
            help=(f"Seconds to sleep between portal requests during normal processing (default {DEFAULT_PACING})."),
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
        repaired = {"libraries": 0, "ligo_only": 0, "event_id": 0}
        before_counts = self._state_counts(qs)

        for start in range(0, total, batch_size):
            batch = list(qs[start : start + batch_size])
            batch_count += 1
            if batch_count % 50 == 0:
                self.stdout.write(f"Progress: {batch_count * batch_size} record(s) processed...")

            updated = []
            failures = list(batch)
            for attempt in range(max_retries + 1):
                if not failures:
                    break
                remaining = []
                for job in failures:
                    try:
                        fields = self._resolve_job(job)
                        updated.append((job, fields))
                        for name in ("libraries", "ligo_only", "event_id"):
                            if name in fields and fields[name] != getattr(job, name):
                                repaired[name] += 1
                    except PortalUnavailable:
                        remaining.append(job)
                    if pacing > 0:
                        time.sleep(pacing)
                failures = remaining
                if failures and attempt < max_retries:
                    time.sleep(self._backoff(attempt))

            if not dry_run and updated:
                with transaction.atomic():
                    field_names = list({name for _, fields in updated for name in fields})
                    for job, fields in updated:
                        for name, value in fields.items():
                            setattr(job, name, value)
                    GWFlowJob.objects.bulk_update([job for job, _ in updated], field_names)

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
            f"{label}: {repaired['libraries']} libraries, {repaired['ligo_only']} ligo_only, "
            f"{repaired['event_id']} event links."
        )
        self.stdout.write(
            f"State before: {before_counts['ligo_only']} ligo_only, "
            f"{before_counts['event_linked']} event links, {before_counts['with_libraries']} with libraries. "
            f"State after: {after_counts['ligo_only']} ligo_only, "
            f"{after_counts['event_linked']} event links, {after_counts['with_libraries']} with libraries."
        )
        self._exit_code = EXIT_FAILURES if any_failure else EXIT_OK

    def _state_counts(self, qs):
        """Return comparable state totals for the repaired fields over a queryset."""
        return {
            "ligo_only": qs.filter(ligo_only=True).count(),
            "event_linked": qs.exclude(event_id=None).count(),
            "with_libraries": qs.exclude(libraries=[]).count(),
        }

    def _resolve_job(self, job):
        """Return the field updates for a single job, or raise PortalUnavailable."""
        data, state = get_versions(job.sname)
        if state == "down" or data is None:
            raise PortalUnavailable(job)

        current = next((v for v in data if v.get("is_current")), None)
        fields = {}
        if current is None:
            # No current version: leave current_history_timestamp null (no substitute).
            fields["current_history_id"] = ""
            fields["current_history_timestamp"] = None
            if not job.is_pruned:
                fields["libraries"] = []
        else:
            # Pruned rows keep their last-known libraries but are excluded from
            # public options by the service layer (is_pruned filter).
            if not job.is_pruned:
                fields["libraries"] = normalise_libraries(current.get("libraries"))
            fields["current_history_id"] = current.get("commit_sha") or ""
            fields["current_history_timestamp"] = normalise_current_history_timestamp(current.get("commit_timestamp"))

        # LIGO-only flag from the superevent's portal metadata (B-2), matching
        # the cron's phase_metadata which uses detail.get("raw_payload", {}).
        detail, state = get_superevent(job.sname)
        if state == "down" or detail is None or not isinstance(detail, dict):
            raise PortalUnavailable(job)
        metadata = detail.get("raw_payload", {})
        fields["ligo_only"] = gwflow_ligo_only_from_metadata(metadata)

        # Authoritative event link (B-3): write the resolved EventID, or None
        # on a no-match so stale links are cleared and reruns converge. A lookup
        # failure propagates to the command's failure path (abort visibly).
        event = EventID.objects.filter(Q(trigger_id=job.sname) | Q(event_id=job.sname)).first()
        fields["event_id"] = event
        return fields

    def _backoff(self, attempt):
        return min(2**attempt, 10)

    def _record_failure(self, job):
        logger.error("gwflow_es_backfill: permanent failure for GWFlowJob %s (%s)", job.id, job.sname)
        self.stderr.write(self.style.ERROR(f"Permanent failure for GWFlowJob {job.id} ({job.sname})"))
