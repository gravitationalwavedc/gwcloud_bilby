# Generated by Django 2.2.9 on 2020-03-31 03:32
import django.db.models.deletion
from django.core.management import call_command
from django.db import migrations, models, DEFAULT_DB_ALIAS, connections
from django.db.migrations.recorder import MigrationRecorder


def check_migrations(apps, schema_editor):
    # Get the internal django migration model
    Migrations = MigrationRecorder.Migration

    if Migrations.objects.filter(app="bilby").exists():
        print("\nFound historic bilby migrations, changing that to bilbiui...")

        # Find any migrations for the bilby app, and rename the app to bilbyui
        for m in Migrations.objects.filter(app="bilby"):
            m.app = "bilbyui"
            m.save()

        # Force commit the transaction
        connections[DEFAULT_DB_ALIAS].in_atomic_block = False
        connections[DEFAULT_DB_ALIAS].commit()

        # Run migrations again
        print("Ok, done with that, now re-running migrations...\n")
        call_command("migrate")

        # Make sure any new migrations are applied
        connections[DEFAULT_DB_ALIAS].in_atomic_block = False
        connections[DEFAULT_DB_ALIAS].commit()

        # Nothing more to do
        exit(0)


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(check_migrations),
        migrations.CreateModel(
            name="BilbyJob",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_id", models.IntegerField()),
                ("username", models.CharField(max_length=30)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, null=True)),
                ("creation_time", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "bilby_bilbyjob",
                "unique_together": {("username", "name")},
            },
        ),
        migrations.CreateModel(
            name="Data",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "data_choice",
                    models.CharField(
                        choices=[["simulated", "Simulated"], ["open", "Open"]], default="simulated", max_length=20
                    ),
                ),
                (
                    "job",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="data", to="bilbyui.BilbyJob"
                    ),
                ),
            ],
            options={
                "db_table": "bilby_data",
            },
        ),
        migrations.CreateModel(
            name="Sampler",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "sampler_choice",
                    models.CharField(
                        choices=[["dynesty", "Dynesty"], ["nestle", "Nestle"], ["emcee", "Emcee"]],
                        default="dynesty",
                        max_length=15,
                    ),
                ),
                (
                    "job",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="sampler", to="bilbyui.BilbyJob"
                    ),
                ),
            ],
            options={
                "db_table": "bilby_sampler",
            },
        ),
        migrations.CreateModel(
            name="Signal",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "signal_choice",
                    models.CharField(
                        choices=[["skip", "None"], ["binaryBlackHole", "Binary Black Hole"]],
                        default="skip",
                        max_length=50,
                    ),
                ),
                ("signal_model", models.CharField(choices=[["binaryBlackHole", "Binary Black Hole"]], max_length=50)),
                (
                    "job",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, related_name="signal", to="bilbyui.BilbyJob"
                    ),
                ),
            ],
            options={
                "db_table": "bilby_signal",
            },
        ),
        migrations.CreateModel(
            name="SignalParameter",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "name",
                    models.CharField(
                        choices=[
                            ["mass1", "Mass 1"],
                            ["mass2", "Mass 2"],
                            ["luminosity_distance", "Luminosity Distance (Mpc)"],
                            ["iota", "iota"],
                            ["psi", "psi"],
                            ["phase", "Phase"],
                            ["merger_time", "Merger Time (GPS Time)"],
                            ["ra", "Right Ascension (Radians)"],
                            ["dec", "Declination (Degrees)"],
                        ],
                        max_length=20,
                    ),
                ),
                ("value", models.FloatField(blank=True, null=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="signal_parameter",
                        to="bilbyui.BilbyJob",
                    ),
                ),
                (
                    "signal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="parameter", to="bilbyui.Signal"
                    ),
                ),
            ],
            options={
                "db_table": "bilby_signalparameter",
            },
        ),
        migrations.CreateModel(
            name="SamplerParameter",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50)),
                ("value", models.CharField(blank=True, max_length=50, null=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sampler_parameter",
                        to="bilbyui.BilbyJob",
                    ),
                ),
                (
                    "sampler",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="parameter", to="bilbyui.Sampler"
                    ),
                ),
            ],
            options={
                "db_table": "bilby_samplerparameter",
            },
        ),
        migrations.CreateModel(
            name="DataParameter",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "name",
                    models.CharField(
                        choices=[
                            ["hanford", "Hanford"],
                            ["livingston", "Livingston"],
                            ["virgo", "Virgo"],
                            ["signal_duration", "Signal Duration (s)"],
                            ["sampling_frequency", "Sampling Frequency (Hz)"],
                            ["start_time", "Start Time"],
                        ],
                        max_length=20,
                    ),
                ),
                ("value", models.CharField(blank=True, max_length=1000, null=True)),
                (
                    "data",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="parameter", to="bilbyui.Data"
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="data_parameter",
                        to="bilbyui.BilbyJob",
                    ),
                ),
            ],
            options={
                "db_table": "bilby_dataparameter",
            },
        ),
        migrations.CreateModel(
            name="Prior",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50)),
                (
                    "prior_choice",
                    models.CharField(
                        choices=[["fixed", "Fixed"], ["uniform", "Uniform"]], default="fixed", max_length=20
                    ),
                ),
                ("fixed_value", models.FloatField(blank=True, null=True)),
                ("uniform_min_value", models.FloatField(blank=True, null=True)),
                ("uniform_max_value", models.FloatField(blank=True, null=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="job_prior", to="bilbyui.BilbyJob"
                    ),
                ),
            ],
            options={
                "db_table": "bilby_prior",
                "unique_together": {("job", "name")},
            },
        ),
    ]
