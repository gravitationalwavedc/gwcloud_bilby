import datetime
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_portal import (
    GWFlowCurrentVersion,
    resolve_current_version,
    resolve_event_id_for_superevent,
)
from bilbyui.views import _create_event_id_guarded, create_event_id, upsert_gwflow_job


class TestGWFlowCurrentVersionResolver(BilbyTestCase):
    def test_resolves_one_current_summary_as_coherent_unit(self):
        summaries = [
            {
                "version_number": 1,
                "record_timestamp": "2026-09-01T01:00:00+00:00",
                "is_current": False,
            },
            {
                "version_number": 2,
                "commit_timestamp": "1999-01-01T00:00:00+00:00",
                "record_timestamp": "2026-09-02T03:04:05+10:00",
                "is_current": True,
            },
        ]
        detail = {
            "raw_payload": {
                "GraceDB": {
                    "Events": [
                        {"GPSTime": 1000.0},
                        {"State": "preferred", "GPSTime": 1438044067.054443},
                    ]
                }
            }
        }

        with (
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_versions",
                return_value=(summaries, "live"),
            ) as get_versions,
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_version",
                return_value=(detail, "stale"),
            ) as get_version,
        ):
            result = resolve_current_version("S250801h")

        self.assertTrue(result.available)
        self.assertEqual(result.trigger_time, 1438044067.054443)
        self.assertEqual(result.current_version_number, 2)
        self.assertEqual(
            result.current_history_timestamp,
            datetime.datetime(
                2026,
                9,
                1,
                17,
                4,
                5,
                tzinfo=datetime.UTC,
            ),
        )
        self.assertEqual(result.versions_state, "live")
        self.assertEqual(result.detail_state, "stale")
        get_versions.assert_called_once_with("S250801h")
        get_version.assert_called_once_with("S250801h", 2)

    def test_portal_boolean_semantics_select_only_canonical_true_values(self):
        rejected = ("false", "0", 0)
        accepted = ("true", 1)

        for is_current in rejected:
            with self.subTest(is_current=is_current):
                summaries = [
                    {
                        "is_current": is_current,
                        "version_number": 7,
                        "record_timestamp": "2026-09-01T00:00:00+00:00",
                    }
                ]
                with (
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_versions",
                        return_value=(summaries, "live"),
                    ),
                    mock.patch("bilbyui.utils.gwflow_portal.get_version") as get_version,
                ):
                    result = resolve_current_version("S250801h")

                self.assertFalse(result.available)
                get_version.assert_not_called()

        detail = {
            "raw_payload": {
                "GraceDB": {
                    "Events": [
                        {
                            "State": "preferred",
                            "GPSTime": 1438044067.054443,
                        }
                    ]
                }
            }
        }
        for is_current in accepted:
            with self.subTest(is_current=is_current):
                summaries = [
                    {
                        "is_current": is_current,
                        "version_number": 8,
                        "record_timestamp": "2026-09-01T00:00:00+00:00",
                    }
                ]
                with (
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_versions",
                        return_value=(summaries, "live"),
                    ),
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_version",
                        return_value=(detail, "live"),
                    ) as get_version,
                ):
                    result = resolve_current_version("S250801h")

                self.assertTrue(result.available)
                get_version.assert_called_once_with(
                    "S250801h",
                    8,
                )

    def test_zero_and_multiple_current_summaries_are_unavailable(self):
        cases = (
            [],
            [
                {"is_current": True, "version_number": 5},
                {"is_current": True, "version_number": 6},
            ],
        )
        for summaries in cases:
            with self.subTest(summaries=summaries):
                with (
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_versions",
                        return_value=(summaries, "live"),
                    ),
                    mock.patch("bilbyui.utils.gwflow_portal.get_version") as get_version,
                ):
                    result = resolve_current_version("S250801h")
                self.assertFalse(result.available)
                get_version.assert_not_called()

    def test_detail_fetch_exception_is_unavailable(self):
        summary = [
            {
                "is_current": True,
                "version_number": 3,
                "record_timestamp": "2026-09-01T00:00:00+00:00",
            }
        ]
        with (
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_versions",
                return_value=(summary, "live"),
            ),
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_version",
                side_effect=RuntimeError("portal failure"),
            ),
        ):
            result = resolve_current_version("S250801h")

        self.assertFalse(result.available)
        self.assertEqual(result.reason, "detail fetch failed")
        self.assertIsNone(result.trigger_time)

    def test_detail_failures_and_unusable_payloads_are_unavailable(self):
        summary = [
            {
                "is_current": True,
                "version_number": 4,
                "record_timestamp": "2026-09-01T00:00:00+00:00",
            }
        ]
        cases = (
            (None, "down"),
            ([], "live"),
            ({"raw_payload": []}, "live"),
        )
        for detail_result in cases:
            with self.subTest(detail=detail_result):
                with (
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_versions",
                        return_value=(summary, "live"),
                    ),
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_version",
                        return_value=detail_result,
                    ),
                ):
                    result = resolve_current_version("S250801h")
                self.assertFalse(result.available)
                self.assertIsNone(result.trigger_time)

    def test_version_identity_is_authoritative_without_a_trigger_time(self):
        """A missing GraceDB trigger time must not suppress the version pointer."""
        summary = [
            {
                "is_current": True,
                "version_number": 4,
                "record_timestamp": "2026-09-01T00:00:00+00:00",
            }
        ]
        detail = {"raw_payload": {"GraceDB": {"Events": [{"State": "preferred", "GPSTime": "nan"}]}}}
        with (
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_versions",
                return_value=(summary, "live"),
            ),
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_version",
                return_value=(detail, "live"),
            ),
        ):
            result = resolve_current_version("S250801h")

        self.assertTrue(result.available)
        self.assertIsNone(result.trigger_time)
        self.assertEqual(result.current_version_number, 4)
        self.assertIsNotNone(result.current_history_timestamp)

    def test_current_version_carries_detail_libraries(self):
        summary = [
            {
                "is_current": True,
                "version_number": 4,
                "record_timestamp": "2026-09-01T00:00:00+00:00",
            }
        ]
        detail = {"raw_payload": {}, "libraries": ["cbc-workflow-o4a", "cbc-workflow-o4c"]}
        with (
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_versions",
                return_value=(summary, "live"),
            ),
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_version",
                return_value=(detail, "live"),
            ),
        ):
            result = resolve_current_version("S250801h")

        self.assertTrue(result.available)
        self.assertEqual(result.libraries, ["cbc-workflow-o4a", "cbc-workflow-o4c"])

    def test_current_version_missing_libraries_stays_none(self):
        summary = [
            {
                "is_current": True,
                "version_number": 4,
                "record_timestamp": "2026-09-01T00:00:00+00:00",
            }
        ]
        detail = {"raw_payload": {}, "libraries": "not-a-list"}
        with (
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_versions",
                return_value=(summary, "live"),
            ),
            mock.patch(
                "bilbyui.utils.gwflow_portal.get_version",
                return_value=(detail, "live"),
            ),
        ):
            result = resolve_current_version("S250801h")

        self.assertTrue(result.available)
        self.assertIsNone(result.libraries)

    def test_null_raw_payload_keeps_version_identity(self):
        """A canonical object-or-null payload must not suppress the pointer."""
        summary = [
            {
                "is_current": True,
                "version_number": 4,
                "record_timestamp": "2026-09-01T00:00:00+00:00",
            }
        ]
        for detail in ({"raw_payload": None}, {}):
            with self.subTest(detail=detail):
                with (
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_versions",
                        return_value=(summary, "live"),
                    ),
                    mock.patch(
                        "bilbyui.utils.gwflow_portal.get_version",
                        return_value=(detail, "live"),
                    ),
                ):
                    result = resolve_current_version("S250801h")

                self.assertTrue(result.available)
                self.assertIsNone(result.trigger_time)
                self.assertEqual(result.current_version_number, 4)
                self.assertIsNotNone(result.current_history_timestamp)


