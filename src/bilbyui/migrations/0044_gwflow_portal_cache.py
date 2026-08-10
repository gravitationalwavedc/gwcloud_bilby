from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    call_command("createcachetable", "gwflow_portal_cache", database=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [("bilbyui", "0043_bilbyjob_gwflow_analysis_uid_gwflowjob_and_more")]
    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
