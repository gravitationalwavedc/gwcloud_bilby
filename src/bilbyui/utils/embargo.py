from django.db.models.functions import Cast, Replace
from django.db.models import Subquery, OuterRef, Value, FloatField, Q
from django.conf import settings
from .misc import is_ligo_user
from bilbyui import models


def user_subject_to_embargo(user):
    if settings.EMBARGO_START_TIME is None:
        return False

    if is_ligo_user(user):
        return False

    return True


def embargo_filter(qs, user):
    if not user_subject_to_embargo(user):
        return qs

    return qs.annotate(
        trigger_time=Cast(
            Replace(
                Subquery(
                    models.IniKeyValue.objects.filter(job=OuterRef('pk'), key='trigger_time').values('value')[:1]
                ),
                Value('"'),
            ),
            FloatField()
        ),
        simulated=Subquery(
            models.IniKeyValue.objects.filter(job=OuterRef('pk'), key='n_simulation').values('value')[:1]
        )
    ).filter(Q(trigger_time__lt=settings.EMBARGO_START_TIME) | Q(simulated__gt=0))


def should_embargo_job(user, trigger_time, simulated):
    if not user_subject_to_embargo(user):
        return False

    if simulated:
        return False

    if trigger_time is None:
        return False

    if trigger_time < settings.EMBARGO_START_TIME:
        return False

    return True
