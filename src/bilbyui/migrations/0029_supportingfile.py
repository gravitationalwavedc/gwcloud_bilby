# Generated by Django 3.2.12 on 2022-03-01 21:56

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0028_eventid_is_ligo_event"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportingFile",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file_type", models.CharField(max_length=3)),
                ("key", models.TextField(null=True)),
                ("file_name", models.TextField()),
                ("token", models.UUIDField(db_index=True, default=uuid.uuid4, null=True, unique=True)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="bilbyui.bilbyjob")),
            ],
        ),
    ]
