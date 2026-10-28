"""Security-completion locks for GWF-9 issue #124.

These tests intentionally use the incident threshold rather than duplicating
the generic threshold-1000 policy matrix in test_es_visibility_policy.
"""

from datetime import UTC, datetime
from io import StringIO
from unittest import mock

from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from django.core.management import call_command
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob, build_bilby_es_doc
from bilbyui.services.gwflow import _gwflow_public_visibility_clause
from bilbyui.services.jobs import _bilby_public_visibility_clause
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import visible_to_user
from bilbyui.utils.gwflow_es import build_gwflow_es_doc
from bilbyui.utils.gwflow_portal import GWFlowCurrentVersion

THRESHOLD = 1421884818.0
BELOW = 1421884817.0
AT = 1421884818.0
ABOVE = 1421884819.0
OLD_OWNER_GPS = 1381222535.0
CURRENT_TIMESTAMP = datetime(2025, 9, 4, 12, 0, tzinfo=UTC)
OLD_TIMESTAMP = datetime(2023, 10, 13, 12, 0, tzinfo=UTC)

LEAKED_SUPEREVENTS = (
    "S250706bq",
    "S250707ad",
    "S250707o",
    "S250711ck",
    "S250712ca",
    "S250723bb",
    "S250723be",
    "S250727dk",
    "S250801h",
    "S250803cn",
    "S250809ab",
    "S250810bu",
    "S250903d",
    "S250904br",
)


def _field_value(document, path):
    value = document
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            return False, None
        value = value[component]
    return True, value


def _matches_clause(document, clause):
    """Evaluate the limited structured ES clauses emitted by visibility code."""
    if "bool" in clause:
        bool_clause = clause["bool"]
        if "must_not" in bool_clause:
            return not _matches_clause(document, bool_clause["must_not"])

        should = bool_clause.get("should", [])
        minimum = bool_clause.get("minimum_should_match", 0)
        return sum(_matches_clause(document, item) for item in should) >= minimum

    if "exists" in clause:
        exists, _ = _field_value(document, clause["exists"]["field"])
        return exists

    if "range" in clause:
        field, operators = next(iter(clause["range"].items()))
        exists, value = _field_value(document, field)
        if not exists:
            return False
        comparisons = {
            "lt": lambda boundary: value < boundary,
            "gt": lambda boundary: value > boundary,
            "lte": lambda boundary: value <= boundary,
            "gte": lambda boundary: value >= boundary,
        }
        return all(comparisons[operator](boundary) for operator, boundary in operators.items())

    raise AssertionError(f"Unsupported test clause: {clause!r}")


