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
    """
    Determine if a job should be embargoed based on user, trigger time, and simulation status.
    
    Args:
        user: The user object. If None, treats as non-LIGO user for embargo checking.
        trigger_time: The GPS trigger time of the job (float or None).
        simulated: Whether the job uses simulated data (True/False or None).
        
    Returns:
        bool: True if the job should be embargoed, False otherwise.
        
    Note:
        - If user is None, treats as non-LIGO user (subject to embargo)
        - Simulated jobs are never embargoed
        - Jobs with no trigger time are never embargoed
        - Jobs with trigger_time < EMBARGO_START_TIME are never embargoed
        - Only real data jobs with trigger_time >= EMBARGO_START_TIME are embargoed
    """
    # If user is None, treat as non-LIGO user for embargo checking
    if user is not None and not user_subject_to_embargo(user):
        return False

    if simulated:
        return False

    if trigger_time is None:
        return False

    if trigger_time < settings.EMBARGO_START_TIME:
        return False

    return True
