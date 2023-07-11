from django.db.models import Subquery, OuterRef, Q, FloatField
from django.conf import settings
from django.db.models.functions import Cast

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

    return qs_embargo_filter(qs)


def qs_embargo_filter(qs):
    return qs.annotate(
        trigger_time=Cast(
            Subquery(
                models.IniKeyValue.objects.filter(job=OuterRef("pk"), key="trigger_time", processed=True).values(
                    "value"
                )
            ),
            FloatField(),
        ),
        simulated=Subquery(
            models.IniKeyValue.objects.filter(job=OuterRef("pk"), key="n_simulation", processed=False).values("value")[
                :1
            ]
        ),
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
