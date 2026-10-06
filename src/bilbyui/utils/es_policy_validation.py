"""Compare database and Elasticsearch visibility, and audit legacy flag drift.

Visibility classes are assigned to ORM-public records in this order:
Bilby simulations, records without an applicable finite time, records with any
time equal to the threshold, records whose times are all below it, then records
with at least one time above it.

Shadow mismatches use a safety invariant before the diagnostic classes. A
non-simulation record with an applicable time greater than or equal to the
threshold that the policy exposes is ``unexplained``. Remaining mismatches are
classified, in order, as simulation, unknown trigger, threshold boundary, or
legacy flag drift. Thus ``unexplained`` means a policy-public, embargo-timed
record that violates the no-new-disclosure invariant.
"""

import logging
from typing import NamedTuple

from django.conf import settings
from elasticsearch import helpers

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.services.gwflow import _GWCLOUD_PRUNED_FILTER, _gwflow_public_visibility_clause
from bilbyui.services.jobs import _bilby_public_visibility_clause
from bilbyui.utils import gwflow_es
from bilbyui.utils.embargo import annotate_simulation, is_record_public, visible_to_user
from bilbyui.utils.reindex import _finite_numeric

logger = logging.getLogger(__name__)

_KINDS = {"bilby", "gwflow"}


class VisibilityReport(NamedTuple):
    kind: str
    threshold: float
    orm_public: int
    es_public: int
    missing_in_es: list
    extra_in_es: list
    classes: dict

    @property
    def ok(self) -> bool:
        return not self.missing_in_es and not self.extra_in_es


class ShadowReport(NamedTuple):
    kind: str
    threshold: float
    flag_drift: int
    simulation: int
    unknown_trigger: int
    threshold_boundary: int
    unexplained: int
    new_exposures: int
    total_mismatches: int

    @property
    def ok(self) -> bool:
        return self.unexplained == 0


def _validate_kind(kind: str) -> None:
    if kind not in _KINDS:
        raise ValueError("kind must be 'bilby' or 'gwflow'")


def _applicable_times(record, kind: str) -> list[float]:
    if kind == "bilby":
        values = [
            record.trigger_time,
            record.event_id.gps_time if record.event_id_id else None,
            record.gwflow_job.trigger_time if record.gwflow_job_id else None,
            (record.gwflow_job.event_id.gps_time if record.gwflow_job_id and record.gwflow_job.event_id_id else None),
        ]
    else:
        values = [
            record.trigger_time,
            record.event_id.gps_time if record.event_id_id else None,
        ]
    return [value for raw in values if (value := _finite_numeric(raw)) is not None]


def _is_simulation(record, kind: str) -> bool:
    return kind == "bilby" and record.simulated is not None and record.simulated > 0


def _classify_visibility(record, kind: str, threshold: float) -> str:
    if _is_simulation(record, kind):
        return "simulation"
    times = _applicable_times(record, kind)
    if not times:
        return "null_time"
    if any(value == threshold for value in times):
        return "equal"
    if all(value < threshold for value in times):
        return "below"
    return "above"


def _queryset(kind: str):
    if kind == "bilby":
        return annotate_simulation(
            BilbyJob.objects.select_related(
                "event_id",
                "gwflow_job__event_id",
            )
        )
    return GWFlowJob.objects.select_related("event_id")


