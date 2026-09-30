from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured

from bilbyui.utils.embargo import get_embargo_start, reset_embargo_start_cache


@register()
def check_embargo_start(app_configs, **kwargs):
    reset_embargo_start_cache()
    try:
        get_embargo_start()
    except ImproperlyConfigured as exc:
        return [Error(str(exc), id="bilbyui.E001")]
    return []