@override_settings(EMBARGO_START_TIME=THRESHOLD, IGNORE_ELASTIC_SEARCH=True)
class TestIssueThresholdStrictestWins(BilbyTestCase):
    """Lock strictest-wins at the exact issue #124 embargo boundary."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = cls.create_user(
            id=9124,
            name="GWF-9 fixture owner",
            primary_email="gwf9-owner@example.com",
        )

    def setUp(self):
        self.anonymous = ADACSAnonymousUser()

    def _gwflow_job(self, suffix, own_time, event_time):
        event = EventID.objects.create(
            event_id=f"G9124{suffix:02d}",
            trigger_id=f"S-GWF9-{suffix}",
            gps_time=event_time,
        )
        return GWFlowJob.objects.create(
            sname=f"S-GWF9-{suffix}",
            user=self.owner,
            trigger_time=own_time,
            event_id=event,
        )

    def _bilby_child(self, suffix, parent_time, parent_event_time):
        parent = self._gwflow_job(
            100 + suffix,
            parent_time,
            parent_event_time,
        )
        with mock.patch.object(BilbyJob, "elastic_search_update"):
            return BilbyJob.objects.create(
                user=self.owner,
                name=f"gwf9-child-{suffix}",
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
                gwflow_job=parent,
            )

    def test_gwflow_issue_boundary_matrix_orm_and_es_agree(self):
        cases = (
            ("mixed-hidden", ABOVE, BELOW, False, ABOVE),
            ("both-below-visible", BELOW, BELOW, True, BELOW),
            ("own-boundary-hidden", AT, BELOW, False, AT),
            ("event-boundary-hidden", BELOW, AT, False, AT),
        )
        clause = _gwflow_public_visibility_clause(THRESHOLD)

        for suffix, (label, own_time, event_time, expected_visible, expected_max) in enumerate(
            cases,
            start=1,
        ):
            with self.subTest(case=label):
                job = self._gwflow_job(suffix, own_time, event_time)
                job = GWFlowJob.objects.select_related("event_id").get(pk=job.pk)
                document = build_gwflow_es_doc(job, {})

                orm_visible = visible_to_user(
                    GWFlowJob.objects.filter(pk=job.pk),
                    self.anonymous,
                    "GWFlowJob",
                ).exists()
                es_visible = _matches_clause(document, clause)

                self.assertEqual(document["_gwcloud"]["searchTriggerTime"], expected_max)
                self.assertEqual(orm_visible, expected_visible)
                self.assertEqual(es_visible, expected_visible)
                self.assertEqual(orm_visible, es_visible)

    @mock.patch(
        "bilbyui.models.request_lookup_users",
        return_value=(True, [{"name": "GWF-9 fixture owner"}]),
    )
    def test_bilby_child_inherits_parent_strictest_wins_in_orm_and_es(self, _lookup):
        cases = (
            ("mixed-hidden", ABOVE, BELOW, False, ABOVE),
            ("both-below-visible", BELOW, BELOW, True, BELOW),
            ("parent-boundary-hidden", AT, BELOW, False, AT),
            ("parent-event-boundary-hidden", BELOW, AT, False, AT),
        )
        clause = _bilby_public_visibility_clause(THRESHOLD)

        for suffix, (label, parent_time, event_time, expected_visible, expected_max) in enumerate(
            cases,
            start=1,
        ):
            with self.subTest(case=label):
                child = self._bilby_child(suffix, parent_time, event_time)
                child = BilbyJob.objects.select_related(
                    "event_id",
                    "gwflow_job__event_id",
                ).get(pk=child.pk)
                document = build_bilby_es_doc(child)

                orm_visible = visible_to_user(
                    BilbyJob.objects.filter(pk=child.pk),
                    self.anonymous,
                    "BilbyJob",
                ).exists()
                es_visible = _matches_clause(document, clause)

                self.assertEqual(document["searchTriggerTime"], expected_max)
                self.assertEqual(orm_visible, expected_visible)
                self.assertEqual(es_visible, expected_visible)
                self.assertEqual(orm_visible, es_visible)


@override_settings(
    EMBARGO_START_TIME=THRESHOLD,
    IGNORE_ELASTIC_SEARCH=True,
    CBCFLOW_PORTAL_URL="https://portal.example.com",
    CBCFLOW_PORTAL_TOKEN="fixture-token",
)
class TestFourteenSupereventSecurityCompletion(BilbyTestCase):
    """Deterministically model the 14-row incident through the repair path."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = cls.create_user(
            id=9125,
            name="GWF-9 repair fixture owner",
            primary_email="gwf9-repair@example.com",
        )

    def _resolved_version(self, sname):
        if sname == "S231013ab":
            return GWFlowCurrentVersion(
                available=True,
                trigger_time=OLD_OWNER_GPS,
                current_version_number=1,
                current_history_timestamp=OLD_TIMESTAMP,
                versions_state="fixture",
                detail_state="fixture",
            )

        index = LEAKED_SUPEREVENTS.index(sname)
        return GWFlowCurrentVersion(
            available=True,
            trigger_time=ABOVE + index,
            current_version_number=1,
            current_history_timestamp=CURRENT_TIMESTAMP,
            versions_state="fixture",
            detail_state="fixture",
        )

    @staticmethod
    def _versions(sname):
        timestamp = OLD_TIMESTAMP if sname == "S231013ab" else CURRENT_TIMESTAMP
        return (
            [
                {
                    "record_timestamp": timestamp,
                    "is_current": True,
                    "libraries": ["cbc-workflow-o4c"],
                }
            ],
            "fixture",
        )

    def test_repair_hides_all_fourteen_and_preserves_2023_owner(self):
        old_event = EventID.objects.create(
            event_id="G585653",
            trigger_id="S231013ab",
            gps_time=OLD_OWNER_GPS,
            nickname="original-2023-owner",
        )
        old_job = GWFlowJob.objects.create(
            sname="S231013ab",
            user=self.owner,
            trigger_time=OLD_OWNER_GPS,
            current_version_number=1,
            current_history_timestamp=OLD_TIMESTAMP,
            event_id=old_event,
            libraries=["cbc-workflow-o4c"],
        )

        leaked_jobs = []
        for index, sname in enumerate(LEAKED_SUPEREVENTS):
            EventID.objects.create(
                event_id=f"G9125{index:03d}",
                trigger_id=sname,
                gps_time=ABOVE + index,
            )
            leaked_jobs.append(
                GWFlowJob.objects.create(
                    sname=sname,
                    user=self.owner,
                    trigger_time=OLD_OWNER_GPS,
                    current_version_number=1,
                    current_history_timestamp=OLD_TIMESTAMP,
                    event_id=old_event,
                )
            )

        stdout = StringIO()
        stderr = StringIO()
        with (
            mock.patch(
                "bilbyui.management.commands.gwflow_es_backfill.resolve_current_version",
                side_effect=self._resolved_version,
            ),
            mock.patch(
                "bilbyui.management.commands.gwflow_es_backfill.get_versions",
                side_effect=self._versions,
            ),
        ):
            result = call_command(
                "gwflow_es_backfill",
                pacing=0,
                max_retries=0,
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(result, 0)
        self.assertIn("scanned=15 changed=14 unavailable=0", stdout.getvalue())

        anonymous = ADACSAnonymousUser()
        visible_ids = set(
            visible_to_user(
                GWFlowJob.objects.filter(pk__in=[job.pk for job in leaked_jobs]),
                anonymous,
                "GWFlowJob",
            ).values_list("pk", flat=True)
        )
        self.assertEqual(visible_ids, set())

        for index, original in enumerate(leaked_jobs):
            with self.subTest(sname=original.sname):
                repaired = GWFlowJob.objects.select_related("event_id").get(pk=original.pk)
                self.assertGreaterEqual(repaired.trigger_time, THRESHOLD)
                self.assertEqual(repaired.current_version_number, 1)
                self.assertEqual(repaired.event_id.trigger_id, repaired.sname)
                self.assertFalse(
                    visible_to_user(
                        GWFlowJob.objects.filter(pk=repaired.pk),
                        anonymous,
                        "GWFlowJob",
                    ).exists()
                )
                document = build_gwflow_es_doc(repaired, {})
                self.assertEqual(
                    document["_gwcloud"]["searchTriggerTime"],
                    ABOVE + index,
                )
                self.assertFalse(
                    _matches_clause(
                        document,
                        _gwflow_public_visibility_clause(THRESHOLD),
                    )
                )

        old_event.refresh_from_db()
        old_job.refresh_from_db()
        self.assertEqual(old_event.event_id, "G585653")
        self.assertEqual(old_event.trigger_id, "S231013ab")
        self.assertEqual(old_event.gps_time, OLD_OWNER_GPS)
        self.assertEqual(old_event.nickname, "original-2023-owner")
        self.assertEqual(old_job.event_id, old_event)
        self.assertEqual(old_job.trigger_time, OLD_OWNER_GPS)
        self.assertTrue(
            visible_to_user(
                GWFlowJob.objects.filter(pk=old_job.pk),
                anonymous,
                "GWFlowJob",
            ).exists()
        )
