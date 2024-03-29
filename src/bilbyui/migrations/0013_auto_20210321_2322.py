# Generated by Django 2.2.19 on 2021-03-21 23:22

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0012_insert_default_labels"),
    ]

    operations = [
        migrations.AddField(
            model_name="bilbyjob",
            name="is_ligo_job",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="data",
            name="data_choice",
            field=models.CharField(
                choices=[["simulated", "Simulated"], ["real", "Real"]], default="simulated", max_length=20
            ),
        ),
    ]
