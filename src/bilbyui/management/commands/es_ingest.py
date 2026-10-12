import json
import logging
import math
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from elasticsearch import helpers

from bilbyui.models import BilbyJob, EventID
from bilbyui.utils.gwflow_es import (
    InvalidGWFlowMetadata,
    build_gwflow_es_doc,
    build_gwflow_es_mapping,
    clear_gwflow_portal_cache,
    compute_protected_identity_digest,
    eligible_gwflow_jobs,
    get_es_client,
    invalidate_gwflow_facet_caches,
    mapping_satisfies_contract,
)
from bilbyui.utils.gwflow_portal import get_superevent

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILURES = 1


def build_bilby_es_mapping():
    """Return the Bilby index mapping body.

    Declares the policy field explicitly as double. All other document fields
    remain dynamically mapped (Bilby documents carry many params/ini fields).
    """
    return {
        "settings": {
            "index": {
                "query": {
                    "default_field": [
                        "job.name",
                        "job.description",
                        "labels.name",
                        "labels.description",
                        "eventId.eventId",
                        "eventId.triggerId",
                        "eventId.nickname",
                        "params.label",
                        "params.waveform_approximant",
                        "params.likelihood_type",
                        "params.detectors",
                        "params.frequency_domain_source_model",
                        "params.meta_data.bilby_version",
                        "params.meta_data.bilby_pipe_version",
                        "ini.sampler",
                    ]
                }
            }
        },
        "mappings": {"properties": {"searchTriggerTime": {"type": "double"}}},
    }