class TestSupereventEventIDResolver(BilbyTestCase):
    def test_cardinality_zero_one_and_many(self):
        self.assertIsNone(resolve_event_id_for_superevent("S250801h"))

        owned = EventID.objects.create(
            event_id="G700001",
            trigger_id="S250801h",
            gps_time=1438044067.0,
        )
        self.assertEqual(
            resolve_event_id_for_superevent("S250801h"),
            owned,
        )

        EventID.objects.create(
            event_id="G700002",
            trigger_id="S250801h",
            gps_time=1438044068.0,
        )
        with self.assertLogs(
            "bilbyui.utils.gwflow_portal",
            level="WARNING",
        ) as logs:
            result = resolve_event_id_for_superevent("S250801h")
        self.assertIsNone(result)
        self.assertIn("Ambiguous EventID ownership", " ".join(logs.output))

    def test_does_not_fall_back_to_event_identifier(self):
        EventID.objects.create(
            event_id="S250801h",
            trigger_id="S231013ab",
            gps_time=1381222535.0,
        )
        self.assertIsNone(resolve_event_id_for_superevent("S250801h"))


class TestEventIDCollisionGuard(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(
            id=301,
            name="GWF-9 test user",
            primary_email="gwf9@example.com",
        )

    def test_foreign_owner_collision_is_non_destructive(self):
        existing = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=1381222535.0,
            nickname="original",
        )

        message = create_event_id(
            self.user,
            event_id="G585653",
            gps_time=1438044067.054443,
            trigger_id="S250801h",
            nickname="replacement",
        )

        self.assertIn("conflict", message)
        self.assertIn("S231013ab", message)
        self.assertIn("S250801h", message)
        self.assertIn("no changes made", message)
        self.assertEqual(EventID.objects.filter(event_id="G585653").count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.trigger_id, "S231013ab")
        self.assertEqual(existing.gps_time, 1381222535.0)
        self.assertEqual(existing.nickname, "original")

    def test_uniqueness_race_reloads_and_reapplies_foreign_owner_policy(self):
        existing = EventID.objects.create(
            event_id="G700011",
            trigger_id="S231013ab",
            gps_time=1000.0,
            nickname="original",
        )
        with (
            mock.patch(
                "bilbyui.views.EventID.objects.get",
                side_effect=[EventID.DoesNotExist, existing],
            ),
            mock.patch.object(
                EventID,
                "save",
                side_effect=IntegrityError("duplicate key"),
            ),
        ):
            resolved, message = _create_event_id_guarded(
                "G700011",
                2000.0,
                trigger_id="S250801h",
                nickname="replacement",
            )

        self.assertEqual(resolved, existing)
        self.assertIn("conflict", message)
        existing.refresh_from_db()
        self.assertEqual(existing.trigger_id, "S231013ab")
        self.assertEqual(existing.gps_time, 1000.0)
        self.assertEqual(existing.nickname, "original")
        self.assertEqual(EventID.objects.filter(event_id="G700011").count(), 1)

    def test_same_owner_is_idempotent_and_empty_fields_backfill(self):
        existing = EventID.objects.create(
            event_id="G700010",
            trigger_id=None,
            gps_time=1000.0,
            nickname=None,
        )

        create_event_id(
            self.user,
            event_id="G700010",
            gps_time=2000.0,
            trigger_id="S250801h",
            nickname="backfilled",
        )
        create_event_id(
            self.user,
            event_id="G700010",
            gps_time=3000.0,
            trigger_id="S250801h",
            nickname="ignored",
        )

        existing.refresh_from_db()
        self.assertEqual(existing.trigger_id, "S250801h")
        self.assertEqual(existing.nickname, "backfilled")
        self.assertEqual(existing.gps_time, 1000.0)
        self.assertEqual(EventID.objects.filter(event_id="G700010").count(), 1)


