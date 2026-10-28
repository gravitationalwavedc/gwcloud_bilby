"""Deterministic pathological fixtures for GWFlow detail-page E2E tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bilbyui.models import GWFlowFile, GWFlowJob

PATH_LENGTH = 1000
SUPEREVENT_EVENT_COUNT = 100
METADATA_COLUMN_COUNT = 12
VERSION_COUNT = 80
SNAME = "S260923aa"
LONG_VALUE = "pathological-value-" + ("x" * 180)


def create_pathological_job(testcase_cls):
    """Create a stable GWFlow owner and job using the shared user factory."""
    user = testcase_cls.create_user(
        id=861,
        name="pathological fixture user",
        primary_email="pathological-fixtures@example.com",
    )
    return GWFlowJob.objects.create(
        sname=SNAME,
        user=user,
        libraries=["cbc-workflow-pathological"],
        schema_version="v3",
        current_version_number=1,
    )


def create_1000_character_file(job):
    """Create a GWFlow file whose unbroken source path is exactly 1,000 chars."""
    path = "p" * PATH_LENGTH
    return GWFlowFile.objects.create(
        job=job,
        analysis_uid="pathological-analysis",
        path=path,
        file_name=path,
        file_size=1024,
        uploaded=True,
    )


def _canonical_event(index, *, long_values=False):
    suffix = f"-{LONG_VALUE}" if long_values else ""
    return {
        "event_name": f"G{index:06d}{suffix}",
        "has_ns": 0.10,
        "has_remnant": 0.09,
        "has_mass_gap": 0.80,
        "pipeline_has_ns": 0.99,
        "pipeline_has_remnant": 0.49,
        "pipeline_has_mass_gap": 0.51,
        "pipeline": f"pipeline-{index:03d}-{LONG_VALUE}",
        "state": f"state-{index:03d}-{LONG_VALUE}",
        "gps_time": 1_400_000_000.0 + index,
        "far": {"value": 1e-9 + index * 1e-12, "unit": "Hz"},
        "network_snr": 20.0 + index,
    }


def build_superevent_with_100_events():
    """Build 100 canonical GraceDB events with deep residual metadata."""
    return {
        "sname": SNAME,
        "schema_version": "v3",
        "gracedb_events": [_canonical_event(index) for index in range(SUPEREVENT_EVENT_COUNT)],
    }


def build_12_column_metadata():
    """Build one long-valued canonical event with five residual fields."""
    event = _canonical_event(0, long_values=True)
    return {"sname": SNAME, "schema_version": "v3", "gracedb_events": [event]}


def build_long_version_list():
    """Build viewport-overflowing rows in the shape returned by get_versions."""
    origin = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    versions = []
    for index in range(VERSION_COUNT):
        versions.append(
            {
                "version_number": 1021,
                "record_timestamp": (origin + timedelta(hours=index)).isoformat(),
                "schema_version": "3",
                "is_current": index == VERSION_COUNT - 1,
                "payload": {"sname": SNAME, "info": {"notes": f"version-{index:03d}"}},
            }
        )
    return versions


def build_pathological_fixtures(testcase_cls):
    """Create the DB fixtures and return all portal payload fixtures together."""
    job = create_pathological_job(testcase_cls)
    file_fixture = create_1000_character_file(job)
    return {
        "user": job.user,
        "job": job,
        "file": file_fixture,
        "superevent": build_superevent_with_100_events(),
        "metadata": build_12_column_metadata(),
        "versions": build_long_version_list(),
    }
