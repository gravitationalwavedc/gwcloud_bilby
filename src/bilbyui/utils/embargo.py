import logging

from django.conf import settings
from django.db.models import FloatField, OuterRef, Q, Subquery
from django.db.models.functions import Cast

from bilbyui import models

from .misc import is_ligo_user

logger = logging.getLogger(__name__)


def user_subject_to_embargo(user):
    if settings.EMBARGO_START_TIME is None:
        return False

    return not is_ligo_user(user)


def embargo_filter(qs, user):
    if not user_subject_to_embargo(user):
        return qs

    return qs_embargo_filter(qs)


def qs_embargo_filter(qs):
    return qs.annotate(
        trigger_time=Cast(
            Subquery(
                models.IniKeyValue.objects.filter(job=OuterRef("pk"), key="trigger_time", processed=True).values(
                    "value",
                ),
            ),
            FloatField(),
        ),
        simulated=Subquery(
            models.IniKeyValue.objects.filter(job=OuterRef("pk"), key="n_simulation", processed=False).values("value")[
                :1
            ],
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
    if user is None:
        logger.debug("Job subject to embargo: user is None (treated as non-LIGO)")
    elif not user_subject_to_embargo(user):
        logger.debug("Job not subject to embargo: LIGO user")
        return False

    if simulated:
        logger.debug("Job not subject to embargo: simulated data")
        return False

    if trigger_time is None:
        logger.debug("Job not subject to embargo: no trigger time")
        return False

    if settings.EMBARGO_START_TIME is None:
        logger.debug("Job not subject to embargo: no embargo start time configured")
        return False

    result = trigger_time >= settings.EMBARGO_START_TIME
    logger.debug(
        "Embargo check: trigger_time=%s, EMBARGO_START_TIME=%s, result=%s",
        trigger_time,
        settings.EMBARGO_START_TIME,
        result,
    )
    return result


def _gwflow_trigger_time_from_metadata(metadata):
    """
    Extract the trigger GPS time from portal metadata (issue #83).

    Selects the preferred event (``State == "preferred"``) if present, else
    the first entry with a usable numeric ``GPSTime``, skipping malformed
    entries (missing or non-numeric ``GPSTime``). Returns ``None`` when no
    usable event exists. Defensive: never raises on malformed metadata.
    """
    try:
        events = metadata["GraceDB"]["Events"]
    except (TypeError, KeyError):
        return None

    if not isinstance(events, list):
        return None

    usable = []
    for event in events:
        if not isinstance(event, dict):
            continue
        gps = event.get("GPSTime")
        if gps is None:
            continue
        try:
            gps = float(gps)
        except (TypeError, ValueError):
            continue
        usable.append((event, gps))

    if not usable:
        return None

    for event, gps in usable:
        if event.get("State") == "preferred":
            return gps

    return usable[0][1]


def gwflow_ligo_only_from_metadata(metadata):
    """
    Determine the ``ligo_only`` flag for a GWFlow job from its portal metadata.

    Extracts the trigger GPS time from ``metadata["GraceDB"]["Events"]`` and
    computes ``ligo_only`` per the embargo rule (matching
    ``should_embargo_job`` semantics):

    - ``EMBARGO_START_TIME is None`` -> ``False`` (all public).
    - Valid trigger GPS time -> ``trigger_time >= EMBARGO_START_TIME``
      (equality is LIGO-only).
    - Missing / malformed trigger -> ``False`` (fail-open, public).

    Args:
        metadata: The raw portal payload dict (may be malformed).

    Returns:
        bool: True if the job should be LIGO-only, False otherwise.
    """
    trigger_time = _gwflow_trigger_time_from_metadata(metadata)

    if settings.EMBARGO_START_TIME is None:
        return False

    if trigger_time is None:
        return False

    # EMBARGO_START_TIME arrives as a string from the environment; treat it as
    # a numeric GPS threshold. A malformed value fails open (public).
    try:
        embargo_start = float(settings.EMBARGO_START_TIME)
    except (TypeError, ValueError):
        return False

    return trigger_time >= embargo_start
