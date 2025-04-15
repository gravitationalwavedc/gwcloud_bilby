from django.core.management.base import BaseCommand

from bilbyui.models import BilbyJob


class Command(BaseCommand):
    help = "Ingest the mysql job details into elastic search"

    def handle(self, *args, **options):
        for job in BilbyJob.objects.all():
            try:
                job.save()
                print(
                    f"Job {job.id} - {job.name} has been ingested into elastic search"
                )
            except Exception as e:
                print(e)
                print(
                    f"Job {job.id} - {job.name} could not be ingested - perhaps it has an empty ini_string"
                )
