from typing import ClassVar

from django.contrib import admin

from .models import BilbyJob, EventID, IniKeyValue, Label


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    fields: ClassVar[list[str]] = ["name", "description"]


@admin.register(EventID)
class EventIDAdmin(admin.ModelAdmin):
    fields: ClassVar[list[str]] = ["event_id", "trigger_id", "nickname", "gps_time"]


class IniKeyValueAdmin(admin.TabularInline):
    model = IniKeyValue

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BilbyJob)
class BilbyJobAdmin(admin.ModelAdmin):
    fields: ClassVar[list[str]] = [
        "name",
        "description",
        "private",
        "job_controller_id",
        "labels",
        "ini_string",
        "is_ligo_job",
    ]
    filter_horizontal = ("labels",)
    readonly_fields = ("creation_time", "last_updated")
    inlines: ClassVar[list] = [
        IniKeyValueAdmin,
    ]
