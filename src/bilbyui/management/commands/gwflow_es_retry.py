import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from elasticsearch import helpers

from bilbyui.models import GWFlowJob
from bilbyui.utils.gwflow_es import (
    InvalidGWFlowMetadata,
    build_gwflow_es_doc,
    get_es_client,
    gwflow_elastic_search_update,
)
from bilbyui.utils.gwflow_portal import get_version
from bilbyui.utils.gwflow_version import version_tuple

logger = logging.getLogger(__name__)


class ExactVersionFetchError(Exception):
    """Raised when the exact portal version could not be fetched."""


class Command(BaseCommand):
    help = (
        "Bounded re-index of the current authoritative version for GWFlowJobs. "
        "Recovers records where the ingest process terminated between the DB "
        "commit and the ES write, without a durable payload ledger."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Re-index jobs ingested within the last N hours (default: 24).",
        )
        parser.add_argument(
            "--no-doc",
            action="store_true",
            default=False,
            help="Also include jobs that have no existing ES document.",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        include_no_doc = options["no_doc"]

        since = timezone.now() - timedelta(hours=hours)
        # Select by last_updated (the ingest-update event whose ES write is being
        # recovered), not creation_time (immutable row creation). An existing row
        # updated within the window must be eligible for re-index.
        candidates = list(GWFlowJob.objects.filter(last_updated__gte=since).order_by("id"))

        if include_no_doc:
            candidates = self._add_no_doc_candidates(candidates)

        self.stdout.write(f"Re-indexing {len(candidates)} GWFlowJob candidate(s)...")

        success = 0
        skipped = 0
        failed = 0
        for job in candidates:
            try:
                outcome = self.handle_job(job)
            except (ExactVersionFetchError, InvalidGWFlowMetadata) as exc:
                failed += 1
                logger.warning("GWFlow ES retry failed for job %s (%s): %s", job.id, job.sname, exc)
                self.stdout.write(self.style.ERROR(f"✗ Job {job.id} ({job.sname}): {exc}"))
                continue
            except Exception as exc:
                failed += 1
                logger.exception("GWFlow ES retry failed for job %s (%s)", job.id, job.sname)
                self.stdout.write(self.style.ERROR(f"✗ Job {job.id} ({job.sname}): {exc}"))
                continue

            if outcome == "written":
                success += 1
                self.stdout.write(self.style.SUCCESS(f"✓ Job {job.id} ({job.sname}) re-indexed"))
            else:
                skipped += 1
                self.stdout.write(self.style.WARNING(f"→ Job {job.id} ({job.sname}) skipped: {outcome}"))

        self.stdout.write(
            self.style.SUCCESS(f"\nRetry complete: {success} re-indexed, {skipped} skipped, {failed} failed")
        )
        if failed:
            raise CommandError(f"{failed} GWFlowJob(s) could not be re-indexed")

    def handle_job(self, job):
        """Re-index the current authoritative version for a single candidate.

        Returns "written" on success, or a short reason string when the job
        was skipped (no current version, or the version changed while the
        exact payload was being fetched).
        """
        expected = version_tuple(job)
        history_id = expected[1]
        if not history_id:
            return "no-current-version"

        data, state = get_version(job.sname, history_id)
        if state == "down" or data is None:
            raise ExactVersionFetchError(
                f"could not fetch exact version {history_id} for {job.sname} (state={state})"
            )

        # Re-read the job's version tuple immediately before writing. If it
        # changed while the payload was being fetched, skip so we never index
        # a payload for a stale version (a newer run will handle it).
        fresh = GWFlowJob.objects.get(pk=job.pk)
        if version_tuple(fresh) != expected:
            return "version-changed"

        # Validate under #70's InvalidGWFlowMetadata rules before any ES call.
        build_gwflow_es_doc(fresh, data)

        gwflow_elastic_search_update(fresh, data)
        return "written"

    def _add_no_doc_candidates(self, candidates):
        """Add jobs that have no existing ES document to the candidate set."""
        if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            return candidates

        existing = set()
        try:
            es = get_es_client()
            for hit in helpers.scan(
                es,
                index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
                query={"query": {"match_all": {}}},
                _source=False,
            ):
                existing.add(hit["_id"])
        except Exception as exc:
            logger.warning("Could not scan ES for existing docs; skipping --no-doc: %s", exc)
            return candidates

        missing = GWFlowJob.objects.exclude(pk__in=existing).order_by("id")
        missing_ids = set(candidates) | set(missing)
        return sorted(missing_ids, key=lambda j: j.id)
