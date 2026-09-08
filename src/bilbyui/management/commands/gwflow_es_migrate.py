import logging

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from elasticsearch import helpers

from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY
from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata, build_gwflow_es_doc, get_es_client
from bilbyui.utils.gwflow_portal import get_version

logger = logging.getLogger("bilbyui.gwflow_es")

EXIT_OK = 0
EXIT_FAILURES = 1

_GWCLOUD_STRICT_FIELDS = {
    "sname": {"type": "keyword"},
    "libraries": {"type": "keyword"},
    "isPruned": {"type": "boolean"},
    "ligoOnly": {"type": "boolean"},
    "lastUpdatedTime": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
    "reviewStatuses": {"type": "keyword"},
    "eventTriggerId": {"type": "keyword"},
}

_DEFAULT_FIELD = [
    "_gwcloud.sname",
    "_gwcloud.libraries",
    "_gwcloud.reviewStatuses",
    "_gwcloud.eventTriggerId",
]


def build_gwflow_es_mapping():
    """Return the strict mapping body used to (re)create the GWFlow index."""
    return {
        "settings": {
            "index.mapping.total_fields.limit": 10000,
            "index.mapping.depth.limit": 100,
            "index.query.default_field": list(_DEFAULT_FIELD),
        },
        "mappings": {
            "date_detection": False,
            "numeric_detection": False,
            "dynamic_templates": [
                {
                    "metadata_strings": {
                        "path_match": "metadata.*",
                        "match_mapping_type": "string",
                        "mapping": {
                            "type": "text",
                            "fields": {
                                "keyword": {"type": "keyword", "ignore_above": 1024}
                            },
                        },
                    }
                }
            ],
            "properties": {
                "_gwcloud": {
                    "type": "object",
                    "dynamic": "strict",
                    "properties": dict(_GWCLOUD_STRICT_FIELDS),
                },
                "metadata": {"type": "object", "dynamic": True},
            },
        },
    }


def measure_doc(doc):
    """Return (field_count, max_depth) for a built document via a deterministic
    traversal. Preserves the information a measured capacity preflight would
    have given, without a separate measurement pass."""
    field_count = 0
    max_depth = 0

    def walk(node, depth):
        nonlocal field_count, max_depth
        max_depth = max(max_depth, depth)
        if isinstance(node, dict):
            field_count += len(node)
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(doc, 0)
    return field_count, max_depth


def extract_item_failures(errors):
    """Return the per-item failures (status >= 300) from a helpers.bulk result."""
    failures = []
    for item in errors or []:
        info = item.get("index") or item.get("create") or item
        if info.get("status", 0) >= 300:
            failures.append(info)
    return failures


class PortalUnavailable(Exception):
    """Raised when the portal is down or returns no data for a job."""


class Command(BaseCommand):
    help = (
        "Drop-and-recreate migration for the GWFlow Elasticsearch index: delete the "
        "concrete index, recreate it with the strict _gwcloud mapping, and reimport "
        "all GWFlowJob documents from the cbcflow portal via the #70 builder."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Perform portal reads and doc building only; no ES writes or cache invalidation.",
        )

    def execute(self, *args, **options):
        # Return the exit code from execute() without Django writing it to stdout.
        # A non-zero code is surfaced as a CommandError so run_from_argv sets the
        # process exit code (Django otherwise discards execute()'s return value).
        self._exit_code = EXIT_OK
        super().execute(*args, **options)
        if self._exit_code != EXIT_OK:
            raise CommandError(
                f"gwflow_es_migrate exited with code {self._exit_code}",
                returncode=self._exit_code,
            )
        return self._exit_code

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            self.stdout.write("IGNORE_ELASTIC_SEARCH is set; gwflow_es_migrate is a no-op.")
            return

        index = settings.ELASTIC_SEARCH_GWFLOW_INDEX
        es = get_es_client()

        jobs = list(GWFlowJob.objects.select_related("event_id").order_by("id"))
        docs = []
        failures = []

        for job in jobs:
            try:
                data, state = get_version(job.sname, job.current_history_id)
                if state == "down" or data is None:
                    raise PortalUnavailable(
                        f"could not fetch version {job.current_history_id} for {job.sname} (state={state})"
                    )
                doc = build_gwflow_es_doc(job, data)
                docs.append((job, doc))
            except (PortalUnavailable, InvalidGWFlowMetadata) as exc:
                failures.append((job, str(exc)))
                logger.warning("gwflow_es_migrate: build failed for job %s (%s): %s", job.id, job.sname, exc)
                self.stderr.write(self.style.ERROR(f"✗ Job {job.id} ({job.sname}): {exc}"))
            except Exception as exc:
                failures.append((job, str(exc)))
                logger.exception("gwflow_es_migrate: unexpected failure for job %s (%s)", job.id, job.sname)
                self.stderr.write(self.style.ERROR(f"✗ Job {job.id} ({job.sname}): {exc}"))

        for job, doc in docs:
            field_count, max_depth = measure_doc(doc)
            logger.info(
                "gwflow_es_migrate: job %s (%s): %d fields, max depth %d",
                job.id,
                job.sname,
                field_count,
                max_depth,
            )

        if failures:
            self.stdout.write(
                self.style.ERROR(
                    f"Refusing to proceed: {len(failures)} document(s) could not be built from the portal."
                )
            )
            self._exit_code = EXIT_FAILURES
            return

        if dry_run:
            self.stdout.write(
                f"Dry run: would delete, recreate, and reimport {len(docs)} document(s) into {index}."
            )
            self._exit_code = EXIT_OK
            return

        # Delete then recreate immediately, in the same command. Creating the
        # index right after deleting it closes the auto-index-creation race and
        # makes the command idempotent and safely re-runnable.
        es.indices.delete(index=index, ignore_unavailable=True)
        es.indices.create(index=index, body=build_gwflow_es_mapping())

        actions = [
            {"_op_type": "index", "_index": index, "_id": job.id, "_source": doc}
            for job, doc in docs
        ]
        _, errors = helpers.bulk(es, actions, stats_only=False, raise_on_error=False, refresh=True)

        item_failures = extract_item_failures(errors)
        for failure in item_failures:
            logger.error("gwflow_es_migrate: bulk item failure: %s", failure)
            self.stderr.write(self.style.ERROR(f"✗ Bulk item failure: {failure}"))

        target_count = es.count(index=index)["count"]
        source_count = len(docs)
        self.stdout.write(f"Count check: source={source_count}, target={target_count}")

        if not item_failures and target_count == source_count:
            cache.delete(LIBRARIES_CACHE_KEY)
            cache.delete(REVIEW_STATUSES_CACHE_KEY)
            self.stdout.write("Invalidated filter-option cache keys after successful reimport")
            self._exit_code = EXIT_OK
        else:
            self._exit_code = EXIT_FAILURES
