import argparse
import logging
from collections import defaultdict
from collections.abc import Mapping

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Case, FloatField, Value, When

from bilbyui.models import BilbyJob, GWFlowJob, IniKeyValue
from bilbyui.utils.embargo import _gwflow_trigger_time_from_metadata
from bilbyui.utils.gwflow_portal import get_version
from bilbyui.utils.reindex import reindex_jobs, verify_search_trigger_time
from bilbyui.utils.search_trigger_time import normalize_trigger

logger = logging.getLogger(__name__)

_SENTINEL = 1126259462.391
_SENTINEL_EVENT = "GW150914_000000"


def positive_integer(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("--batch must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("--batch must be a positive integer")
    return parsed


class Command(BaseCommand):
    help = "Backfill typed trigger times in bounded, resumable pages."

    def add_arguments(self, parser):
        parser.add_argument("--kind", required=True, choices=("bilby", "gwflow"))
        parser.add_argument(
            "--batch",
            type=positive_integer,
            default=500,
            help="Positive keyset page size (default: 500).",
        )
        parser.add_argument(
            "--after-id",
            type=int,
            default=0,
            help="Exclusively start after this job ID (default: 0).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Resolve and report without database or Elasticsearch writes.",
        )

    def handle(self, *_args, **options):
        kind = options["kind"]
        batch = options["batch"]
        dry_run = options["dry_run"]
        cursor = options["after_id"]
        totals = defaultdict(int)

        while True:
            page = self._candidate_page(kind, cursor, batch)
            if not page:
                break
            page_ids = [job.id for job in page]

            try:
                resolutions, counts = self._resolve_page(kind, page)
                for key, value in counts.items():
                    totals[key] += value

                updated = 0
                concurrent_ids = []
                not_updated_ids = []
                if not dry_run:
                    updated, concurrent_ids, not_updated_ids = self._write_page(
                        kind,
                        resolutions,
                    )
                    totals["updated"] += updated
                    totals["unchanged"] += len(concurrent_ids) + len(not_updated_ids)
                    if concurrent_ids:
                        self.stderr.write(
                            "concurrent_change "
                            f"kind={kind} job_ids={self._ids(concurrent_ids)} "
                            f"expected={len(resolutions)} updated={updated}"
                        )
                    if not_updated_ids:
                        self.stderr.write(
                            "not_updated "
                            f"kind={kind} job_ids={self._ids(not_updated_ids)} "
                            f"expected={len(resolutions)} updated={updated}"
                        )
            except Exception as exc:
                totals["failed"] += len(page_ids)
                self.stderr.write(
                    f"page_failed kind={kind} failed_ids={self._ids(page_ids)} "
                    f"last_successful_id={cursor} reason={type(exc).__name__}"
                )
                raise CommandError(
                    f"kind={kind} failed_ids={self._ids(page_ids)} last_successful_id={cursor} status=page_failed"
                ) from exc

            if not dry_run:
                try:
                    reindex_jobs(page_ids, kind)
                except Exception as exc:
                    totals["failed"] += len(page_ids)
                    self.stderr.write(
                        f"reindex_failed kind={kind} failed_ids={self._ids(page_ids)} "
                        f"last_fully_reindexed_id={cursor} reason={type(exc).__name__}"
                    )
                    raise CommandError(
                        f"kind={kind} failed_ids={self._ids(page_ids)} "
                        f"last_fully_reindexed_id={cursor} status=reindex_failed "
                        f'recovery="python manage.py es_reindex_reconcile '
                        f'--kind {kind} --after-id {cursor}"'
                    ) from exc

            cursor = page_ids[-1]
            self.stdout.write(
                f"kind={kind} last_successful_id={cursor} "
                f"scanned={len(page)} resolved={counts['resolved']} "
                f"unresolved={counts['unresolved']} updated={updated}"
            )

        self.stdout.write(
            f"backfill_complete kind={kind} dry_run={str(dry_run).lower()} "
            f"scanned={totals['scanned']} resolved={totals['resolved']} "
            f"unresolved={totals['unresolved']} unchanged={totals['unchanged']} "
            f"updated={totals['updated']} rejected_source={totals['rejected_source']} "
            f"duplicate_disagreement={totals['duplicate_disagreement']} "
            f"failed={totals['failed']}"
        )

        if not dry_run:
            try:
                verify_search_trigger_time(kind)
            except Exception as exc:
                raise CommandError(f"kind={kind} last_successful_id={cursor} status=verification_failed") from exc

    @staticmethod
    def _ids(values):
        return ",".join(str(value) for value in values)

    @staticmethod
    def _candidate_page(kind, cursor, batch):
        model = BilbyJob if kind == "bilby" else GWFlowJob
        queryset = model.objects.filter(
            id__gt=cursor,
            trigger_time__isnull=True,
        ).order_by("id")
        if kind == "gwflow":
            queryset = queryset.select_related("event_id")
        return list(queryset[:batch])

    def _resolve_page(self, kind, page):
        if kind == "bilby":
            return self._resolve_bilby_page(page)
        return self._resolve_gwflow_page(page)

    def _resolve_bilby_page(self, page):
        rows_by_job = defaultdict(list)
        source_rows = (
            IniKeyValue.objects.filter(
                job_id__in=[job.id for job in page],
                key="trigger_time",
            )
            .order_by("job_id", "-processed", "-index", "-id")
            .values("id", "job_id", "value", "index", "processed")
        )
        for row in source_rows:
            rows_by_job[row["job_id"]].append(row)

        resolutions = {}
        counts = defaultdict(int)
        counts["scanned"] = len(page)

        for job in page:
            selected = None
            selected_class = "none"
            for processed in (True, False):
                usable = []
                for row in rows_by_job[job.id]:
                    if row["processed"] != processed:
                        continue
                    normalized = normalize_trigger(row["value"])
                    if normalized is None:
                        counts["rejected_source"] += 1
                        logger.warning(
                            "trigger_source_rejected kind=bilby job_id=%s source_row_id=%s",
                            job.id,
                            row["id"],
                        )
                    else:
                        usable.append((row, normalized))

                if not usable:
                    continue

                if len({value for _, value in usable}) > 1:
                    counts["duplicate_disagreement"] += 1
                    logger.warning(
                        "trigger_duplicate_disagreement job_id=%s processed=%s source_row_ids=%s",
                        job.id,
                        str(processed).lower(),
                        self._ids(row["id"] for row, _ in usable),
                    )
                chosen, selected = max(
                    usable,
                    key=lambda item: (item[0]["index"], item[0]["id"]),
                )
                selected_class = f"processed={str(processed).lower()} source_row_id={chosen['id']}"
                break

            if selected is None:
                counts["unresolved"] += 1
                counts["unchanged"] += 1
                logger.debug(
                    "trigger_unresolved kind=bilby job_id=%s source_class=none reason=no_usable_source",
                    job.id,
                )
            else:
                counts["resolved"] += 1
                resolutions[job.id] = selected
                logger.debug(
                    "trigger_resolved kind=bilby job_id=%s source_class=%s",
                    job.id,
                    selected_class,
                )

        return resolutions, counts

    def _resolve_gwflow_page(self, page):
        resolutions = {}
        counts = defaultdict(int)
        counts["scanned"] = len(page)

        for job in page:
            selected = None
            source_class = "none"
            event = job.event_id
            if event is not None:
                event_value = normalize_trigger(event.gps_time)
                sentinel_allowed = event.event_id == _SENTINEL_EVENT and event_value == _SENTINEL
                if event_value not in (None, 0.0, _SENTINEL) or sentinel_allowed:
                    selected = event_value
                    source_class = "event_id"

            if selected is None:
                try:
                    metadata, state = get_version(
                        job.sname,
                        job.current_history_id,
                    )
                except Exception as exc:
                    raise RuntimeError(f"portal fetch failed for GWFlowJob {job.id}") from exc
                if state == "down" or not isinstance(metadata, Mapping):
                    raise RuntimeError(f"portal metadata unavailable for GWFlowJob {job.id}")
                selected = normalize_trigger(_gwflow_trigger_time_from_metadata(metadata))
                source_class = "metadata"

            if selected is None:
                counts["unresolved"] += 1
                counts["unchanged"] += 1
                logger.debug(
                    "trigger_unresolved kind=gwflow job_id=%s source_class=metadata reason=no_usable_source",
                    job.id,
                )
            else:
                counts["resolved"] += 1
                resolutions[job.id] = selected
                logger.debug(
                    "trigger_resolved kind=gwflow job_id=%s source_class=%s",
                    job.id,
                    source_class,
                )

        return resolutions, counts

    @staticmethod
    def _write_page(kind, resolutions):
        if not resolutions:
            return 0, [], []

        model = BilbyJob if kind == "bilby" else GWFlowJob
        ids = list(resolutions)
        expression = Case(
            *[When(id=job_id, then=Value(trigger_time)) for job_id, trigger_time in resolutions.items()],
            output_field=FloatField(),
        )
        with transaction.atomic():
            updated = model.objects.filter(
                id__in=ids,
                trigger_time__isnull=True,
            ).update(trigger_time=expression)

        if updated == len(ids):
            return updated, [], []

        current_values = dict(
            model.objects.filter(id__in=ids).values_list("id", "trigger_time")
        )
        concurrently_changed = [
            job_id
            for job_id, expected in resolutions.items()
            if current_values.get(job_id) is not None
            and current_values[job_id] != expected
        ]
        not_updated = [
            job_id
            for job_id in ids
            if job_id not in current_values or current_values[job_id] is None
        ]
        return updated, concurrently_changed, not_updated
