import logging
import urllib.parse

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.utils.gwflow_es import gwflow_elastic_search_update

logger = logging.getLogger(__name__)

HTTP_OK = 200


class Command(BaseCommand):
    help = "Ingest job details into Elasticsearch"

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

        self.stdout.write(f"Starting Elasticsearch ingestion for {total_jobs} bilby jobs...")

        for job in BilbyJob.objects.all():
            try:
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
