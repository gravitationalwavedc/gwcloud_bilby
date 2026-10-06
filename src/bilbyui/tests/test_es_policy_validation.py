"""Tests for Elasticsearch visibility-policy validation reports."""

from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from bilbyui.models import BilbyJob, EventID, GWFlowJob, IniKeyValue
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.es_policy_validation import (
    collect_shadow_comparison,
    collect_visibility_parity,
)

T = 100.0


@override_settings(
    EMBARGO_START_TIME=T,
    ELASTIC_SEARCH_INDEX="bilby-policy-test",
    ELASTIC_SEARCH_GWFLOW_INDEX="gwflow-policy-test",
)
class TestESPolicyValidation(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(id=71, primary_email="policy@example.com")
        self.counter = 0

    def bilby(self, *, trigger_time=None, is_ligo_job=False, private=False, simulation=None):
        self.counter += 1
        job = BilbyJob.objects.create(
            user=self.user,
            name=f"policy-{self.counter}",
            ini_string="",
            trigger_time=trigger_time,
            is_ligo_job=is_ligo_job,
            private=private,
        )
        if simulation is not None:
            IniKeyValue.objects.create(
                job=job,
                key="n_simulation",
                value=str(simulation),
                index=0,
                processed=False,
            )
        return job

    def gwflow(self, *, trigger_time=None, ligo_only=False, is_pruned=False, event_id=None):
        self.counter += 1
        return GWFlowJob.objects.create(
            user=self.user,
            sname=f"S24{self.counter:04d}a",
            trigger_time=trigger_time,
            ligo_only=ligo_only,
            is_pruned=is_pruned,
            event_id=event_id,
        )

    @staticmethod
    def hits(*ids):
        return [{"_id": str(stable_id)} for stable_id in ids]

    def parity(self, kind, hits):
        with (
            patch("bilbyui.utils.gwflow_es.get_es_client", return_value=object()),
            patch("bilbyui.utils.es_policy_validation.helpers.scan", return_value=hits),
        ):
            return collect_visibility_parity(kind, T)

    def test_visibility_equal_sets_pass_and_build_expected_scan(self):
        job = self.bilby(trigger_time=T - 1)
        with (
            patch("bilbyui.utils.gwflow_es.get_es_client", return_value=object()) as client,
            patch(
                "bilbyui.utils.es_policy_validation.helpers.scan",
                return_value=self.hits(job.id),
            ) as scan,
        ):
            report = collect_visibility_parity("bilby", T, batch=17)

        self.assertTrue(report.ok)
        self.assertEqual((report.orm_public, report.es_public), (1, 1))
        client.assert_called_once_with()
        kwargs = scan.call_args.kwargs
        self.assertEqual(kwargs["index"], "bilby-policy-test")
        self.assertEqual(kwargs["size"], 17)
        self.assertFalse(kwargs["_source"])
        self.assertFalse(kwargs["preserve_order"])

    def test_visibility_set_differences_fail(self):
        job = self.bilby(trigger_time=T - 1)
        missing = self.parity("bilby", [])
        extra = self.parity("bilby", self.hits(job.id, 999))

        self.assertEqual(missing.missing_in_es, [job.id])
        self.assertFalse(missing.ok)
        self.assertEqual(extra.extra_in_es, [999])
        self.assertFalse(extra.ok)

    def test_bilby_visibility_classes_cover_public_corpus(self):
        below = self.bilby(trigger_time=T - 1)
        null = self.bilby()
        simulation_equal = self.bilby(trigger_time=T, simulation=1)
        simulation_above = self.bilby(trigger_time=T + 1, simulation=2)
        # Correct policy excludes equality and above for non-simulations.
        self.bilby(trigger_time=T)
        self.bilby(trigger_time=T + 1)

        report = self.parity(
            "bilby",
            self.hits(below.id, null.id, simulation_equal.id, simulation_above.id),
        )

        self.assertEqual(
            report.classes,
            {"below": 1, "null_time": 1, "simulation": 2, "equal": 0, "above": 0},
        )
        self.assertTrue(report.ok)

    def test_visibility_classifier_surfaces_equal_and_above_when_adapter_returns_them(self):
        equal = self.bilby(trigger_time=T)
        above = self.bilby(trigger_time=T + 1)
        with (
            patch("bilbyui.utils.es_policy_validation.visible_to_user", side_effect=lambda qs, *_, **__: qs),
            patch("bilbyui.utils.es_policy_validation.helpers.scan", return_value=self.hits(equal.id, above.id)),
        ):
            report = collect_visibility_parity("bilby", T, es=object())

        self.assertEqual(report.classes["equal"], 1)
        self.assertEqual(report.classes["above"], 1)

    def test_gwflow_visibility_uses_non_pruned_scope_and_classes(self):
        below = self.gwflow(trigger_time=T - 1)
        null = self.gwflow()
        self.gwflow(trigger_time=T - 1, is_pruned=True)

        report = self.parity("gwflow", self.hits(below.id, null.id))

        self.assertEqual(report.orm_public, 2)
        self.assertEqual(report.classes["below"], 1)
        self.assertEqual(report.classes["null_time"], 1)
        self.assertTrue(report.ok)

    def test_shadow_produces_all_diagnostic_classes(self):
        self.bilby(trigger_time=T - 1, is_ligo_job=True)
        self.bilby(trigger_time=T + 1, is_ligo_job=True, simulation=1)
        self.bilby(is_ligo_job=True)
        self.bilby(trigger_time=T, is_ligo_job=False)

        report = collect_shadow_comparison("bilby", T, batch=2)

        self.assertEqual(report.flag_drift, 1)
        self.assertEqual(report.simulation, 1)
        self.assertEqual(report.unknown_trigger, 1)
        self.assertEqual(report.threshold_boundary, 1)
        self.assertEqual(report.total_mismatches, 4)
        self.assertEqual(report.new_exposures, 3)
        self.assertEqual(report.unexplained, 0)
        self.assertTrue(report.ok)

    def test_shadow_p0_invariant_is_unexplained_and_fails(self):
        self.gwflow(trigger_time=T + 1, ligo_only=True)
        with patch(
            "bilbyui.utils.es_policy_validation.is_record_public",
            return_value=True,
        ):
            report = collect_shadow_comparison("gwflow", T)

        self.assertEqual(report.unexplained, 1)
        self.assertEqual(report.new_exposures, 1)
        self.assertEqual(report.total_mismatches, 1)
        self.assertFalse(report.ok)

    def test_shadow_over_restriction_is_reported_but_passes(self):
        self.gwflow(trigger_time=T, ligo_only=False)

        report = collect_shadow_comparison("gwflow", T)

        self.assertEqual(report.threshold_boundary, 1)
        self.assertEqual(report.new_exposures, 0)
        self.assertEqual(report.unexplained, 0)
        self.assertTrue(report.ok)

    def test_shadow_uses_event_time(self):
        event = EventID.objects.create(event_id="G71001", gps_time=T)
        self.gwflow(ligo_only=False, event_id=event)

        report = collect_shadow_comparison("gwflow", T)

        self.assertEqual(report.threshold_boundary, 1)


    @override_settings(EMBARGO_START_TIME=200.0)
    def test_visibility_uses_explicit_threshold_instead_of_setting(self):
        self.bilby(trigger_time=150.0)

        report = self.parity("bilby", [])

        self.assertTrue(report.ok)
        self.assertEqual(report.orm_public, 0)
        self.assertEqual(report.classes["below"], 0)

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_shadow_uses_explicit_threshold_instead_of_setting(self):
        self.gwflow(trigger_time=150.0, ligo_only=True)

        report = collect_shadow_comparison("gwflow", 200.0)

        self.assertEqual(report.new_exposures, 1)
        self.assertEqual(report.flag_drift, 1)
        self.assertEqual(report.unexplained, 0)

    def test_visibility_orm_scan_uses_multiple_bounded_pages(self):
        jobs = [self.bilby(trigger_time=T - 1) for _ in range(5)]

        with (
            patch(
                "bilbyui.utils.es_policy_validation.helpers.scan",
                return_value=self.hits(*(job.id for job in jobs)),
            ),
            CaptureQueriesContext(connection) as queries,
        ):
            report = collect_visibility_parity("bilby", T, batch=2, es=object())

        page_queries = [
            query["sql"]
            for query in queries.captured_queries
            if 'FROM "bilbyui_bilbyjob"' in query["sql"] and "LIMIT 2" in query["sql"]
        ]
        self.assertTrue(report.ok)
        self.assertEqual(report.orm_public, 5)
        self.assertGreaterEqual(len(page_queries), 3)

    def test_invalid_kind_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "kind must be"):
            collect_visibility_parity("other", T, es=object())
        with self.assertRaisesRegex(ValueError, "kind must be"):
            collect_shadow_comparison("other", T)
