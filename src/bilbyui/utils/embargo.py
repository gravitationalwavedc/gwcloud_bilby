import logging
import math
import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import (
    Case,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Cast

from bilbyui import models

from .misc import is_ligo_user

logger = logging.getLogger(__name__)

N_SIM_TEXT = r"^[ \t]*\+?[0-9]{1,9}[ \t]*\Z"

_CACHE_UNSET = object()
_cached_embargo_start_raw = _CACHE_UNSET
_cached_embargo_start = None


def reset_embargo_start_cache() -> None:
    """Clear the cached embargo threshold."""
    global _cached_embargo_start, _cached_embargo_start_raw

    _cached_embargo_start_raw = _CACHE_UNSET
    _cached_embargo_start = None


def get_embargo_start() -> float | None:
    """Return the configured finite embargo threshold, or None when disabled."""
    global _cached_embargo_start, _cached_embargo_start_raw

    raw = settings.EMBARGO_START_TIME
    if _cached_embargo_start_raw is not _CACHE_UNSET and raw == _cached_embargo_start_raw:
        return _cached_embargo_start

    if raw is None or raw == "":
        parsed = None
    else:
        try:
            if isinstance(raw, bool):
                raise TypeError
            parsed = float(raw)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ImproperlyConfigured(
                "EMBARGO_START_TIME must be empty or a finite numeric GPS threshold."
            ) from exc

        if not math.isfinite(parsed):
            raise ImproperlyConfigured(
                "EMBARGO_START_TIME must be empty or a finite numeric GPS threshold."
            )

    _cached_embargo_start_raw = raw
    _cached_embargo_start = parsed
    return parsed


def user_subject_to_embargo(user):
    if get_embargo_start() is None:
        return False

    return not is_ligo_user(user)



def is_simulated_value(text):
    """Return whether raw n_simulation text is a positive integer count."""
    if text is None or isinstance(text, bool) or not isinstance(text, str):
        return False
    if not re.fullmatch(N_SIM_TEXT, text):
        return False
    return int(text) > 0


def is_public(trigger_times, is_simulation, user):
    """Return public visibility using strictest-wins trigger-time semantics."""
    embargo_start = get_embargo_start()
    if embargo_start is None:
        return True
    if not user_subject_to_embargo(user):
        return True
    if is_simulation:
        return True

    for trigger_time in trigger_times:
        if trigger_time is None:
            continue
        if isinstance(trigger_time, bool):
            raise TypeError("Trigger times must be numeric or None, not bool")
        try:
            finite = math.isfinite(trigger_time)
        except TypeError as exc:
            raise TypeError("Trigger times must be numeric or None") from exc
        if not finite:
            raise ValueError("Trigger times must be finite")
        if trigger_time >= embargo_start:
            return False
    return True


def annotate_simulation(qs):
    """Annotate jobs with raw and parsed n_simulation values."""
    qs = qs.annotate(
        n_sim_raw=Subquery(
            models.IniKeyValue.objects.filter(
                job=OuterRef("pk"),
                key="n_simulation",
                processed=False,
            ).values("value")[:1]
        )
    )
    return qs.annotate(
        simulated=Case(
            When(
                n_sim_raw__regex=N_SIM_TEXT,
                then=Cast("n_sim_raw", IntegerField()),
            ),
            default=Value(None),
            output_field=IntegerField(),
        )
    )


def is_record_public(record, user, *, is_simulation=None) -> bool:
    """Evaluate visibility for a record whose required relations are preloaded.

    GWFlowJob callers must use ``select_related("event_id")``. BilbyJob
    callers must use
    ``select_related("event_id", "gwflow_job__event_id")``.
    """
    if isinstance(record, models.EventID):
        return is_public([record.gps_time], False, user)

    if isinstance(record, models.GWFlowJob):
        return is_public(
            [
                record.trigger_time,
                record.event_id.gps_time if record.event_id_id else None,
            ],
            False,
            user,
        )

    if isinstance(record, models.BilbyJob):
        if is_simulation is None:
            raise ValueError(
                "BilbyJob visibility requires is_simulation; use "
                "is_simulated_value(raw_n_simulation) or an "
                "annotate_simulation() result."
            )

        return is_public(
            [
                record.trigger_time,
                record.event_id.gps_time if record.event_id_id else None,
                record.gwflow_job.trigger_time if record.gwflow_job_id else None,
                (
                    record.gwflow_job.event_id.gps_time
                    if record.gwflow_job_id
                    and record.gwflow_job.event_id_id
                    else None
                ),
            ],
            is_simulation,
            user,
        )

    raise TypeError(f"Unsupported visibility record type: {type(record).__name__}")



def visible_to_user(qs, user, model_kind):
    """Return the public-visible subset for a supported model kind."""
    embargo_start = get_embargo_start()
    if embargo_start is None:
        return qs
    if not user_subject_to_embargo(user):
        return qs

    if model_kind == "EventID":
        return qs.filter(
            Q(gps_time__lt=embargo_start) | Q(gps_time__isnull=True)
        )

    if model_kind == "GWFlowJob":
        return qs.filter(
            (Q(trigger_time__lt=embargo_start) | Q(trigger_time__isnull=True))
            & (
                Q(event_id__gps_time__lt=embargo_start)
                | Q(event_id__gps_time__isnull=True)
            )
        )

    if model_kind == "BilbyJob":
        qs = annotate_simulation(qs)
        return qs.filter(
            Q(simulated__gt=0)
            | (
                (Q(trigger_time__lt=embargo_start) | Q(trigger_time__isnull=True))
                & (
                    Q(event_id__gps_time__lt=embargo_start)
                    | Q(event_id__gps_time__isnull=True)
                )
                & (
                    Q(gwflow_job__trigger_time__lt=embargo_start)
                    | Q(gwflow_job__trigger_time__isnull=True)
                )
                & (
                    Q(gwflow_job__event_id__gps_time__lt=embargo_start)
                    | Q(gwflow_job__event_id__gps_time__isnull=True)
                )
            )
        )

    raise ValueError(f"Unsupported model kind: {model_kind!r}")

def embargo_filter(qs, user):
    if not user_subject_to_embargo(user):
        return qs

    return qs_embargo_filter(qs)


def qs_embargo_filter(qs):
    return qs.annotate(
        _embargo_trigger_time=Cast(
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
    ).filter(Q(_embargo_trigger_time__lt=get_embargo_start()) | Q(simulated__gt=0))


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

    embargo_start = get_embargo_start()
    if embargo_start is None:
        logger.debug("Job not subject to embargo: no embargo start time configured")
        return False

    result = trigger_time >= embargo_start
    logger.debug(
        "Embargo check: trigger_time=%s, embargo_start=%s, result=%s",
        trigger_time,
        embargo_start,
        result,
    )
    return result


def _gwflow_trigger_time_from_metadata(metadata):
    """
    Extract the trigger GPS time from portal metadata (issue #83).

    Selects the preferred event (``State == "preferred"``) if present, else
    the first entry with a usable numeric GPS time, skipping malformed
    entries (missing or non-numeric GPS time). Returns ``None`` when no
    usable event exists. Defensive: never raises on malformed metadata.
    Accepts both the capitalised portal shape (``GraceDB`` / ``Events`` /
    ``GPSTime``) and the canonical lowercase shape (``gracedb`` / ``events``
    / ``gps_time`` / ``gpstime``), matching ``resolve_event_id_for``.
    """
    try:
        gracedb = metadata["GraceDB"]
    except (TypeError, KeyError):
        gracedb = None
    if not isinstance(gracedb, dict):
        try:
            gracedb = metadata["gracedb"]
        except (TypeError, KeyError):
            return None
    if not isinstance(gracedb, dict):
        return None

    events = gracedb.get("Events")
    if not isinstance(events, list):
        events = gracedb.get("events")
    if not isinstance(events, list):
        return None

    usable = []
    for event in events:
        if not isinstance(event, dict):
            continue
        gps = event.get("GPSTime")
        if gps is None:
            gps = event.get("gps_time")
        if gps is None:
            gps = event.get("gpstime")
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
        if event.get("State") == "preferred" or event.get("state") == "preferred":
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

    embargo_start = get_embargo_start()
    if embargo_start is None or trigger_time is None:
        return False

    return trigger_time >= embargo_start
