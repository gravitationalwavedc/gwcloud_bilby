import logging

from django.core.management.base import BaseCommand

from bilbyui.models import BilbyJob

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Ingest the mysql job details into elastic search"

    def handle(self, *args, **options):
        total_jobs = BilbyJob.objects.count()
        success_count = 0
        error_count = 0

        self.stdout.write(f"Starting Elasticsearch ingestion for {total_jobs} jobs...")

        for job in BilbyJob.objects.all():
            try:
                job.save()
                success_count += 1
                logger.info(f"Job {job.id} - {job.name} has been ingested into Elasticsearch")
                self.stdout.write(self.style.SUCCESS(f"✓ Job {job.id} - {job.name}"))
            except Exception as e:
                error_count += 1
                logger.error(f"Job {job.id} - {job.name} could not be ingested: {str(e)}", exc_info=True)
                self.stdout.write(self.style.ERROR(f"✗ Job {job.id} - {job.name}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"\nIngestion complete: {success_count} succeeded, {error_count} failed"))