class Command(BaseCommand):
    help = (
        "Ingest job details into Elasticsearch.\n\n"
        "Operational modes:\n"
        "  python manage.py es_ingest --gwflow\n"
        "      Upsert documents for every local GWFlowJob using live portal detail.\n"
        "  python manage.py es_ingest --gwflow --wipe-and-rebuild\n"
        "      Delete and recreate only settings.ELASTIC_SEARCH_GWFLOW_INDEX before rebuilding it.\n"
        "      The rebuild expects a quiescent database and is intended to run inside the maintenance "
        "writer freeze (issue #123); a concurrent write can make the before/after protected-identity "
        "digest differ and the run will fail closed.\n"
        "  python manage.py es_ingest\n"
        "      Drop and rebuild the Bilby index."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--gwflow",
            action="store_true",
            default=False,
            help="Ingest gwflow superevent records from cbcflow portal",
        )
        parser.add_argument(
            "--wipe-and-rebuild",
            action="store_true",
            help="With --gwflow, delete and recreate only the GWFlow index before rebuilding it.",
        )

    def execute(self, *args, **options):
        self._exit_code = EXIT_OK
        super().execute(*args, **options)
        if self._exit_code != EXIT_OK:
            raise CommandError(f"es_ingest exited with code {self._exit_code}", returncode=self._exit_code)
        return self._exit_code

    def handle(self, *_args, **options):
        if options["wipe_and_rebuild"] and not options["gwflow"]:
            raise CommandError("--wipe-and-rebuild requires --gwflow")
        if options["gwflow"]:
            self._exit_code = self.handle_gwflow(wipe_and_rebuild=options["wipe_and_rebuild"])
        else:
            self.handle_bilby()

    def handle_bilby(self):
        total_jobs = BilbyJob.objects.count()
        success_count = 0
        error_count = 0

        # Rebuild the bilby index from the DB so stale documents (jobs deleted
        # from the DB but still present in ES) are removed. The per-job
        # elastic_search_update() path only upserts, so without dropping the
        # index first a re-ingest would leave orphaned docs behind and the
        # public job list would keep surfacing empty pages.
        if not getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            es = get_es_client()
            es.indices.delete(index=settings.ELASTIC_SEARCH_INDEX, ignore_unavailable=True)
            es.indices.create(index=settings.ELASTIC_SEARCH_INDEX, body=build_bilby_es_mapping())

        self.stdout.write(f"Starting Elasticsearch ingestion for {total_jobs} bilby jobs...")

        for job in BilbyJob.objects.select_related("gwflow_job__event_id", "event_id").all():
            try:
                if getattr(job, "gwflow_job", None) is not None:
                    # GWFlow children always follow the parent link, including None.
                    job.event_id = job.gwflow_job.event_id
                elif job.event_id is None:
                    # GWOSC Jobs: strip version suffix, decode trigger_time, link/create EventID
                    if str(job.user_id) == str(getattr(settings, "GWOSC_INGEST_USER", "") or "") or "--" in job.name:
                        parts = job.name.split("--", 1)
                        raw_prefix = parts[0]
                        clean_prefix = re.sub(r"-v\d+$", "", raw_prefix)
                        if re.match(r"^(GW\d{6}(_\d{6})?|G\d+)$", clean_prefix):
                            ini_kv = (
                                job.inikeyvalue_set.filter(key="trigger_time", processed=True)
                                .exclude(value="null")
                                .first()
                                or job.inikeyvalue_set.filter(key="trigger_time", processed=False)
                                .exclude(value="null")
                                .first()
                                or job.inikeyvalue_set.filter(key="trigger_time", processed=True).first()
                                or job.inikeyvalue_set.filter(key="trigger_time", processed=False).first()
                            )

                            gps = None
                            if ini_kv and ini_kv.value:
                                try:
                                    val = json.loads(ini_kv.value)
                                    parsed_gps = float(val)
                                    if isinstance(val, bool):
                                        parsed_gps = None
                                except (ValueError, TypeError, OverflowError, json.JSONDecodeError, RecursionError):
                                    try:
                                        parsed_gps = float(ini_kv.value)
                                    except (ValueError, TypeError, OverflowError):
                                        parsed_gps = None
                                if parsed_gps is not None and math.isfinite(parsed_gps):
                                    gps = parsed_gps

                            if gps is None:
                                source_identifier = (
                                    f"IniKeyValue {ini_kv.id}" if ini_kv is not None else f"BilbyJob {job.id}"
                                )
                                logger.warning(
                                    "No finite GPS value for GWOSC source %s; creating EventID %s with gps_time=None",
                                    source_identifier,
                                    clean_prefix,
                                )

                            event, _ = EventID.objects.get_or_create(
                                event_id=clean_prefix,
                                defaults={"gps_time": gps},
                            )
                            job.event_id = event

                job.save()
                success_count += 1
                logger.info("Job %s - %s has been ingested into Elasticsearch", job.id, job.name)
                self.stdout.write(self.style.SUCCESS(f"✓ Job {job.id} - {job.name}"))
            except Exception as e:
                error_count += 1
                logger.exception("Job %s - %s could not be ingested", job.id, job.name)
                self.stdout.write(self.style.ERROR(f"✗ Job {job.id} - {job.name}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nIngestion complete: {success_count} succeeded, {error_count} failed"))

    def _run_gwflow_query_checks(self, es, index, docs_by_id, record_failure):
        """Run the five deterministic wipe-mode query gates."""
        checks = []

        snames = sorted(
            {
                doc["_gwcloud"]["sname"]
                for doc in docs_by_id.values()
                if doc.get("_gwcloud", {}).get("sname") is not None
            }
        )
        if snames:
            sname = snames[0]
            checks.append(
                (
                    f"sname={sname}",
                    {"term": {"_gwcloud.sname": sname}},
                    {pk for pk, doc in docs_by_id.items() if doc.get("_gwcloud", {}).get("sname") == sname},
                )
            )
        else:
            record_failure(
                "query",
                reason="sname query gate: no document carries _gwcloud.sname",
            )

        for field in ("type", "status", "review_status"):
            values = sorted(
                {
                    analysis[field]
                    for doc in docs_by_id.values()
                    for analysis in (doc.get("metadata", {}).get("analyses") or [])
                    if analysis.get(field) is not None
                },
                key=lambda value: str(value),
            )
            if not values:
                # Do not query an absent value: an empty expected set would trivially
                # pass and hide a genuine problem with the rebuilt corpus.
                record_failure(
                    "query",
                    reason=(f"analyses.{field} query gate: no analysis carries metadata.analyses.{field}"),
                )
                continue

            value = values[0]
            checks.append(
                (
                    f"analyses.{field}={value}",
                    {"term": {f"metadata.analyses.{field}": value}},
                    {
                        pk
                        for pk, doc in docs_by_id.items()
                        if any(
                            analysis.get(field) == value for analysis in (doc.get("metadata", {}).get("analyses") or [])
                        )
                    },
                )
            )

        checks.append(
            (
                "searchTriggerTime range [100, 200)",
                {
                    "range": {
                        "_gwcloud.searchTriggerTime": {
                            "gte": 100.0,
                            "lt": 200.0,
                        }
                    }
                },
                {
                    pk
                    for pk, doc in docs_by_id.items()
                    if isinstance(
                        doc.get("_gwcloud", {}).get("searchTriggerTime"),
                        (int, float),
                    )
                    and 100.0 <= float(doc["_gwcloud"]["searchTriggerTime"]) < 200.0
                },
            )
        )

        for label, query, expected in checks:
            try:
                response = es.search(index=index, query=query, size=10000)
            except Exception as exc:
                record_failure("query", reason=f"{label}: search failed: {exc}")
                continue
            actual = {str(hit["_id"]) for hit in response.get("hits", {}).get("hits", [])}
            if actual != expected:
                record_failure(
                    "query",
                    reason=f"{label}: expected ids {sorted(expected)} got {sorted(actual)}",
                )
            else:
                self.stdout.write(f"✓ query {label}: {len(actual)} hit(s)")

    def handle_gwflow(self, wipe_and_rebuild=False):
        if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            raise CommandError("IGNORE_ELASTIC_SEARCH must be false to run --gwflow ingestion")

        portal_url = getattr(settings, "CBCFLOW_PORTAL_URL", None)
        portal_token = getattr(settings, "CBCFLOW_PORTAL_TOKEN", None)
        if not portal_url or not portal_token:
            raise CommandError("CBCFLOW_PORTAL_URL and CBCFLOW_PORTAL_TOKEN must be set to run --gwflow ingestion.")

        index = settings.ELASTIC_SEARCH_GWFLOW_INDEX
        failures = []
        actions = []
        jobs_by_id = {}
        docs_by_id = {}
        eligible_jobs = list(eligible_gwflow_jobs())
        eligible_ids = {str(job.pk) for job in eligible_jobs}

        def record_failure(phase, job=None, *, pk=None, sname=None, reason):
            # A durable machine-readable failure record is deliberately deferred to
            # issue #118 and is owned by the issue #123 cutover runbook.
            if job is not None:
                pk = job.pk
                sname = job.sname
                version_number = job.current_version_number
            else:
                version_number = None
            failure = {
                "phase": phase,
                "sname": sname,
                "pk": pk,
                "current_version_number": version_number,
                "reason": str(reason),
            }
            failures.append(failure)
            line = f"✗ phase={phase} sname={sname} pk={pk} reason={reason}"
            self.stdout.write(self.style.ERROR(line))
            logger.error(line)

        for job in eligible_jobs:
            clear_gwflow_portal_cache(job.sname)
            try:
                data, state = get_superevent(job.sname)
            except Exception as exc:
                record_failure("fetch", job, reason=exc)
                logger.exception(
                    "GWFlow fetch raised for sname=%s pk=%s version=%s",
                    job.sname,
                    job.pk,
                    job.current_version_number,
                )
                continue

            if state != "live" or not isinstance(data, dict):
                reason = f"state={state}; expected live state with object data"
                record_failure("fetch", job, reason=reason)
                continue

            try:
                doc = build_gwflow_es_doc(job, data)
            except InvalidGWFlowMetadata as exc:
                record_failure("build", job, reason=exc)
                continue

            action = {
                "_op_type": "index",
                "_index": index,
                "_id": str(job.id),
                "_source": doc,
            }
            actions.append(action)
            jobs_by_id[str(job.id)] = job
            docs_by_id[str(job.id)] = doc

        before = compute_protected_identity_digest()
        logger.info("GWFlow protected PostgreSQL identity digest before ES: %s", before)

        try:
            es = get_es_client()
        except Exception as exc:
            record_failure("client", reason=exc)
            es = None

        expected_mapping = build_gwflow_es_mapping()
        if es is not None and wipe_and_rebuild:
            try:
                es.indices.delete(index=index, ignore_unavailable=True)
                es.indices.create(index=index, body=expected_mapping)
            except Exception as exc:
                record_failure("mapping", reason=f"index recreation failed: {exc}")

        submitted_ids = {str(action["_id"]) for action in actions}
        indexed_ids = set()
        failed_ids = set()

        if es is not None and actions and not any(failure["phase"] == "mapping" for failure in failures):
            try:
                results = helpers.streaming_bulk(
                    es,
                    actions,
                    raise_on_error=False,
                    raise_on_exception=False,
                    refresh=True,
                    chunk_size=500,
                )
                for ok, item in results:
                    if not isinstance(item, dict) or len(item) != 1:
                        record_failure(
                            "bulk",
                            reason=f"malformed/unknown item result: {item!r}",
                        )
                        continue

                    operation_name, operation = next(iter(item.items()))
                    if operation_name != "index" or not isinstance(operation, dict):
                        record_failure(
                            "bulk",
                            reason=f"malformed/unknown item result: {item!r}",
                        )
                        continue

                    item_id = operation.get("_id")
                    item_id = str(item_id) if item_id is not None else None
                    if item_id not in submitted_ids:
                        record_failure(
                            "bulk",
                            pk=item_id,
                            reason=f"malformed/unknown item result: {item!r}",
                        )
                        continue

                    job = jobs_by_id[item_id]
                    if item_id in failed_ids:
                        record_failure(
                            "bulk",
                            job,
                            reason="malformed/unknown item result: duplicate item result",
                        )
                        continue

                    if ok is False:
                        failed_ids.add(item_id)
                        error = operation.get("error")
                        if isinstance(error, dict):
                            reason = error.get("reason") or str(error)
                        else:
                            reason = error or "unknown bulk indexing error"
                        status = operation.get("status")
                        if status is not None:
                            reason = f"{reason} (status={status})"
                        record_failure("bulk", job, reason=reason)
                        indexed_ids.discard(item_id)
                        continue

                    status = operation.get("status")
                    valid_success = (
                        ok is True
                        and operation.get("_index") == index
                        and isinstance(status, int)
                        and 200 <= status <= 299
                    )
                    if not valid_success:
                        failed_ids.add(item_id)
                        indexed_ids.discard(item_id)
                        record_failure(
                            "bulk",
                            job,
                            reason=f"malformed/unknown item result: {item!r}",
                        )
                        continue

                    if item_id in indexed_ids:
                        indexed_ids.remove(item_id)
                        failed_ids.add(item_id)
                        record_failure(
                            "bulk",
                            job,
                            reason="malformed/unknown item result: duplicate success",
                        )
                        continue

                    indexed_ids.add(item_id)
            except Exception as exc:
                logger.exception("GWFlow bulk indexing raised: %s", exc)
                for item_id in submitted_ids - failed_ids:
                    failed_ids.add(item_id)
                    indexed_ids.discard(item_id)
                    record_failure("bulk", jobs_by_id[item_id], reason=exc)

            for item_id in submitted_ids - indexed_ids - failed_ids:
                failed_ids.add(item_id)
                record_failure(
                    "bulk",
                    jobs_by_id[item_id],
                    reason="missing item result",
                )

        indexed_jobs = [jobs_by_id[item_id] for item_id in indexed_ids]

        if es is not None and wipe_and_rebuild:
            try:
                es.indices.refresh(index=index)
            except Exception as exc:
                record_failure("refresh", reason=exc)

            try:
                mapping_response = es.indices.get_mapping(index=index)
                installed_mapping = mapping_response[index]["mappings"]
                if not mapping_satisfies_contract(expected_mapping["mappings"], installed_mapping):
                    record_failure(
                        "mapping",
                        reason=(
                            "installed mapping does not satisfy the contract: "
                            f"expected={expected_mapping['mappings']!r} "
                            f"actual={installed_mapping!r}"
                        ),
                    )
            except Exception as exc:
                record_failure("mapping", reason=f"mapping verification failed: {exc}")

            try:
                count = es.count(index=index)["count"]
                if count != len(eligible_ids):
                    record_failure(
                        "parity",
                        reason=f"index count {count} != eligible {len(eligible_ids)}",
                    )
            except Exception as exc:
                record_failure("parity", reason=f"count verification failed: {exc}")

            try:
                id_response = es.search(
                    index=index,
                    query={"match_all": {}},
                    size=max(len(eligible_ids), 1),
                    _source=False,
                )
                actual_ids = {str(hit["_id"]) for hit in id_response.get("hits", {}).get("hits", [])}
                if actual_ids != eligible_ids:
                    record_failure(
                        "parity",
                        reason=(
                            f"index ids differ from eligible ids: "
                            f"missing={sorted(eligible_ids - actual_ids)} "
                            f"unexpected={sorted(actual_ids - eligible_ids)}"
                        ),
                    )
            except Exception as exc:
                record_failure("parity", reason=f"id-set verification failed: {exc}")

            self._run_gwflow_query_checks(
                es,
                index,
                docs_by_id,
                record_failure,
            )

        after = compute_protected_identity_digest()
        logger.info("GWFlow protected PostgreSQL identity digest after ES: %s", after)
        if before != after:
            record_failure(
                "postgres",
                reason=f"protected identity digest changed: before={before} after={after}",
            )

        if not failures and wipe_and_rebuild:
            invalidate_gwflow_facet_caches()

        failed_index_ids = {
            str(failure["pk"]) for failure in failures if failure["phase"] == "bulk" and failure["pk"] is not None
        }
        indexed_jobs = [job for job in indexed_jobs if str(job.pk) not in failed_index_ids]
        for job in indexed_jobs:
            line = f"✓ GWFlowJob {job.pk} ({job.sname}) indexed"
            self.stdout.write(self.style.SUCCESS(line))
            logger.info(line)

        self.stdout.write(f"{len(indexed_jobs)} indexed, {len(failures)} failed")
        return EXIT_FAILURES if failures else EXIT_OK
