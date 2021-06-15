from django.contrib import admin

from .models import BilbyJob, Label, IniKeyValue


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    fields = ['name', 'description']


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
    fields = ['name', 'description', 'private', 'job_controller_id', 'labels', 'ini_string', 'is_ligo_job']
    filter_horizontal = ('labels',)
    readonly_fields = ('creation_time', 'last_updated')
    inlines = [IniKeyValueAdmin, ]
