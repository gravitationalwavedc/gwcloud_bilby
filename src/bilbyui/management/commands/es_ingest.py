from django.core.management.base import BaseCommand

from bilbyui.models import BilbyJob


class Command(BaseCommand):
    help = "Ingest the mysql job details into elastic search"

    def handle(self, *args, **options):
        for job in BilbyJob.objects.all():
            job.save()

            print(job, "has been ingested into elastic search")
