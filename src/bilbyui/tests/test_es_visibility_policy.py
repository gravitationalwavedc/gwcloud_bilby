from unittest import mock

from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob, build_bilby_es_doc
from bilbyui.services.gwflow import _gwflow_public_visibility_clause
from bilbyui.services.jobs import _bilby_public_visibility_clause
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import visible_to_user
from bilbyui.utils.gwflow_es import build_gwflow_es_doc

THRESHOLD = 1000.0


def _field_value(document, path):
    value = document
    for component in path.split("."):
        if not isinstance(value, dict) or component not in value:
            return False, None
        value = value[component]
    return True, value


def _matches_clause(document, clause):
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
        return all(
            {
                "lt": value < boundary,
                "gt": value > boundary,
                "lte": value <= boundary,
                "gte": value >= boundary,
            }[operator]
            for operator, boundary in operators.items()
        )

    raise AssertionError(f"Unsupported test clause: {clause!r}")


@override_settings(EMBARGO_START_TIME=THRESHOLD)
class TestBilbyDBESParity(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(
            id=810,
            name="Parity User",
            primary_email="parity810@example.com",
            authentication_method="password",
        )

    def _event(self, suffix, gps_time):
        return EventID.objects.create(event_id=f"G81{suffix:04d}", gps_time=gps_time)

    def _parent(self, suffix, trigger_time=None, event_time=None):
        event = self._event(100 + suffix, event_time) if event_time is not None else None
        return GWFlowJob.objects.create(
            sname=f"S-PARITY-{suffix}",
            user=self.user,
            trigger_time=trigger_time,
            event_id=event,
        )

    def _job(
        self,
        suffix,
        *,
        trigger_time=None,
        event_time=None,
        parent_trigger=None,
        parent_event=None,
        simulation=False,
    ):
        event = self._event(suffix, event_time) if event_time is not None else None
        parent = None
        if parent_trigger is not None or parent_event is not None:
            parent = self._parent(suffix, parent_trigger, parent_event)

        with mock.patch.object(BilbyJob, "elastic_search_update"):
            job = BilbyJob.objects.create(
                user=self.user,
                name=f"bilby-parity-{suffix}",
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
                trigger_time=trigger_time,
                event_id=event,
                gwflow_job=parent,
            )

        if simulation:
            raw_simulation = job.inikeyvalue_set.filter(
                key="n_simulation",
                processed=False,
            ).first()
            if raw_simulation is None:
                job.inikeyvalue_set.create(
                    key="n_simulation",
                    value="1",
                    processed=False,
                    index=999,
                )
            else:
                raw_simulation.value = "1"
                raw_simulation.save(update_fields=["value"])
        return job

    @mock.patch(
        "bilbyui.models.request_lookup_users",
        return_value=(True, [{"name": "Parity User"}]),
    )
    def test_bilby_policy_matrix(self, lookup_users):
        cases = (
            ("all-null", {}, None, True),
            ("below", {"trigger_time": 999.0}, 999.0, True),
            ("equality", {"trigger_time": 1000.0}, 1000.0, False),
            ("above", {"trigger_time": 1001.0}, 1001.0, False),
            ("direct-event-only", {"event_time": 1001.0}, 1001.0, False),
            ("parent-trigger-only", {"parent_trigger": 1001.0}, 1001.0, False),
            ("parent-event-only", {"parent_event": 1001.0}, 1001.0, False),
            (
                "mixed-strictest-wins",
                {
                    "trigger_time": 900.0,
                    "event_time": 950.0,
                    "parent_trigger": 999.0,
                    "parent_event": 1001.0,
                },
                1001.0,
                False,
            ),
            (
                "simulation-embargoed",
                {"trigger_time": 1001.0, "simulation": True},
                1001.0,
                True,
            ),
        )

        clause = _bilby_public_visibility_clause(THRESHOLD)
        for suffix, (label, values, expected_stored, expected_visible) in enumerate(cases, start=1):
            with self.subTest(case=label):
                job = self._job(suffix, **values)
                loaded = BilbyJob.objects.select_related(
                    "event_id",
                    "gwflow_job__event_id",
                ).get(pk=job.pk)
                document = build_bilby_es_doc(loaded)

                orm_visible = visible_to_user(
                    BilbyJob.objects.filter(pk=job.pk),
                    self.user,
                    "BilbyJob",
                ).exists()
                es_visible = _matches_clause(document, clause)

                if expected_stored is None:
                    self.assertNotIn("searchTriggerTime", document)
                else:
                    self.assertEqual(document["searchTriggerTime"], expected_stored)
                self.assertEqual(orm_visible, expected_visible)
                self.assertEqual(es_visible, expected_visible)
                self.assertEqual(orm_visible, es_visible)


@override_settings(EMBARGO_START_TIME=THRESHOLD)
class TestGWFlowDBESParity(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(
            id=820,
            name="GWFlow Parity User",
            primary_email="parity820@example.com",
            authentication_method="password",
        )

    def test_gwflow_policy_matrix(self):
        cases = (
            ("all-null", None, None, None, True),
            ("own-below", 999.0, None, 999.0, True),
            ("own-equality", 1000.0, None, 1000.0, False),
            ("own-above", 1001.0, None, 1001.0, False),
            ("event-below", None, 999.0, 999.0, True),
            ("event-equality", None, 1000.0, 1000.0, False),
            ("event-above", None, 1001.0, 1001.0, False),
            ("own-event-strictest", 900.0, 1001.0, 1001.0, False),
        )

        clause = _gwflow_public_visibility_clause(THRESHOLD)
        for suffix, (label, own_time, event_time, expected_stored, expected_visible) in enumerate(cases, start=1):
            with self.subTest(case=label):
                event = (
                    EventID.objects.create(
                        event_id=f"G82{suffix:04d}",
                        gps_time=event_time,
                    )
                    if event_time is not None
                    else None
                )
                job = GWFlowJob.objects.create(
                    sname=f"S-GWFLOW-PARITY-{suffix}",
                    user=self.user,
                    trigger_time=own_time,
                    event_id=event,
                )
                loaded = GWFlowJob.objects.select_related("event_id").get(pk=job.pk)
                document = build_gwflow_es_doc(loaded, {})

                orm_visible = visible_to_user(
                    GWFlowJob.objects.filter(pk=job.pk),
                    self.user,
                    "GWFlowJob",
                ).exists()
                es_visible = _matches_clause(document, clause)

                envelope = document["_gwcloud"]
                if expected_stored is None:
                    self.assertNotIn("searchTriggerTime", envelope)
                else:
                    self.assertEqual(envelope["searchTriggerTime"], expected_stored)
                self.assertEqual(orm_visible, expected_visible)
                self.assertEqual(es_visible, expected_visible)
                self.assertEqual(orm_visible, es_visible)
