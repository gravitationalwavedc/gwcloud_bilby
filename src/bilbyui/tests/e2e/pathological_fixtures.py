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
        current_history_id="0" * 40,
        ligo_only=False,
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


def build_superevent_with_100_events():
    """Build the real metadata payload shape consumed by the detail renderer."""
    events = []
    for index in range(SUPEREVENT_EVENT_COUNT):
        events.append(
            {
                "uid": f"G{index:06d}",
                "pipeline": f"pipeline-{index:03d}-{LONG_VALUE}",
                "state": f"state-{index:03d}-{LONG_VALUE}",
                "gps_time": 1_400_000_000.0 + index,
                "far": {"value": 1e-9 + index * 1e-12, "unit": "Hz"},
                "network_snr": 20.0 + index,
                "pastro": 0.99,
                "p_bbh": 0.80,
                "p_bns": 0.10,
                "p_nsbh": 0.09,
                "mass_1": 30.0 + index,
                "mass_2": 20.0 + index,
            }
        )
    return {"sname": SNAME, "schema_version": "v3", "gracedb": {"events": events}}


def build_12_column_metadata():
    """Build one long-valued GraceDB record covering all 12 comparative columns."""
    event = {
        "uid": f"G-LONG-{LONG_VALUE}",
        "pipeline": f"gstlal-{LONG_VALUE}",
        "state": f"preferred-{LONG_VALUE}",
        "gps_time": f"1400000000.000-{LONG_VALUE}",
        "far": {"value": 1.2e-12, "unit": f"Hz-{LONG_VALUE}"},
        "network_snr": f"24.8-{LONG_VALUE}",
        "pastro": f"0.99-{LONG_VALUE}",
        "p_bbh": f"0.80-{LONG_VALUE}",
        "p_bns": f"0.10-{LONG_VALUE}",
        "p_nsbh": f"0.09-{LONG_VALUE}",
        "mass_1": f"31.2-{LONG_VALUE}",
        "mass_2": f"22.4-{LONG_VALUE}",
    }
    return {"sname": SNAME, "schema_version": "v3", "gracedb": {"events": [event]}}


def build_long_version_list():
    """Build viewport-overflowing rows in the shape returned by get_versions."""
    origin = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    versions = []
    for index in range(VERSION_COUNT):
        versions.append(
            {
                "commit_sha": f"{index:040x}",
                "commit_timestamp": (origin + timedelta(hours=index)).isoformat(),
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
