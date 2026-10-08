from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


@override_settings(EMBARGO_START_TIME=100.0)
class TestGetById(BilbyTestCase):
    def setUp(self):
        self.ini_string = create_test_ini_string({"detectors": "['H1']"})
        self.user, _ = User.objects.update_or_create(
            id=1,
            defaults={"name": "buffy summers", "primary_email": "buffy@test.com"},
        )
        self.other_user, _ = User.objects.update_or_create(
            id=4,
            defaults={"name": "Other User", "primary_email": "other@test.com"},
        )
        self.create_user(id=1)

    def create_job(
        self,
        *,
        user_id=1,
        private=False,
        trigger_time=None,
        event_id=None,
        gwflow_job=None,
        simulation=None,
        name=None,
    ):
        job = BilbyJob.objects.create(
            user_id=user_id,
            name=name or f"job-{BilbyJob.objects.count()}",
            private=private,
            trigger_time=trigger_time,
            event_id=event_id,
            gwflow_job=gwflow_job,
            ini_string=self.ini_string,
        )
        if trigger_time is not None:
            BilbyJob.objects.filter(pk=job.pk).update(trigger_time=trigger_time)
            job.trigger_time = trigger_time
        IniKeyValue.objects.filter(
            job=job,
            key="n_simulation",
            processed=False,
        ).delete()
        if simulation is not None:
            IniKeyValue.objects.create(
                job=job,
                key="n_simulation",
                value=simulation,
                index=0,
                processed=False,
            )
        return job

    def assert_denied(self, job, user=None):
        with self.assertRaises(BilbyJob.DoesNotExist):
            BilbyJob.get_by_id(job.id, user or self.user)

    def test_legacy_flag_is_not_an_access_decision(self):
        self.authenticate()
        job = self.create_job()
        self.assertEqual(BilbyJob.get_by_id(job.id, self.user), job)

    def test_non_ligo_owner_cannot_access_private_embargoed_job(self):
        self.authenticate()
        self.assert_denied(self.create_job(private=True, trigger_time=100.0))

    def test_ligo_member_cannot_access_another_users_private_job(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assert_denied(
            self.create_job(user_id=4, private=True, trigger_time=101.0),
        )

    def test_simulation_bypasses_embargo_but_not_private_ownership(self):
        self.authenticate()
        own = self.create_job(private=True, trigger_time=100.0, simulation="1")
        other = self.create_job(
            user_id=4,
            private=True,
            trigger_time=100.0,
            simulation="+2",
        )
        self.assertEqual(BilbyJob.get_by_id(own.id, self.user), own)
        self.assert_denied(other)

    def test_missing_invalid_and_zero_simulation_do_not_bypass(self):
        self.authenticate()
        for index, simulation in enumerate((None, "invalid", "0")):
            with self.subTest(simulation=simulation):
                self.assert_denied(
                    self.create_job(
                        trigger_time=100.0,
                        simulation=simulation,
                        name=f"real-{index}",
                    )
                )

    def test_direct_event_at_threshold_taints_below_threshold_job(self):
        self.authenticate()
        event = EventID.objects.create(event_id="GW123456", gps_time=100.0)
        self.assert_denied(self.create_job(trigger_time=99.0, event_id=event))

    def test_gwflow_parent_at_threshold_taints_below_threshold_job(self):
        self.authenticate()
        parent = GWFlowJob.objects.create(
            sname="S123456a",
            user=self.other_user,
            trigger_time=100.0,
        )
        self.assert_denied(self.create_job(trigger_time=99.0, gwflow_job=parent))

    def test_gwflow_parent_event_taints_below_threshold_job(self):
        self.authenticate()
        event = EventID.objects.create(event_id="GW123457", gps_time=101.0)
        parent = GWFlowJob.objects.create(
            sname="S123457a",
            user=self.other_user,
            trigger_time=99.0,
            event_id=event,
        )
        self.assert_denied(self.create_job(trigger_time=99.0, gwflow_job=parent))

    def test_ligo_member_can_access_public_embargoed_job(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        job = self.create_job(trigger_time=100.0)
        self.assertEqual(BilbyJob.get_by_id(job.id, self.user), job)

    def test_malformed_id_raises_does_not_exist(self):
        self.authenticate()
        with self.assertRaises(BilbyJob.DoesNotExist):
            BilbyJob.get_by_id("not-an-int", self.user)

    def test_anonymous_user_cannot_access_private_job(self):
        self.assert_denied(self.create_job(private=True), ADACSAnonymousUser())
