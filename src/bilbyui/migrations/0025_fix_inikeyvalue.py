# Generated by Django 3.2.3 on 2021-06-03 02:45

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("bilbyui", "0018_auto_20210603_0101"),
    ]

    replaces = [
        ("bilbyui", "0019_inikeyvalue"),
        ("bilbyui", "0023_alter_inikeyvalue_unique_together"),
    ]

    operations = [
        migrations.CreateModel(
            name="IniKeyValue",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.TextField(db_index=True)),
                ("value", models.TextField(db_index=True)),
                ("index", models.IntegerField()),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="bilbyui.bilbyjob")),
            ],
        ),
    ]
