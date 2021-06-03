from django.db import migrations


def insert_labels(apps, schema_editor):
    Label = apps.get_model("bilbyui", "Label")
    Label.objects.create(
        name='Bad Run',
        description='This run contains some issues and should not be used for science.',
    )

    Label.objects.create(
        name='Production Run',
        description='This run has been completed successfully and can be used for science.',
    )

    Label.objects.create(
        name='Review Requested',
        description='This run should be reviewed by peers.',
    )

    Label.objects.create(
        name='Reviewed',
        description='This run has been reviewed.',
    )


def delete_labels(apps, schema_editor):
    Label = apps.get_model("bilbyui", "Label")
    labels = Label.objects.all()

    for label in labels:
        label.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0011_auto_20200720_0109'),
    ]

    operations = [
        migrations.RunPython(insert_labels, reverse_code=delete_labels),
    ]
