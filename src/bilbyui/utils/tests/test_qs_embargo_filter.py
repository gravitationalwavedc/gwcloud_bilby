from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import BilbyJob, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import qs_embargo_filter

User = get_user_model()


class TestQsEmbargoFilter(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user(id=1, name="test user", primary_email="test@test.com")

    def _create_job(self, name, trigger_time=None, n_simulation=None):
        """Create a BilbyJob with optional IniKeyValue entries."""
        ini_config = {"detectors": "['H1']"}
        if trigger_time is not None:
            ini_config["trigger-time"] = trigger_time
        if n_simulation is not None:
            ini_config["n-simulation"] = n_simulation

        return BilbyJob.objects.create(
            user_id=self.user.id,
            name=name,
            description=name,
            ini_string=create_test_ini_string(ini_config),
        )

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_trigger_time_below_embargo(self):
        """Jobs with trigger_time < EMBARGO_START_TIME should be included."""
        self._create_job("early job", trigger_time=3.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "early job")

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_trigger_time_above_embargo(self):
        """Jobs with trigger_time >= EMBARGO_START_TIME should be excluded."""
        self._create_job("late job", trigger_time=7.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_trigger_time_equal_to_embargo(self):
        """Jobs with trigger_time == EMBARGO_START_TIME should be excluded."""
        self._create_job("boundary job", trigger_time=5.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_simulated_job_included(self):
        """Simulated jobs (n_simulation > 0) should always be included."""
        self._create_job("sim job", trigger_time=10.0, n_simulation=1)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "sim job")

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_non_simulated_late_job_excluded(self):
        """Non-simulated job with trigger_time >= EMBARGO_START_TIME should be excluded."""
        self._create_job("real late job", trigger_time=10.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_simulated_job_without_trigger_time(self):
        """Simulated job without trigger_time should still be included."""
        self._create_job("sim no trigger", n_simulation=1)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "sim no trigger")

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_mixed_jobs(self):
        """Test multiple jobs with different trigger times and simulation status."""
        self._create_job("early real", trigger_time=1.0, n_simulation=0)
        self._create_job("late real", trigger_time=10.0, n_simulation=0)
        self._create_job("early sim", trigger_time=1.0, n_simulation=1)
        self._create_job("late sim", trigger_time=10.0, n_simulation=1)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        # early real (trigger_time=1.0 < 5.0) and both sim jobs (simulated > 0) should be included
        # late real (trigger_time=10.0 >= 5.0, not simulated) should be excluded
        self.assertEqual(result.count(), 3)
        names = set(result.values_list("name", flat=True))
        self.assertEqual(names, {"early real", "early sim", "late sim"})

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_no_embargo_setting(self):
        """When EMBARGO_START_TIME is high enough, all jobs should be included."""
        self._create_job("job 1", trigger_time=1.0, n_simulation=0)
        self._create_job("job 2", trigger_time=3.0, n_simulation=0)

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 2)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_empty_queryset(self):
        """Empty queryset should return empty result."""
        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 0)

    @override_settings(EMBARGO_START_TIME=5.0)
    def test_job_with_processed_trigger_time(self):
        """Only processed IniKeyValue entries should be considered for trigger_time."""
        job = self._create_job("processed trigger", trigger_time=1.0, n_simulation=0)

        # Add an unprocessed trigger_time entry that should be ignored
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value="99.0",
            index=1,
            processed=False,
        )

        qs = BilbyJob.objects.all()
        result = qs_embargo_filter(qs)

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().name, "processed trigger")


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
            trigger_time=trigger_time,
            event_id=event,
            gwflow_job=gwflow,
        )
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
        public_event.is_ligo_event = True
        EventID.objects.filter(pk=public_event.pk).update(is_ligo_event=True)

        equal_event = self._event(31, 100.0)
        equal_event.is_ligo_event = False
        EventID.objects.filter(pk=equal_event.pk).update(is_ligo_event=False)

        null_event = self._event(32, None)
        null_event.is_ligo_event = True
        EventID.objects.filter(pk=null_event.pk).update(is_ligo_event=True)

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
        public_parent.ligo_only = True
        GWFlowJob.objects.filter(pk=public_parent.pk).update(ligo_only=True)

        event_tainted_parent = self._gwflow(31, 99.0, equal_event)
        event_tainted_parent.ligo_only = False
        GWFlowJob.objects.filter(pk=event_tainted_parent.pk).update(ligo_only=False)

        trigger_tainted_parent = self._gwflow(32, 100.0, public_event)
        trigger_tainted_parent.ligo_only = False
        GWFlowJob.objects.filter(pk=trigger_tainted_parent.pk).update(ligo_only=False)

        unlinked_parent = self._gwflow(33, 99.0)
        unlinked_parent.ligo_only = True
        GWFlowJob.objects.filter(pk=unlinked_parent.pk).update(ligo_only=True)

        all_null_parent = self._gwflow(34)
        all_null_parent.ligo_only = True
        GWFlowJob.objects.filter(pk=all_null_parent.pk).update(ligo_only=True)

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
        for record, _, expected in bilby_cases:
            record.is_ligo_job = not expected
            BilbyJob.objects.filter(pk=record.pk).update(is_ligo_job=record.is_ligo_job)

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
