# Generated by Django 3.2.3 on 2021-06-07 02:45

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0016_merge_20210601_0127'),
    ]

    operations = [
        migrations.RenameField(
            model_name='bilbyjob',
            old_name='job_id',
            new_name='job_controller_id',
        ),
    ]