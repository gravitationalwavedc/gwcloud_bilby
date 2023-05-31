from django.core.management.base import BaseCommand, CommandError

from bilbyui.models import BilbyJob


class Command(BaseCommand):
    help = "Ingest the mysql job details in to elastic search"

    def handle(self, *args, **options):
        for job in BilbyJob.objects.all():
            job.elastic_search_update()

            print(job, "has been ingested in to elastic search")