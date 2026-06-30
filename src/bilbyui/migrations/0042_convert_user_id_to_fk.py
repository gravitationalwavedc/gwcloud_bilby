from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

from adacs_sso_plugin.utils import auth_request, create_or_update_user_from_data


def migrate_user_data(apps, schema_editor):
    BilbyJob = apps.get_model("bilbyui", "BilbyJob")
    BilbyJobUploadToken = apps.get_model("bilbyui", "BilbyJobUploadToken")
    User = apps.get_model("users", "User")

    # Collect all unique user_id values from both tables
    user_ids = set()
    user_ids.update(BilbyJob.objects.values_list("user_id", flat=True).distinct())
    user_ids.update(BilbyJobUploadToken.objects.values_list("user_id", flat=True).distinct())

    for user_id in user_ids:
        try:
            _, user_data_list = auth_request("get_users", {"ids": [user_id]})
            if user_data_list:
                create_or_update_user_from_data(user_data_list[0])
            else:
                # Create placeholder user if SSO returns no data
                User.objects.update_or_create(id=user_id, defaults={"name": f"User {user_id}", "primary_email": ""})
        except Exception as e:
            # Create placeholder user on error to maintain FK integrity
            print(f"Failed to migrate user {user_id}: {e}")
            User.objects.update_or_create(id=user_id, defaults={"name": f"User {user_id}", "primary_email": ""})


class Migration(migrations.Migration):

    dependencies = [
        ("bilbyui", "0041_auto_20230814_2318"),
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrate_user_data, migrations.RunPython.noop),
        # Rename user_id to user for BilbyJob
        migrations.RenameField(
            model_name="bilbyjob",
            old_name="user_id",
            new_name="user",
        ),
        migrations.AlterField(
            model_name="bilbyjob",
            name="user",
            field=models.ForeignKey(
                settings.AUTH_USER_MODEL,
                on_delete=models.PROTECT,
                related_name="bilby_jobs",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="bilbyjob",
            unique_together={("user", "name")},
        ),
        # Rename user_id to user for BilbyJobUploadToken
        migrations.RenameField(
            model_name="bilbyjobuploadtoken",
            old_name="user_id",
            new_name="user",
        ),
        migrations.AlterField(
            model_name="bilbyjobuploadtoken",
            name="user",
            field=models.ForeignKey(
                settings.AUTH_USER_MODEL,
                on_delete=models.CASCADE,
                related_name="upload_tokens",
            ),
        ),
    ]
