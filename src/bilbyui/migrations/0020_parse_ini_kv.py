from django.db import migrations

from bilbyui.utils.parse_ini_file import parse_ini_file


def forward_parse_ini_files(apps, schema_editor):
    BilbyJob = apps.get_model("bilbyui", "BilbyJob")
    IniKeyValue = apps.get_model("bilbyui", "IniKeyValue")

    for job in BilbyJob.objects.all():
        # Parse the ini file and store the config as key/value pairs
        parse_ini_file(job, IniKeyValue)


def reverse_parse_ini_files(apps, schema_editor):
    BilbyJob = apps.get_model("bilbyui", "BilbyJob")
    IniKeyValue = apps.get_model("bilbyui", "IniKeyValue")

    for job in BilbyJob.objects.all():
        # Only destroy the IniKeyValues if it's non-destructive (We have a copy of the ini file in the job)
        if job.ini_string:
            IniKeyValue.objects.filter(job=job).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0019_inikeyvalue'),
    ]

    operations = [
        migrations.RunPython(forward_parse_ini_files, reverse_code=reverse_parse_ini_files),
    ]
