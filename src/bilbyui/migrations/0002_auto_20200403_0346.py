# Generated by Django 2.2.9 on 2020-04-03 03:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prior",
            name="job",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="prior", to="bilbyui.BilbyJob"
            ),
        ),
    ]
