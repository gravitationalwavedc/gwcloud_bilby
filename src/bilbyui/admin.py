from django.contrib import admin

from .models import BilbyJob, Label


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    fields = ['name', 'description']


@admin.register(BilbyJob)
class BilbyJobAdmin(admin.ModelAdmin):
    fields = ['name', 'description', 'private', 'job_controller_id', 'labels', 'ini_string']
    filter_horizontal = ('labels',)
    readonly_fields = ('creation_time', 'last_updated')
