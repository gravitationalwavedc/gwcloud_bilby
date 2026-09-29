import json
import logging
import re
import urllib.parse

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.utils.gwflow_es import get_es_client, gwflow_elastic_search_update

logger = logging.getLogger(__name__)

HTTP_OK = 200


class Command(BaseCommand):
    help = (
        "Ingest job details into Elasticsearch.\n\n"
        "Operational sequencing:\n"
        "  Step 1: python manage.py es_ingest --gwflow\n"
        "          Populate/create EventID rows for all superevents and link GWFlowJob.event_id,\n"
        "          cascading to child bilby_jobs.\n"
        "  Step 2: python manage.py es_ingest\n"
        "          Drop and rebuild the Bilby index, backfilling GWOSC jobs and linking\n"
        "          child Bilby jobs to their established parent EventID."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--gwflow",
            action="store_true",
            default=False,
            help="Ingest gwflow superevent records from cbcflow portal",
        )

    def handle(self, *_args, **options):
        if options.get("gwflow"):
            self.handle_gwflow()
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

        self.stdout.write(f"Starting Elasticsearch ingestion for {total_jobs} bilby jobs...")

        for job in BilbyJob.objects.select_related("gwflow_job__event_id", "event_id").all():
            try:
                if job.event_id is None:
                    # GWFlow Child Jobs: inherit parent superevent EventID if available
                    if getattr(job, "gwflow_job", None) is not None:
                        if job.gwflow_job.event_id is not None:
                            job.event_id = job.gwflow_job.event_id
                        else:
                            event = EventID.objects.filter(
                                Q(trigger_id=job.gwflow_job.sname) | Q(event_id=job.gwflow_job.sname)
                            ).first()
                            if event:
                                job.event_id = event
                    # GWOSC Jobs: strip version suffix, decode trigger_time, link/create EventID
                    elif str(job.user_id) == str(getattr(settings, "GWOSC_INGEST_USER", "") or "") or "--" in job.name:
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

                            gps = 1126259462.391
                            if ini_kv and ini_kv.value:
                                try:
                                    val = json.loads(ini_kv.value)
                                    gps = float(val)
                                except (ValueError, TypeError, json.JSONDecodeError):
                                    try:
                                        gps = float(ini_kv.value)
                                    except (ValueError, TypeError):
                                        gps = 1126259462.391

                            event, _ = EventID.objects.get_or_create(
                                event_id=clean_prefix,
                                defaults={"gps_time": gps, "is_ligo_event": job.is_ligo_job},
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

    def handle_gwflow(self):
        portal_url = getattr(settings, "CBCFLOW_PORTAL_URL", None)
        portal_token = getattr(settings, "CBCFLOW_PORTAL_TOKEN", None)

        if not portal_url or not portal_token:
            msg = "CBCFLOW_PORTAL_URL and CBCFLOW_PORTAL_TOKEN must be set to run --gwflow ingestion."
            self.stderr.write(self.style.ERROR(msg))
            logger.error(msg)
            return

        headers = {"Authorization": portal_token}
        base_url = portal_url.rstrip("/")
        next_url = f"{base_url}/api/v1/superevents/?page=1"

        success_count = 0
        skip_count = 0
        error_count = 0

        self.stdout.write("Starting Elasticsearch ingestion for gwflow jobs from portal...")

        while next_url:
            try:
                response = requests.get(next_url, headers=headers, timeout=30)
                if response.status_code != HTTP_OK:
                    msg = f"Failed to fetch superevents list from portal: HTTP {response.status_code}"
                    self.stderr.write(self.style.ERROR(msg))
                    logger.error(msg)
                    break

                try:
                    data = response.json()
                except ValueError:
                    msg = "Portal returned invalid JSON for superevents list"
                    self.stdout.write(self.style.WARNING(msg))
                    logger.warning(msg)
                    break
                results = data.get("results") if isinstance(data, dict) and "results" in data else data
                if not isinstance(results, list):
                    msg = f"Unexpected portal response shape: {type(data)}"
                    self.stderr.write(self.style.ERROR(msg))
                    logger.error(msg)
                    break

                for item in results:
                    sname = (item.get("sname") or item.get("name")) if isinstance(item, dict) else str(item)
                    if not sname:
                        continue

                    # Fetch detail payload for this superevent
                    detail_url = f"{base_url}/api/v1/superevents/{urllib.parse.quote(sname)}/"
                    try:
                        detail_resp = requests.get(detail_url, headers=headers, timeout=30)
                    except requests.RequestException as e:
                        self.stdout.write(self.style.WARNING(f"Skipping {sname}: portal detail request failed: {e}"))
                        error_count += 1
                        continue
                    if detail_resp.status_code != HTTP_OK:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping {sname}: portal detail returned HTTP {detail_resp.status_code}"
                            )
                        )
                        error_count += 1
                        continue

                    try:
                        metadata = detail_resp.json()
                    except ValueError:
                        self.stdout.write(self.style.WARNING(f"Skipping {sname}: portal detail returned invalid JSON"))
                        error_count += 1
                        continue

                    job = GWFlowJob.objects.filter(sname=sname).first()

                    if not job:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping {sname}: no matching local GWFlowJob record found")
                        )
                        skip_count += 1
                        continue

                    try:
                        if job.event_id is None:
                            event = EventID.objects.filter(Q(trigger_id=sname) | Q(event_id=sname)).first()
                            if event is None and isinstance(metadata, dict):
                                raw = (
                                    metadata.get("raw_payload") if isinstance(metadata.get("raw_payload"), dict) else {}
                                )
                                gracedb = (
                                    metadata.get("GraceDB")
                                    or metadata.get("gracedb")
                                    or raw.get("GraceDB")
                                    or raw.get("gracedb")
                                    or {}
                                )
                                if not isinstance(gracedb, dict):
                                    gracedb = {}
                                preferred_uid = gracedb.get("preferred_event") or gracedb.get("preferred_event_uid")
                                events = gracedb.get("Events") or gracedb.get("events") or []
                                if not isinstance(events, list):
                                    events = []

                                chosen = None
                                if preferred_uid:
                                    for ev in events:
                                        if isinstance(ev, dict) and (
                                            ev.get("UID") == preferred_uid or ev.get("uid") == preferred_uid
                                        ):
                                            chosen = ev
                                            break
                                if chosen is None:
                                    for ev in events:
                                        if isinstance(ev, dict):
                                            st = ev.get("state") or ev.get("State")
                                            if isinstance(st, str) and st.lower() == "preferred":
                                                chosen = ev
                                                break
                                if chosen is None and events:
                                    if isinstance(events[0], dict):
                                        chosen = events[0]

                                chosen_uid = None
                                gps_time = None
                                if chosen:
                                    chosen_uid = chosen.get("UID") or chosen.get("uid") or preferred_uid
                                    gps_time = (
                                        chosen.get("GPSTime")
                                        or chosen.get("gps_time")
                                        or chosen.get("gpstime")
                                        or gracedb.get("preferred_event_gps")
                                        or gracedb.get("gps_time")
                                    )
                                elif preferred_uid:
                                    chosen_uid = preferred_uid
                                    gps_time = gracedb.get("preferred_event_gps") or gracedb.get("gps_time")

                                gps_val = 1126259462.391
                                if gps_time is not None:
                                    try:
                                        val = json.loads(gps_time) if isinstance(gps_time, str) else gps_time
                                        gps_val = float(val)
                                    except (ValueError, TypeError, json.JSONDecodeError):
                                        try:
                                            gps_val = float(gps_time)
                                        except (ValueError, TypeError):
                                            gps_val = 1126259462.391

                                if chosen_uid and re.match(r"^(GW\d{6}(_\d{6})?|G\d+)$", str(chosen_uid)):
                                    event, _ = EventID.objects.get_or_create(
                                        event_id=chosen_uid,
                                        defaults={
                                            "trigger_id": sname,
                                            "gps_time": gps_val,
                                            "is_ligo_event": job.ligo_only,
                                        },
                                    )

                            if event is not None:
                                update_fields = []
                                if job.ligo_only and not event.is_ligo_event:
                                    event.is_ligo_event = True
                                    update_fields.append("is_ligo_event")
                                if (
                                    not event.trigger_id
                                    and sname
                                    and re.match(r"^(S\d{6}[a-z]{1,2}|G\d+)$", str(sname))
                                ):
                                    event.trigger_id = sname
                                    update_fields.append("trigger_id")
                                if update_fields:
                                    event.save(update_fields=update_fields)

                                job.event_id = event
                                job.save()

                        # Decoupled child cascade: executes whenever job.event_id is not None
                        if job.event_id is not None:
                            for child in job.bilby_jobs.filter(event_id__isnull=True):
                                child.event_id = job.event_id
                                child.save()

                        gwflow_elastic_search_update(job, metadata)
                        success_count += 1
                        self.stdout.write(self.style.SUCCESS(f"✓ GWFlowJob {job.id} ({sname}) ingested"))
                    except Exception as e:
                        error_count += 1
                        logger.exception("Error ingesting GWFlowJob %s (%s)", job.id, sname)
                        self.stdout.write(self.style.ERROR(f"✗ GWFlowJob {job.id} ({sname}): {e}"))

                # Determine next page URL
                next_page = data.get("next") if isinstance(data, dict) else None
                next_url = next_page or None

            except Exception as e:
                msg = f"Error during gwflow ingestion loop: {e}"
                self.stderr.write(self.style.ERROR(msg))
                logger.exception(msg)
                break

        self.stdout.write(
            self.style.SUCCESS(
                f"\nGWFlow ingestion complete: {success_count} succeeded, {skip_count} skipped, {error_count} failed"
            )
        )
