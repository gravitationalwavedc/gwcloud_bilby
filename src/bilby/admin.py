from django.contrib import admin
from .models import BilbyJob, Data, DataParameter, Signal, SignalParameter, Sampler, SamplerParameter, Prior, Label

# Register your models here.


class InlineDataAdmin(admin.TabularInline):
    model = Data


class InlineDataParameterAdmin(admin.TabularInline):
    model = DataParameter

    def has_add_permission(self, request):
        num_objects = self.model.objects.count()
        if num_objects >= 6:
            return False
        else:
            return True


class InlineSamplerAdmin(admin.TabularInline):
    model = Sampler


class InlineSamplerParameterAdmin(admin.TabularInline):
    model = SamplerParameter


class InlineSignalAdmin(admin.TabularInline):
    model = Signal


class InlineSignalParameterAdmin(admin.TabularInline):
    model = SignalParameter


class InlinePriorAdmin(admin.TabularInline):
    model = Prior


@admin.register(Sampler)
class SamplerAdmin(admin.ModelAdmin):
    fields = ['job', 'sampler_choice']


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    fields = ['job', 'signal_choice', 'signal_model']


@admin.register(Data)
class DataAdmin(admin.ModelAdmin):
    fields = ['job', 'data_choice']
    inlines = (InlineDataParameterAdmin,)


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    fields = ['name', 'description']


@admin.register(BilbyJob)
class BilbyJobAdmin(admin.ModelAdmin):
    fields = ['name', 'description', 'private', 'job_id', 'labels']
    filter_horizontal = ('labels',)
    readonly_fields = ('creation_time', 'last_updated')
    inlines = (
        InlineDataAdmin,
        InlineDataParameterAdmin,
        InlineSignalAdmin,
        InlineSignalParameterAdmin,
        InlinePriorAdmin,
        InlineSamplerAdmin,
        InlineSamplerParameterAdmin
    )
