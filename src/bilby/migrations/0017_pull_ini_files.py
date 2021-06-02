from urllib import request

from django.db import migrations
from django.conf import settings

from bilby.utils.jobs.request_file_download_id import request_file_download_id
from bilby.utils.jobs.request_file_list import request_file_list


def pull_ini_files(apps, schema_editor):
    BilbyJob = apps.get_model("bilby", "BilbyJob")

    for job in BilbyJob.objects.all():
        try:
            # Try to get the root file list for the job
            success, result = request_file_list(job, '', False)
            if not success:
                print(f"Unable to fetch ini file for {job} because {result}")
                continue

            # Try to find the ini file for the job
            path = None
            for f in result:
                if f['path'].endswith('config_complete.ini'):
                    path = f['path']

            # Check we found the ini file
            if not path:
                print(f'Job {job} did not have an ini file')
                continue

            # Fetch the ini file from the job server
            success, dl_id = request_file_download_id(job, path)
            ini_data = request.urlopen(f'{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/?fileId={dl_id}').read()

            # Set the job's ini string
            job.ini_string = ini_data.decode('utf-8')
            job.save()

            print(f"Successfully fetched ini file for Job {job}")

        except:
            print(f"Unable to fetch ini file for {job} reason unknown - job server did not return 200.")


class Migration(migrations.Migration):

    dependencies = [
        ('bilby', '0016_merge_20210601_0127'),
    ]

    operations = [
        migrations.RunPython(pull_ini_files),
    ]
