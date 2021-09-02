# Generated by Django 3.2.4 on 2021-07-13 00:57

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('bilbyui', '0024_bilbyjob_is_uploaded_job'),
    ]

    operations = [
        migrations.CreateModel(
            name='BilbyJobUploadToken',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
                ('user_id', models.IntegerField()),
                ('is_ligo', models.BooleanField()),
                ('created', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
        ),
    ]