# Generated by Django 3.2.9 on 2021-12-10 04:12

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0025_bilbyjobuploadtoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventID',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_id', models.CharField(max_length=15, unique=True, validators=[
                    django.core.validators.RegexValidator(
                        message='Must be of the form GW123456_123456',
                        regex='^GW\\d{6}_\\d{6}$'
                    )
                ])),
                ('trigger_id', models.CharField(blank=True, max_length=15, null=True, validators=[
                    django.core.validators.RegexValidator(
                        message='Must be of the form S123456a',
                        regex='^S\\d{6}[a-z]{1,2}$'
                    )
                ])),
                ('nickname', models.CharField(blank=True, max_length=20, null=True)),
            ],
        ),
        migrations.AddField(
            model_name='bilbyjob',
            name='event_id',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='bilbyui.eventid'),
        ),
    ]
