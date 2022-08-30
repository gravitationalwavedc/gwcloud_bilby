from django.db import migrations


def update_preferred_label(apps, schema_editor):
    Label = apps.get_model("bilbyui", "Label")

    for label in Label.objects.filter(name='Preferred'):
        label.name = "Official"


def rollback_preferred_label(apps, schema_editor):
    Label = apps.get_model("bilbyui", "Label")

    for label in Label.objects.filter(name='Official'):
        label.name = "Preferred"


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0033_auto_20220810_0113'),
    ]

    operations = [
        migrations.RunPython(update_preferred_label, reverse_code=rollback_preferred_label),
    ]
