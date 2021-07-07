# Generated by Django 3.2.4 on 2021-06-11 01:38

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0022_auto_20210606_0521'),
    ]

    operations = [
        migrations.CreateModel(
            name='FileDownloadToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
                ('path', models.TextField()),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bilbyui.bilbyjob')),
            ],
        ),
    ]