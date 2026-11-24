from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import numpy as np
from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.checks import run_checks
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import (
    annotate_simulation,
    get_embargo_start,
    is_public,
    is_record_public,
    is_simulated_value,
    reset_embargo_start_cache,
    resolve_job_trigger,
    should_embargo_job,
    user_subject_to_embargo,
)

User = get_user_model()


class TestEmbargoStart(BilbyTestCase):
    def setUp(self):
        super().setUp()
        reset_embargo_start_cache()

    def tearDown(self):
        reset_embargo_start_cache()
        super().tearDown()

    @override_settings(EMBARGO_START_TIME=None)
    def test_none_disables_embargo(self):
        self.assertIsNone(get_embargo_start())

    @override_settings(EMBARGO_START_TIME="")
    def test_empty_string_disables_embargo(self):
        self.assertIsNone(get_embargo_start())

    @override_settings(EMBARGO_START_TIME="123.5")
    def test_numeric_string_returns_float(self):
        self.assertEqual(get_embargo_start(), 123.5)

    @override_settings(EMBARGO_START_TIME=456)
    def test_numeric_value_returns_float(self):
        self.assertEqual(get_embargo_start(), 456.0)

    def test_malformed_values_raise(self):
        for raw in ("not-a-number", " ", object(), True, False):
            with self.subTest(raw=raw), override_settings(EMBARGO_START_TIME=raw):
                reset_embargo_start_cache()
                with self.assertRaises(ImproperlyConfigured):
                    get_embargo_start()

    def test_non_finite_values_raise(self):
        values = ("nan", "inf", "-inf", float("nan"), float("inf"), float("-inf"))
        for raw in values:
            with self.subTest(raw=raw), override_settings(EMBARGO_START_TIME=raw):
                reset_embargo_start_cache()
                with self.assertRaises(ImproperlyConfigured):
                    get_embargo_start()

    def test_same_raw_value_is_not_reparsed(self):
        class CountingFloat:
            calls = 0

            def __float__(self):
                self.calls += 1
                return 123.0

        raw = CountingFloat()
        with override_settings(EMBARGO_START_TIME=raw):
            self.assertEqual(get_embargo_start(), 123.0)
            self.assertEqual(get_embargo_start(), 123.0)
        self.assertEqual(raw.calls, 1)

    def test_override_settings_changes_cached_result(self):
        with override_settings(EMBARGO_START_TIME="10"):
            self.assertEqual(get_embargo_start(), 10.0)
        with override_settings(EMBARGO_START_TIME="20"):
            self.assertEqual(get_embargo_start(), 20.0)

    def test_reset_clears_cached_result(self):
        class CountingFloat:
            calls = 0

            def __float__(self):
                self.calls += 1
                return 123.0

        raw = CountingFloat()
        with override_settings(EMBARGO_START_TIME=raw):
            get_embargo_start()
            reset_embargo_start_cache()
            get_embargo_start()
        self.assertEqual(raw.calls, 2)


class TestEmbargoSystemCheck(BilbyTestCase):
    def setUp(self):
        super().setUp()
        reset_embargo_start_cache()

    def tearDown(self):
        reset_embargo_start_cache()
        super().tearDown()

    def _embargo_errors(self):
        return [error for error in run_checks() if error.id == "bilbyui.E001"]

    @override_settings(EMBARGO_START_TIME="123.5")
    def test_valid_setting_has_no_error(self):
        self.assertEqual(self._embargo_errors(), [])

    @override_settings(EMBARGO_START_TIME=None)
    def test_disabled_setting_has_no_error(self):
        self.assertEqual(self._embargo_errors(), [])

    @override_settings(EMBARGO_START_TIME="bad")
    def test_malformed_setting_reports_one_error(self):
        errors = self._embargo_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "bilbyui.E001")

    @override_settings(EMBARGO_START_TIME="nan")
    def test_non_finite_setting_reports_one_error(self):
        errors = self._embargo_errors()
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "bilbyui.E001")

    @override_settings(EMBARGO_START_TIME=True)
    def test_check_reports_instead_of_raising(self):
        self.assertEqual(len(self._embargo_errors()), 1)

    @override_settings(EMBARGO_START_TIME="bad")
    def test_app_ready_does_not_parse_setting(self):
        apps.get_app_config("bilbyui").ready()


