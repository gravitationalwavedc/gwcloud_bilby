# Generated by Django 3.2.9 on 2022-01-05 01:49

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0026_auto_20211210_0412"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bilbyjob",
            name="event_id",
            field=models.ForeignKey(
                default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, to="bilbyui.eventid"
            ),
        ),
    ]
