# Generated by Django 3.2.3 on 2021-06-06 06:11

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0019_inikeyvalue"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="inikeyvalue",
            unique_together={("job", "key")},
        ),
    ]