class TestUserSubjectToEmbargo(BilbyTestCase):
    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo(self):
        # If no embargo, no users embargoed
        self.user = ADACSAnonymousUser()
        self.assertFalse(user_subject_to_embargo(self.user))

        self.user = self.create_user()
        self.assertFalse(user_subject_to_embargo(self.user))

        self.user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertFalse(user_subject_to_embargo(self.user))

    @override_settings(EMBARGO_START_TIME=1)
    def test_with_embargo(self):
        # User is only exempt from embargo if they are a LIGO user
        self.user = ADACSAnonymousUser()
        self.assertTrue(user_subject_to_embargo(self.user))

        self.assertTrue(user_subject_to_embargo(self.user))

        self.user = self.create_user()
        self.assertTrue(user_subject_to_embargo(self.user))

        self.user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertFalse(user_subject_to_embargo(self.user))


class TestShouldEmbargoJob(BilbyTestCase):
    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo(self):
        # If no embargo, no jobs embargoed
        self.user = ADACSAnonymousUser()
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user = self.create_user()
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_with_embargo(self):
        # Jobs should be embargoed is the trigger time is later than EMBARGO_START_TIME,
        # the job is run on real data, and the user is not a LIGO user
        self.user = ADACSAnonymousUser()
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, 2.0, True))
        self.assertTrue(should_embargo_job(self.user, 2.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user = self.create_user()
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, 2.0, True))
        self.assertTrue(should_embargo_job(self.user, 2.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, 2.0, True))
        self.assertFalse(should_embargo_job(self.user, 2.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

    @override_settings(EMBARGO_START_TIME="1.5")
    def test_with_embargo_string_start_time(self):
        # EMBARGO_START_TIME arrives as a string from the environment; it should
        # be treated as a numeric GPS threshold (regression: float >= str raised
        # TypeError)
        self.user = ADACSAnonymousUser()
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertTrue(should_embargo_job(self.user, 2.0, False))

    @override_settings(EMBARGO_START_TIME="not-a-number")
    def test_with_embargo_malformed_start_time(self):
        self.user = ADACSAnonymousUser()
        with self.assertRaises(ImproperlyConfigured):
            should_embargo_job(self.user, 2.0, False)

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_with_embargo_none_user(self):
        # When user is None, should treat as non-LIGO user for embargo checking
        self.assertFalse(should_embargo_job(None, 1.0, True))
        self.assertFalse(should_embargo_job(None, 1.0, False))
        self.assertFalse(should_embargo_job(None, 2.0, True))
        self.assertTrue(should_embargo_job(None, 2.0, False))
        self.assertFalse(should_embargo_job(None, None, True))
        self.assertFalse(should_embargo_job(None, None, False))


class TestIsPublic(BilbyTestCase):
    def setUp(self):
        super().setUp()
        reset_embargo_start_cache()
        self.user = ADACSAnonymousUser()

    def tearDown(self):
        reset_embargo_start_cache()
        super().tearDown()

    @override_settings(EMBARGO_START_TIME=None)
    def test_disabled_threshold_is_public(self):
        self.assertTrue(is_public([100.0], False, self.user))

    @override_settings(EMBARGO_START_TIME=10)
    def test_ligo_member_is_public(self):
        user = self.create_user()
        user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertTrue(is_public([10.0, 11.0], False, user))

    @override_settings(EMBARGO_START_TIME=10)
    def test_simulation_is_public(self):
        self.assertTrue(is_public([10.0, 11.0], True, self.user))

    @override_settings(EMBARGO_START_TIME=10)
    def test_null_and_before_times_are_public(self):
        cases = ([None], [None, None], [1.0, 9.999])
        for trigger_times in cases:
            with self.subTest(trigger_times=trigger_times):
                self.assertTrue(is_public(trigger_times, False, self.user))

    @override_settings(EMBARGO_START_TIME=10)
    def test_equal_after_and_parent_times_restrict(self):
        cases = ([10.0], [11.0], [None, 10.0], [1.0, None, 11.0])
        for trigger_times in cases:
            with self.subTest(trigger_times=trigger_times):
                self.assertFalse(is_public(trigger_times, False, self.user))

    @override_settings(EMBARGO_START_TIME=10)
    def test_invalid_times_raise(self):
        for trigger_time, exception in (
            (True, TypeError),
            (False, TypeError),
            ("10", TypeError),
            (float("nan"), ValueError),
            (float("inf"), ValueError),
            (float("-inf"), ValueError),
        ):
            with self.subTest(trigger_time=trigger_time), self.assertRaises(exception):
                is_public([trigger_time], False, self.user)


class TestSimulationGrammar(BilbyTestCase):
    def test_positive_values(self):
        for value in ("1", "+1", " 1 ", "\t+42\t", "999999999"):
            with self.subTest(value=value):
                self.assertTrue(is_simulated_value(value))

    def test_zero_and_invalid_values(self):
        values = (
            "0",
            "+0",
            " 000 ",
            None,
            "",
            " ",
            "-1",
            "1.0",
            "1e2",
            "text",
            "1\n",
            "\n1",
            "1000000000",
            True,
            False,
            1,
        )
        for value in values:
            with self.subTest(value=value):
                self.assertFalse(is_simulated_value(value))


class TestAnnotateSimulation(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user(
            id=9100,
            name="simulation annotation user",
            primary_email="simulation-annotation@example.com",
        )

    def _job(self, name):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name=name,
            description=name,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        job.inikeyvalue_set.filter(key="n_simulation").delete()
        return job

    def _add_value(self, job, value, *, processed=False):
        from bilbyui.models import IniKeyValue

        IniKeyValue.objects.create(
            job=job,
            key="n_simulation",
            value=value,
            index=0,
            processed=processed,
        )

    def test_python_and_annotation_agree(self):
        values = (
            "0",
            "+0",
            " 000 ",
            "1",
            "+1",
            " 1 ",
            "999999999",
            "1000000000",
            "",
            " ",
            "-1",
            "1.0",
            "1e2",
            "text",
            "1\n",
        )
        jobs = []
        for index, value in enumerate(values):
            job = self._job(f"grammar {index}")
            self._add_value(job, value)
            jobs.append((job, value))

        annotated = {
            job.pk: job for job in annotate_simulation(BilbyJob.objects.filter(pk__in=[job.pk for job, _ in jobs]))
        }
        for job, value in jobs:
            with self.subTest(value=value):
                expected = int(value) if is_simulated_value(value) else None
                if value.strip(" \t").lstrip("+").isdigit() and len(value.strip(" \t").lstrip("+")) <= 9:
                    expected = int(value)
                self.assertEqual(annotated[job.pk].simulated, expected)

    def test_missing_value_annotates_none(self):
        job = self._job("missing")
        annotated = annotate_simulation(BilbyJob.objects.filter(pk=job.pk)).get()
        self.assertIsNone(annotated.n_sim_raw)
        self.assertIsNone(annotated.simulated)

    def test_raw_unprocessed_value_is_used(self):
        job = self._job("raw")
        self._add_value(job, "2", processed=False)
        annotated = annotate_simulation(BilbyJob.objects.filter(pk=job.pk)).get()
        self.assertEqual(annotated.n_sim_raw, "2")
        self.assertEqual(annotated.simulated, 2)

    def test_processed_value_does_not_grant_simulation(self):
        job = self._job("processed")
        self._add_value(job, "2", processed=True)
        annotated = annotate_simulation(BilbyJob.objects.filter(pk=job.pk)).get()
        self.assertIsNone(annotated.n_sim_raw)
        self.assertIsNone(annotated.simulated)

    def test_invalid_value_is_not_cast(self):
        job = self._job("invalid")
        self._add_value(job, "not-an-integer", processed=False)
        annotated = annotate_simulation(BilbyJob.objects.filter(pk=job.pk)).get()
        self.assertEqual(annotated.n_sim_raw, "not-an-integer")
        self.assertIsNone(annotated.simulated)


@override_settings(EMBARGO_START_TIME=100)
class TestRecordPublic(BilbyTestCase):
    def setUp(self):
        super().setUp()
        reset_embargo_start_cache()
        self.user = ADACSAnonymousUser()
        self.owner = self.create_user(
            id=9200,
            name="record visibility owner",
            primary_email="record-visibility@example.com",
        )

    def tearDown(self):
        reset_embargo_start_cache()
        super().tearDown()

    def create_event(self, number, gps_time):
        return EventID.objects.create(
            event_id=f"G92{number:04d}",
            gps_time=gps_time,
        )

    def create_gwflow(self, number, trigger_time=None, event=None):
        return GWFlowJob.objects.create(
            sname=f"S2309{number:02d}a",
            user=self.owner,
            trigger_time=trigger_time,
            event_id=event,
        )

    def create_bilby(
        self,
        number,
        trigger_time=None,
        event=None,
        gwflow_job=None,
    ):
        return BilbyJob.objects.create(
            user=self.owner,
            name=f"record visibility {number}",
            ini_string="",
            trigger_time=trigger_time,
            event_id=event,
            gwflow_job=gwflow_job,
        )

    def test_event_equality_and_zero_queries(self):
        before = self.create_event(1, 99)
        equal = self.create_event(2, 100)
        before = EventID.objects.get(pk=before.pk)
        equal = EventID.objects.get(pk=equal.pk)

        with self.assertNumQueries(0):
            self.assertTrue(is_record_public(before, self.user))
            self.assertFalse(is_record_public(equal, self.user, is_simulation=True))

    def test_gwflow_linked_unlinked_all_null_and_zero_queries(self):
        restricted_event = self.create_event(3, 100)
        linked = self.create_gwflow(1, 99, restricted_event)
        unlinked = self.create_gwflow(2, 99)
        all_null = self.create_gwflow(3)
        records = {
            record.pk: record
            for record in GWFlowJob.objects.filter(pk__in=[linked.pk, unlinked.pk, all_null.pk]).select_related(
                "event_id"
            )
        }

        with self.assertNumQueries(0):
            self.assertFalse(is_record_public(records[linked.pk], self.user))
            self.assertTrue(is_record_public(records[unlinked.pk], self.user))
            self.assertTrue(is_record_public(records[all_null.pk], self.user))

    def test_bilby_paths_simulation_and_zero_queries(self):
        public_event = self.create_event(4, 99)
        restricted_event = self.create_event(5, 100)
        public_parent = self.create_gwflow(4, 99, public_event)
        trigger_tainted_parent = self.create_gwflow(5, 100, public_event)
        event_tainted_parent = self.create_gwflow(6, 99, restricted_event)
        public = self.create_bilby(1, 99, public_event, public_parent)
        direct_taint = self.create_bilby(2, 99, restricted_event)
        parent_trigger_taint = self.create_bilby(3, 99, public_event, trigger_tainted_parent)
        parent_event_taint = self.create_bilby(4, 99, public_event, event_tainted_parent)
        unlinked = self.create_bilby(5, 99)
        all_null = self.create_bilby(6)
        jobs = [
            public,
            direct_taint,
            parent_trigger_taint,
            parent_event_taint,
            unlinked,
            all_null,
        ]
        records = {
            record.pk: record
            for record in BilbyJob.objects.filter(pk__in=[job.pk for job in jobs]).select_related(
                "event_id", "gwflow_job__event_id"
            )
        }

        with self.assertNumQueries(0):
            self.assertTrue(is_record_public(records[public.pk], self.user, is_simulation=False))
            for restricted in (
                direct_taint,
                parent_trigger_taint,
                parent_event_taint,
            ):
                self.assertFalse(
                    is_record_public(
                        records[restricted.pk],
                        self.user,
                        is_simulation=False,
                    )
                )
            self.assertTrue(
                is_record_public(
                    records[parent_event_taint.pk],
                    self.user,
                    is_simulation=True,
                )
            )
            self.assertTrue(is_record_public(records[unlinked.pk], self.user, is_simulation=False))
            self.assertTrue(is_record_public(records[all_null.pk], self.user, is_simulation=False))

    def test_bilby_requires_simulation_state(self):
        job = self.create_bilby(7)
        with self.assertRaisesRegex(
            ValueError,
            r"is_simulated_value.*annotate_simulation",
        ):
            is_record_public(job, self.user)

    def test_unsupported_type_raises(self):
        with self.assertRaises(TypeError):
            is_record_public(object(), self.user)


class TestResolveJobTrigger(BilbyTestCase):
    def test_processed_float_preferred(self):
        processed = SimpleNamespace(trigger_time=2.5)
        args = SimpleNamespace(trigger_time=9.0)
        self.assertEqual(resolve_job_trigger(processed, args), 2.5)

    def test_processed_none_falls_back_to_raw(self):
        processed = SimpleNamespace(trigger_time=None)
        args = SimpleNamespace(trigger_time="7.5")
        self.assertEqual(resolve_job_trigger(processed, args), 7.5)

    def test_numeric_string_normalised(self):
        self.assertEqual(resolve_job_trigger(None, SimpleNamespace(trigger_time="3.0")), 3.0)

    def test_event_name_resolved_via_gwosc(self):
        with mock.patch("bilbyui.utils.embargo.event_gps", return_value=1126259462.0):
            self.assertEqual(
                resolve_job_trigger(None, SimpleNamespace(trigger_time="GW150914")),
                1126259462.0,
            )

    def test_event_name_resolution_failure_returns_none(self):
        with mock.patch("bilbyui.utils.embargo.event_gps", side_effect=ValueError("not found")):
            self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time="GW999999")))

    def test_event_gps_malformed_output_returns_none(self):
        # event_gps returning a non-real value must collapse to None, never raise.
        for bad in (None, True, False, object(), "not-a-number"):
            with self.subTest(bad=bad):
                with mock.patch("bilbyui.utils.embargo.event_gps", return_value=bad):
                    self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time="GW150914")))

    def test_decimal_normalised(self):
        # The structured admission path passes a graphene.Decimal; it must be
        # normalised to a finite float (or None), not dropped.
        self.assertEqual(resolve_job_trigger(None, SimpleNamespace(trigger_time=Decimal("2.5"))), 2.5)
        self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time=Decimal("NaN"))))

    def test_boolean_rejected(self):
        self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time=True)))
        self.assertIsNone(resolve_job_trigger(SimpleNamespace(trigger_time=False), None))

    def test_numpy_bool_rejected(self):
        # numpy.bool_ is not a Python bool subclass; it must be routed through
        # value.item() so it is rejected like a Python bool rather than
        # coerced to a finite GPS time (float(np.bool_(True)) == 1.0).
        self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time=np.bool_(True))))
        self.assertIsNone(resolve_job_trigger(SimpleNamespace(trigger_time=np.bool_(False)), None))

    def test_numpy_float64_normalised(self):
        self.assertEqual(resolve_job_trigger(None, SimpleNamespace(trigger_time=np.float64(2.5))), 2.5)
        self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time=np.float64("nan"))))

    def test_non_finite_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), "nan", "inf"):
            with self.subTest(value=value):
                self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time=value)))

    def test_missing_both_returns_none(self):
        self.assertIsNone(resolve_job_trigger())
        self.assertIsNone(resolve_job_trigger(SimpleNamespace(trigger_time=None), SimpleNamespace(trigger_time=None)))

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_admission_rejects_non_member_on_embargoed_real_job(self):
        # A non-member attempting an embargoed real job is still rejected.
        nonmember = self.create_user(
            id=9001,
            name="nonmember",
            primary_email="nonmember@example.com",
            authentication_method="password",
        )
        self.assertTrue(should_embargo_job(nonmember, 200.0, False))
        self.assertFalse(should_embargo_job(nonmember, 50.0, False))
        self.assertFalse(should_embargo_job(nonmember, 200.0, True))


