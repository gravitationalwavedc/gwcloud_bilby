from django.db import migrations


def insert_preferred_label(apps, schema_editor):
    Label = apps.get_model("bilby", "Label")

    Label.objects.create(
        name='Preferred',
        description='This run has been marked by GWCloud admins as preferred for analysis of this event.',
        protected=True  # This label is protected - a normal user should not be able to set this label on a job
    )


def delete_preferred_label(apps, schema_editor):
    Label = apps.get_model("bilby", "Label")

    Label.objects.filter(name='Preferred').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('bilby', '0014_label_protected'),
    ]

    operations = [
        migrations.RunPython(insert_preferred_label, reverse_code=delete_preferred_label),
    ]
