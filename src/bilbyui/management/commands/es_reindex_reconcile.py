import argparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.utils.reindex import ReindexError, reindex_jobs, verify_search_trigger_time


def batch_size(value):
    value = int(value)
    if not 1 <= value <= 200:
        raise argparse.ArgumentTypeError("--batch must be between 1 and 200")
    return value


class Command(BaseCommand):
    help = (
        "Reconcile configured Elasticsearch documents by ascending stable ID, "
        "then verify searchTriggerTime for the complete selected kind."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=("bilby", "gwflow"),
            help="Reconcile only this job kind; omit to process bilby then gwflow.",
        )
        parser.add_argument(
            "--after-id",
            type=int,
            default=0,
            help="Exclusively resume writes after this stable ID; verification still scans all rows.",
        )
        parser.add_argument(
            "--batch",
            type=batch_size,
            default=200,
            help="Keyset page size from 1 to 200 (default: 200).",
        )

    def handle(self, *_args, **options):
        if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            self.stdout.write("IGNORE_ELASTIC_SEARCH is set; es_reindex_reconcile is a no-op.")
            return

        kinds = (options["kind"],) if options["kind"] else ("bilby", "gwflow")
        for kind in kinds:
            try:
                self._reconcile_kind(kind, options["after_id"], options["batch"])
                verify_search_trigger_time(kind)
            except ReindexError as exc:
                raise CommandError(str(exc)) from exc

    def _reconcile_kind(self, kind, after_id, batch):
        if kind == "bilby":
            queryset = BilbyJob.objects.select_related(
                "event_id",
                "gwflow_job__event_id",
            )
        else:
            queryset = GWFlowJob.objects.select_related("event_id")

        cursor = after_id
        while True:
            page = list(
                queryset.filter(id__gt=cursor)
                .order_by("id")
                .values_list("id", flat=True)[:batch]
            )
            if not page:
                return

            try:
                reindex_jobs(page, kind)
            except ReindexError as exc:
                failed_ids = ",".join(str(stable_id) for stable_id in page)
                raise ReindexError(
                    f"kind={kind} failed_ids={failed_ids} status=reindex_failed"
                ) from exc

            cursor = page[-1]
            self.stdout.write(f"kind={kind} last_successful_id={cursor}")