class TestVisibleToUser(BilbyTestCase):
    def setUp(self):
        from bilbyui.utils.embargo import reset_embargo_start_cache

        reset_embargo_start_cache()
        self.owner = self.create_user(
            id=21,
            name="adapter owner",
            primary_email="adapter-owner@example.com",
        )
        self.nonmember = self.create_user(
            id=22,
            name="public user",
            primary_email="public-user@example.com",
        )
        self.member = self.create_user(
            id=23,
            name="ligo user",
            primary_email="ligo-user@example.com",
            authentication_method="ligo_shibboleth",
        )

    def tearDown(self):
        from bilbyui.utils.embargo import reset_embargo_start_cache

        reset_embargo_start_cache()
        super().tearDown()

    def _event(self, suffix, gps_time):
        from bilbyui.models import EventID

        return EventID.objects.create(
            event_id=f"G{900000 + suffix}",
            gps_time=gps_time,
        )

    def _gwflow(self, suffix, trigger_time=None, event=None):
        from bilbyui.models import GWFlowJob

        return GWFlowJob.objects.create(
            sname=f"S{suffix:06d}a",
            user=self.owner,
            trigger_time=trigger_time,
            event_id=event,
        )

    def _bilby(
        self,
        name,
        trigger_time=None,
        event=None,
        gwflow=None,
        simulation_value=None,
        simulation_processed=False,
    ):
        from bilbyui.models import BilbyJob, IniKeyValue
        from bilbyui.tests.test_utils import create_test_ini_string

        job = BilbyJob.objects.create(
            user=self.owner,
            name=name,
            description=name,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            event_id=event,
            gwflow_job=gwflow,
        )
        # The ini contains no trigger-time, so parse_ini_file derives NULL.
        # Write the explicit trigger_time via QuerySet.update (bypassing the
        # save override) so the visibility tests exercise the column value.
        if trigger_time is not None:
            BilbyJob.objects.filter(pk=job.pk).update(trigger_time=trigger_time)
        job.inikeyvalue_set.filter(key="n_simulation").delete()
        if simulation_value is not None:
            IniKeyValue.objects.create(
                job=job,
                key="n_simulation",
                value=simulation_value,
                index=100,
                processed=simulation_processed,
            )
        return job

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_event_id_truth_table(self):
        from bilbyui.models import EventID
        from bilbyui.utils.embargo import visible_to_user

        expected = {
            self._event(1, None).pk,
            self._event(2, 99.0).pk,
        }
        self._event(3, 100.0)
        self._event(4, 101.0)

        actual = set(visible_to_user(EventID.objects.all(), self.nonmember, "EventID").values_list("pk", flat=True))
        self.assertEqual(actual, expected)

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_gwflow_truth_table_and_nullable_relation(self):
        from bilbyui.models import GWFlowJob
        from bilbyui.utils.embargo import visible_to_user

        early_event = self._event(10, 99.0)
        equal_event = self._event(11, 100.0)
        expected = {
            self._gwflow(10, None, None).pk,
            self._gwflow(11, 99.0, early_event).pk,
            self._gwflow(12, None, early_event).pk,
            self._gwflow(13, 99.0, None).pk,
        }
        self._gwflow(14, 100.0, early_event)
        self._gwflow(15, 101.0, early_event)
        self._gwflow(16, 99.0, equal_event)

        queryset = visible_to_user(GWFlowJob.objects.all(), self.nonmember, "GWFlowJob")
        self.assertEqual(set(queryset.values_list("pk", flat=True)), expected)
        self.assertIn("LEFT OUTER JOIN", str(queryset.query).upper())

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_bilby_truth_table_taint_paths_and_simulation(self):
        from bilbyui.models import BilbyJob
        from bilbyui.utils.embargo import visible_to_user

        early_event = self._event(20, 99.0)
        equal_event = self._event(21, 100.0)
        early_parent = self._gwflow(20, 99.0, early_event)
        late_parent = self._gwflow(21, 100.0, early_event)
        tainted_parent_event = self._gwflow(22, 99.0, equal_event)

        expected = {
            self._bilby("all null").pk,
            self._bilby("all early", 99.0, early_event, early_parent).pk,
            self._bilby("partial null", None, early_event, early_parent).pk,
            self._bilby(
                "valid simulation",
                100.0,
                equal_event,
                late_parent,
                simulation_value="+1",
            ).pk,
        }
        self._bilby("own equal", 100.0, early_event, early_parent)
        self._bilby("own after", 101.0, early_event, early_parent)
        self._bilby("direct event taint", 99.0, equal_event, early_parent)
        self._bilby("parent trigger taint", 99.0, early_event, late_parent)
        self._bilby("parent event taint", 99.0, early_event, tainted_parent_event)

        for name, value in (
            ("missing simulation", None),
            ("zero simulation", "0"),
            ("invalid simulation", "invalid"),
        ):
            self._bilby(
                name,
                100.0,
                equal_event,
                late_parent,
                simulation_value=value,
            )

        actual = set(visible_to_user(BilbyJob.objects.all(), self.nonmember, "BilbyJob").values_list("pk", flat=True))
        self.assertEqual(actual, expected)

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_null_trigger_no_event_non_simulation_is_visible(self):
        from bilbyui.models import BilbyJob
        from bilbyui.utils.embargo import visible_to_user

        job = self._bilby("null regression")
        self.assertTrue(visible_to_user(BilbyJob.objects.all(), self.nonmember, "BilbyJob").filter(pk=job.pk).exists())

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_adapter_object_parity_and_legacy_flag_independence(self):
        from bilbyui.models import BilbyJob, EventID, GWFlowJob
        from bilbyui.utils.embargo import (
            is_record_public,
            is_simulated_value,
            visible_to_user,
        )

        public_event = self._event(30, 99.0)
        equal_event = self._event(31, 100.0)
        null_event = self._event(32, None)
        event_cases = (
            (public_event, True),
            (equal_event, False),
            (null_event, True),
        )
        event_pks = [record.pk for record, _ in event_cases]
        visible_event_ids = set(
            visible_to_user(
                EventID.objects.filter(pk__in=event_pks),
                self.nonmember,
                "EventID",
            ).values_list("pk", flat=True)
        )
        loaded_events = {record.pk: record for record in EventID.objects.filter(pk__in=event_pks)}
        with self.assertNumQueries(0):
            for record, expected in event_cases:
                queryset_result = record.pk in visible_event_ids
                self.assertEqual(queryset_result, expected)
                self.assertEqual(
                    queryset_result,
                    is_record_public(loaded_events[record.pk], self.nonmember),
                )

        public_parent = self._gwflow(30, 99.0, public_event)
        event_tainted_parent = self._gwflow(31, 99.0, equal_event)
        trigger_tainted_parent = self._gwflow(32, 100.0, public_event)
        unlinked_parent = self._gwflow(33, 99.0)
        all_null_parent = self._gwflow(34)
        gwflow_cases = (
            (public_parent, True),
            (event_tainted_parent, False),
            (trigger_tainted_parent, False),
            (unlinked_parent, True),
            (all_null_parent, True),
        )
        gwflow_pks = [record.pk for record, _ in gwflow_cases]
        visible_gwflow_ids = set(
            visible_to_user(
                GWFlowJob.objects.filter(pk__in=gwflow_pks),
                self.nonmember,
                "GWFlowJob",
            ).values_list("pk", flat=True)
        )
        loaded_gwflows = {
            record.pk: record for record in GWFlowJob.objects.filter(pk__in=gwflow_pks).select_related("event_id")
        }
        with self.assertNumQueries(0):
            for record, expected in gwflow_cases:
                queryset_result = record.pk in visible_gwflow_ids
                self.assertEqual(queryset_result, expected)
                self.assertEqual(
                    queryset_result,
                    is_record_public(loaded_gwflows[record.pk], self.nonmember),
                )

        bilby_cases = (
            (
                self._bilby(
                    "parity all early",
                    99.0,
                    public_event,
                    public_parent,
                ),
                None,
                True,
            ),
            (self._bilby("parity unlinked", 99.0), None, True),
            (self._bilby("parity all null"), None, True),
            (
                self._bilby(
                    "parity own equality",
                    100.0,
                    public_event,
                    public_parent,
                ),
                None,
                False,
            ),
            (
                self._bilby(
                    "parity direct event taint",
                    99.0,
                    equal_event,
                    public_parent,
                ),
                None,
                False,
            ),
            (
                self._bilby(
                    "parity parent trigger taint",
                    99.0,
                    public_event,
                    trigger_tainted_parent,
                ),
                None,
                False,
            ),
            (
                self._bilby(
                    "parity parent event taint",
                    99.0,
                    public_event,
                    event_tainted_parent,
                ),
                None,
                False,
            ),
            (
                self._bilby(
                    "parity partial null",
                    None,
                    public_event,
                    public_parent,
                ),
                None,
                True,
            ),
            (
                self._bilby(
                    "parity valid simulation",
                    100.0,
                    equal_event,
                    trigger_tainted_parent,
                    simulation_value=" +1 ",
                ),
                " +1 ",
                True,
            ),
            (
                self._bilby(
                    "parity missing simulation",
                    100.0,
                    equal_event,
                    trigger_tainted_parent,
                ),
                None,
                False,
            ),
            (
                self._bilby(
                    "parity zero simulation",
                    100.0,
                    equal_event,
                    trigger_tainted_parent,
                    simulation_value="0",
                ),
                "0",
                False,
            ),
            (
                self._bilby(
                    "parity invalid simulation",
                    100.0,
                    equal_event,
                    trigger_tainted_parent,
                    simulation_value="invalid",
                ),
                "invalid",
                False,
            ),
            (
                self._bilby(
                    "parity processed simulation",
                    100.0,
                    equal_event,
                    trigger_tainted_parent,
                    simulation_value="1",
                    simulation_processed=True,
                ),
                None,
                False,
            ),
        )
        bilby_pks = [record.pk for record, _, _ in bilby_cases]
        visible_bilby_ids = set(
            visible_to_user(
                BilbyJob.objects.filter(pk__in=bilby_pks),
                self.nonmember,
                "BilbyJob",
            ).values_list("pk", flat=True)
        )
        loaded_bilby = {
            record.pk: record
            for record in BilbyJob.objects.filter(pk__in=bilby_pks).select_related("event_id", "gwflow_job__event_id")
        }
        with self.assertNumQueries(0):
            for record, raw_simulation, expected in bilby_cases:
                queryset_result = record.pk in visible_bilby_ids
                self.assertEqual(queryset_result, expected)
                self.assertEqual(
                    queryset_result,
                    is_record_public(
                        loaded_bilby[record.pk],
                        self.nonmember,
                        is_simulation=is_simulated_value(raw_simulation),
                    ),
                )

    @override_settings(EMBARGO_START_TIME=None)
    def test_disabled_threshold_returns_same_queryset(self):
        from bilbyui.models import EventID
        from bilbyui.utils.embargo import visible_to_user

        queryset = EventID.objects.all()
        self.assertIs(
            visible_to_user(queryset, self.nonmember, "EventID"),
            queryset,
        )

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_exempt_user_returns_same_queryset(self):
        from bilbyui.models import EventID
        from bilbyui.utils.embargo import visible_to_user

        queryset = EventID.objects.all()
        self.assertIs(
            visible_to_user(queryset, self.member, "EventID"),
            queryset,
        )

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_unsupported_model_kind_raises(self):
        from bilbyui.models import EventID
        from bilbyui.utils.embargo import visible_to_user

        with self.assertRaises(ValueError):
            visible_to_user(
                EventID.objects.all(),
                self.nonmember,
                "Unsupported",
            )
