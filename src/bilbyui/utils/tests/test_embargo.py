from types import SimpleNamespace
from unittest import mock

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
    embargo_filter,
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


class TestEmbargoFilter(BilbyTestCase):
    def setUp(self):
        self.users = []
        for i in range(1, 5):
            self.users.append(self.create_user(id=i, name=f"user {i}", primary_email=f"user{i}@test.com"))

        for i, vals in enumerate([(1.0, 1), (2.0, 1), (1.0, 0), (2.0, 0)]):
            BilbyJob.objects.create(
                user_id=self.users[i].id,
                name=f"test job {i}",
                description=f"test job {i}",
                ini_string=create_test_ini_string(
                    {
                        "detectors": "['H1']",
                        "trigger-time": vals[0],
                        "n-simulation": vals[1],
                    }
                ),
            )

    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo(self):
        # If no embargo, filter returns input queryset
        input_qs = BilbyJob.objects.all()
        self.user = ADACSAnonymousUser()
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))

        self.user = self.create_user()
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))

        self.user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_with_embargo(self):
        # When embargo is in place, should modify a filter method to force it to return embargoed jobs
        # only for known, LIGO users
        input_qs = BilbyJob.objects.all()
        self.user = ADACSAnonymousUser()
        self.assertQuerySetEqual(
            BilbyJob.objects.filter(pk__in=[1, 2, 3]),
            embargo_filter(input_qs, self.user),
        )

        self.user = self.create_user()
        self.assertQuerySetEqual(
            BilbyJob.objects.filter(pk__in=[1, 2, 3]),
            embargo_filter(input_qs, self.user),
        )

        self.user.authentication_methods = [AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]]
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))


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

    def test_boolean_rejected(self):
        self.assertIsNone(resolve_job_trigger(None, SimpleNamespace(trigger_time=True)))
        self.assertIsNone(resolve_job_trigger(SimpleNamespace(trigger_time=False), None))

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
