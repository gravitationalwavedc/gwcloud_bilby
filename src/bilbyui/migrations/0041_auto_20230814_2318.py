# Generated by Django 3.2.20 on 2023-08-14 23:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0040_alter_bilbyjob_ini_string"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bilbyjob",
            name="job_type",
            field=models.IntegerField(choices=[(0, "Normal Job"), (1, "Uploaded Job"), (2, "External Job")], default=0),
        ),
        migrations.CreateModel(
            name="ExternalBilbyJob",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("url", models.URLField()),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="bilbyui.bilbyjob")),
            ],
        ),
    ]
