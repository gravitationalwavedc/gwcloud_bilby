from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import BilbyJob, BilbyPermissionError, EventID, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


@override_settings(EMBARGO_START_TIME=100.0)
class TestBilbyJobFilter(BilbyTestCase):
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
        simulation=None,
        is_ligo_job=False,
        name=None,
    ):
        job = BilbyJob.objects.create(
            user_id=user_id,
            name=name or f"job-{BilbyJob.objects.count()}",
            private=private,
            trigger_time=trigger_time,
            event_id=event_id,
            is_ligo_job=is_ligo_job,
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

    def ids(self, qs):
        return set(qs.values_list("id", flat=True))

    def test_user_filter_rejects_anonymous_user(self):
        with self.assertRaises(BilbyPermissionError):
            BilbyJob.user_bilby_job_filter(
                BilbyJob.objects.all(),
                ADACSAnonymousUser(),
            )

    def test_user_filter_applies_owner_scope_before_visibility(self):
        self.authenticate()
        visible = self.create_job(private=True, trigger_time=99.0)
        self.create_job(private=True, trigger_time=100.0, name="embargoed")
        self.create_job(user_id=4, trigger_time=99.0, name="other-public")
        result = BilbyJob.user_bilby_job_filter(BilbyJob.objects.all(), self.user)
        self.assertEqual(self.ids(result), {visible.id})

    def test_public_filter_applies_public_scope_before_visibility(self):
        self.authenticate()
        visible = self.create_job(trigger_time=99.0)
        self.create_job(trigger_time=100.0, name="embargoed")
        self.create_job(private=True, trigger_time=99.0, name="private")
        result = BilbyJob.public_bilby_job_filter(BilbyJob.objects.all(), self.user)
        self.assertEqual(self.ids(result), {visible.id})

    def test_owner_or_public_scope_is_cumulative_with_visibility(self):
        self.authenticate()
        own = self.create_job(private=True, trigger_time=99.0)
        public = self.create_job(user_id=4, trigger_time=99.0, name="public")
        self.create_job(private=True, trigger_time=100.0, name="own-embargoed")
        self.create_job(user_id=4, private=True, trigger_time=99.0, name="other-private")
        result = BilbyJob.bilby_job_filter(BilbyJob.objects.all(), self.user)
        self.assertEqual(self.ids(result), {own.id, public.id})

    def test_ligo_member_does_not_bypass_private_scope(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        own = self.create_job(private=True, trigger_time=100.0)
        public = self.create_job(user_id=4, trigger_time=100.0, name="public")
        self.create_job(user_id=4, private=True, trigger_time=99.0, name="other-private")
        result = BilbyJob.bilby_job_filter(BilbyJob.objects.all(), self.user)
        self.assertEqual(self.ids(result), {own.id, public.id})

    def test_simulation_bypasses_only_embargo(self):
        self.authenticate()
        own = self.create_job(private=True, trigger_time=100.0, simulation="+2")
        public = self.create_job(
            user_id=4,
            trigger_time=100.0,
            simulation="1",
            name="public",
        )
        self.create_job(
            user_id=4,
            private=True,
            trigger_time=100.0,
            simulation="1",
            name="other-private",
        )
        result = BilbyJob.bilby_job_filter(BilbyJob.objects.all(), self.user)
        self.assertEqual(self.ids(result), {own.id, public.id})

    def test_direct_event_taint_applies_to_all_collection_filters(self):
        self.authenticate()
        event = EventID.objects.create(event_id="GW123456", gps_time=100.0)
        self.create_job(trigger_time=99.0, event_id=event)
        filters = (
            BilbyJob.user_bilby_job_filter(BilbyJob.objects.all(), self.user),
            BilbyJob.public_bilby_job_filter(BilbyJob.objects.all(), self.user),
            BilbyJob.bilby_job_filter(BilbyJob.objects.all(), self.user),
        )
        for result in filters:
            self.assertEqual(self.ids(result), set())

    def test_anonymous_scope_ignores_legacy_flag(self):
        visible = self.create_job(trigger_time=99.0, is_ligo_job=True)
        self.create_job(private=True, trigger_time=99.0, name="private")
        self.create_job(trigger_time=100.0, name="embargoed")
        result = BilbyJob.bilby_job_filter(
            BilbyJob.objects.all(),
            ADACSAnonymousUser(),
        )
        self.assertEqual(self.ids(result), {visible.id})
