# Generated by Django 2.2.19 on 2021-05-31 00:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0013_auto_20210321_2322"),
    ]

    operations = [
        migrations.AddField(
            model_name="label",
            name="protected",
            field=models.BooleanField(default=False),
        ),
    ]