@override_settings(
    GWFLOW_INGEST_USER=302,
    EMBARGO_START_TIME=1421884818.0,
)
class TestGWFlowAuthoritativeUpsert(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(
            id=302,
            name="GWF-9 ingest user",
            primary_email="gwf9-ingest@example.com",
        )

    def params(self, sname, **overrides):
        values = {
            "sname": sname,
            "schema_version": "v1",
            "libraries": ["cbc-workflow-o4c"],
            "is_pruned": False,
            "current_version_number": 1,
            "current_history_timestamp": "2026-08-01T00:00:00+00:00",
            "event_id": "G585653",
            "metadata": '{"GraceDB": {"Events": [{"GPSTime": 1.0}]}}',
            "files": [],
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_recomputes_trigger_pointer_and_scoped_link_together(self):
        foreign = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=1381222535.0,
        )
        owned = EventID.objects.create(
            event_id="G700020",
            trigger_id="S250801h",
            gps_time=1438044067.0,
        )
        resolved = GWFlowCurrentVersion(
            available=True,
            trigger_time=1438044067.054443,
            current_version_number=1,
            current_history_timestamp=datetime.datetime(
                2026,
                9,
                1,
                tzinfo=datetime.UTC,
            ),
            versions_state="live",
            detail_state="live",
        )

        with (
            mock.patch(
                "bilbyui.views.resolve_current_version",
                return_value=resolved,
            ),
            mock.patch("bilbyui.views.gwflow_elastic_search_update"),
            mock.patch(
                "bilbyui.views.get_version",
                return_value=({"raw_payload": {}}, "live"),
            ),
        ):
            upsert_gwflow_job(self.user, self.params("S250801h"))

        job = GWFlowJob.objects.get(sname="S250801h")
        self.assertEqual(job.trigger_time, 1438044067.054443)
        self.assertEqual(job.current_version_number, 1)
        self.assertEqual(
            job.current_history_timestamp,
            resolved.current_history_timestamp,
        )
        self.assertEqual(job.event_id, owned)
        self.assertNotEqual(job.event_id, foreign)

    def test_unavailable_clears_foreign_link_when_stored_time_unresolved(self):
        stored_timestamp = datetime.datetime(
            2026,
            7,
            1,
            tzinfo=datetime.UTC,
        )

        for index, trigger_time in enumerate((None, 1400.0)):
            with self.subTest(trigger_time=trigger_time):
                foreign = EventID.objects.create(
                    event_id=f"G58565{index}",
                    trigger_id=f"S23101{index}ab",
                    gps_time=1438044067.0,
                )
                job = GWFlowJob.objects.create(
                    sname=f"S25080{index + 1}h",
                    user=self.user,
                    trigger_time=trigger_time,
                    current_version_number=1,
                    current_history_timestamp=stored_timestamp,
                    event_id=foreign,
                )

                with (
                    mock.patch(
                        "bilbyui.views.resolve_current_version",
                        return_value=GWFlowCurrentVersion(
                            available=False,
                            reason="detail has no usable finite trigger time",
                        ),
                    ),
                    mock.patch(
                        "bilbyui.views.resolve_event_id_for_superevent",
                        return_value=None,
                    ),
                    mock.patch("bilbyui.views.gwflow_elastic_search_update"),
                ):
                    upsert_gwflow_job(
                        self.user,
                        self.params(
                            job.sname,
                            current_history_timestamp=stored_timestamp,
                        ),
                    )

                job.refresh_from_db()
                self.assertEqual(job.trigger_time, trigger_time)
                self.assertEqual(job.current_version_number, 1)
                self.assertEqual(
                    job.current_history_timestamp,
                    stored_timestamp,
                )
                self.assertIsNone(job.event_id)

    def test_unavailable_retains_same_owner_link_when_stored_time_unresolved(self):
        stored_timestamp = datetime.datetime(
            2026,
            7,
            1,
            tzinfo=datetime.UTC,
        )

        for index, trigger_time in enumerate((None, 1400.0)):
            with self.subTest(trigger_time=trigger_time):
                sname = f"S25081{index}h"
                owned = EventID.objects.create(
                    event_id=f"G70001{index}",
                    trigger_id=sname,
                    gps_time=1438044067.0,
                )
                job = GWFlowJob.objects.create(
                    sname=sname,
                    user=self.user,
                    trigger_time=trigger_time,
                    current_version_number=1,
                    current_history_timestamp=stored_timestamp,
                    event_id=owned,
                )

                with (
                    mock.patch(
                        "bilbyui.views.resolve_current_version",
                        return_value=GWFlowCurrentVersion(
                            available=False,
                            reason="detail has no usable finite trigger time",
                        ),
                    ),
                    mock.patch(
                        "bilbyui.views.resolve_event_id_for_superevent",
                        return_value=None,
                    ),
                    mock.patch("bilbyui.views.gwflow_elastic_search_update"),
                ):
                    upsert_gwflow_job(
                        self.user,
                        self.params(
                            job.sname,
                            current_history_timestamp=stored_timestamp,
                        ),
                    )

                job.refresh_from_db()
                self.assertEqual(job.trigger_time, trigger_time)
                self.assertEqual(job.current_version_number, 1)
                self.assertEqual(job.current_history_timestamp, stored_timestamp)
                self.assertEqual(job.event_id, owned)

    def test_unavailable_clears_foreign_link_when_own_time_is_embargoed(self):
        foreign = EventID.objects.create(
            event_id="G585659",
            trigger_id="S231019ab",
            gps_time=1438044067.0,
        )
        stored_timestamp = datetime.datetime(
            2026,
            7,
            1,
            tzinfo=datetime.UTC,
        )
        job = GWFlowJob.objects.create(
            sname="S250809h",
            user=self.user,
            trigger_time=1438044067.0,
            current_version_number=1,
            current_history_timestamp=stored_timestamp,
            event_id=foreign,
        )

        with (
            mock.patch(
                "bilbyui.views.resolve_current_version",
                return_value=GWFlowCurrentVersion(
                    available=False,
                    reason="detail has no usable finite trigger time",
                ),
            ),
            mock.patch(
                "bilbyui.views.resolve_event_id_for_superevent",
                return_value=None,
            ),
            mock.patch("bilbyui.views.gwflow_elastic_search_update"),
        ):
            upsert_gwflow_job(
                self.user,
                self.params(
                    job.sname,
                    current_history_timestamp=stored_timestamp,
                ),
            )

        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 1438044067.0)
        self.assertEqual(job.current_version_number, 1)
        self.assertEqual(job.current_history_timestamp, stored_timestamp)
        self.assertIsNone(job.event_id)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestGWFlowChildrenFollowParent(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(
            id=303,
            name="GWF-9 child user",
            primary_email="gwf9-child@example.com",
        )

    def test_handle_bilby_clears_stale_child_when_parent_link_is_none(self):
        stale = EventID.objects.create(
            event_id="G700030",
            trigger_id="S231013ab",
            gps_time=1000.0,
        )
        parent = GWFlowJob.objects.create(
            sname="S250801h",
            user=self.user,
            event_id=None,
        )
        child = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GWF9-child-clear",
            gwflow_job=parent,
            event_id=stale,
            ini_string="[data]\ndetectors = ['H1']\n",
        )

        call_command("es_ingest")

        child.refresh_from_db()
        self.assertIsNone(child.event_id)


@override_settings(
    CBCFLOW_PORTAL_URL="https://portal.example",
    CBCFLOW_PORTAL_TOKEN="token",
    IGNORE_ELASTIC_SEARCH=True,
)
class TestGWFlowChosenUIDCollisionPath(BilbyTestCase):
    class Response:
        def __init__(self, payload, status_code=200):
            self.payload = payload
            self.status_code = status_code

        def json(self):
            return self.payload

    def setUp(self):
        super().setUp()
        self.user = self.create_user(
            id=304,
            name="GWF-9 chosen UID user",
            primary_email="gwf9-chosen@example.com",
        )