def collect_visibility_parity(
    kind: str,
    threshold: float,
    *,
    batch: int = 200,
    es=None,
) -> VisibilityReport:
    """Compare ORM-public IDs with IDs returned by the production ES clause."""
    _validate_kind(kind)
    es = es or gwflow_es.get_es_client()

    if kind == "bilby":
        public = visible_to_user(
            _queryset(kind).filter(private=False),
            None,
            "BilbyJob",
            threshold=threshold,
        )
        index = settings.ELASTIC_SEARCH_INDEX
        query = {
            "bool": {
                "filter": [
                    {"term": {"_private_info_.private": False}},
                    _bilby_public_visibility_clause(threshold),
                ]
            }
        }
    else:
        public = visible_to_user(
            _queryset(kind).filter(is_pruned=False),
            None,
            "GWFlowJob",
            threshold=threshold,
        )
        index = settings.ELASTIC_SEARCH_GWFLOW_INDEX
        query = {
            "bool": {
                "filter": [
                    _GWCLOUD_PRUNED_FILTER,
                    _gwflow_public_visibility_clause(threshold),
                ]
            }
        }

    orm_ids = set()
    classes = {
        "below": 0,
        "null_time": 0,
        "simulation": 0,
        "equal": 0,
        "above": 0,
    }
    cursor = 0
    while True:
        page = list(public.order_by("id").filter(id__gt=cursor)[:batch])
        if not page:
            break
        cursor = page[-1].id
        for record in page:
            orm_ids.add(record.id)
            classes[_classify_visibility(record, kind, threshold)] += 1

    es_ids = set()
    for hit in helpers.scan(
        es,
        index=index,
        query=query,
        _source=False,
        size=batch,
        preserve_order=False,
    ):
        raw_id = hit.get("_id") if isinstance(hit, dict) else None
        if isinstance(raw_id, str) and raw_id.isdecimal():
            es_ids.add(int(raw_id))
        elif isinstance(raw_id, int) and not isinstance(raw_id, bool) and str(raw_id).isdecimal():
            es_ids.add(raw_id)

    report = VisibilityReport(
        kind=kind,
        threshold=threshold,
        orm_public=len(orm_ids),
        es_public=len(es_ids),
        missing_in_es=sorted(orm_ids - es_ids),
        extra_in_es=sorted(es_ids - orm_ids),
        classes=classes,
    )
    logger.info(
        "ES visibility parity kind=%s orm_public=%d es_public=%d missing=%d extra=%d",
        kind,
        report.orm_public,
        report.es_public,
        len(report.missing_in_es),
        len(report.extra_in_es),
    )
    return report


def collect_shadow_comparison(
    kind: str,
    threshold: float,
    *,
    batch: int = 200,
) -> ShadowReport:
    """Compare legacy visibility flags with record-level policy decisions."""
    _validate_kind(kind)
    counts = {
        "flag_drift": 0,
        "simulation": 0,
        "unknown_trigger": 0,
        "threshold_boundary": 0,
        "unexplained": 0,
        "new_exposures": 0,
        "total_mismatches": 0,
    }

    queryset = _queryset(kind).order_by("id")
    cursor = 0
    while True:
        records = list(queryset.filter(id__gt=cursor)[:batch])
        if not records:
            break
        cursor = records[-1].id

        for record in records:
            flag_public = not record.is_ligo_job if kind == "bilby" else not record.ligo_only
            is_sim = _is_simulation(record, kind)
            if kind == "bilby":
                policy_public = is_record_public(record, None, is_simulation=is_sim, threshold=threshold)
            else:
                policy_public = is_record_public(record, None, threshold=threshold)
            if flag_public == policy_public:
                continue

            counts["total_mismatches"] += 1
            if policy_public and not flag_public:
                counts["new_exposures"] += 1

            times = _applicable_times(record, kind)
            if not is_sim and any(value >= threshold for value in times) and policy_public:
                counts["unexplained"] += 1
            elif is_sim:
                counts["simulation"] += 1
            elif not times:
                counts["unknown_trigger"] += 1
            elif any(value == threshold for value in times):
                counts["threshold_boundary"] += 1
            else:
                counts["flag_drift"] += 1

    report = ShadowReport(kind=kind, threshold=threshold, **counts)
    logger.info(
        "ES shadow comparison kind=%s mismatches=%d unexplained=%d new_exposures=%d",
        kind,
        report.total_mismatches,
        report.unexplained,
        report.new_exposures,
    )
    return report
