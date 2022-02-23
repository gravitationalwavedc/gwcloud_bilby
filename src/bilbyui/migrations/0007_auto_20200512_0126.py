# Generated by Django 2.2.12 on 2020-05-12 01:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0006_auto_20200511_0428'),
    ]

    operations = [
        migrations.AddField(
            model_name='bilbyjob',
            name='public',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='dataparameter',
            name='name',
            field=models.CharField(
                choices=[
                    ['hanford', 'Hanford'],
                    ['livingston', 'Livingston'],
                    ['virgo', 'Virgo'],
                    ['signal_duration', 'Signal Duration (s)'],
                    ['sampling_frequency', 'Sampling Frequency (Hz)'],
                    ['trigger_time', 'Trigger Time'],
                    ['hanford_minimum_frequency', 'Hanford Minimum Frequency'],
                    ['hanford_maximum_frequency', 'Hanford Maximum Frequency'],
                    ['hanford_channel', 'Hanford Channel'],
                    ['livingston_minimum_frequency', 'Livingston Minimum Frequency'],
                    ['livingston_maximum_frequency', 'Livingston Maximum Frequency'],
                    ['livingston_channel', 'Livingston Channel'],
                    ['virgo_minimum_frequency', 'Virgo Minimum Frequency'],
                    ['virgo_maximum_frequency', 'Virgo Maximum Frequency'],
                    ['virgo_channel', 'Virgo Channel']
                ],
                max_length=20
            ),
        ),
    ]
