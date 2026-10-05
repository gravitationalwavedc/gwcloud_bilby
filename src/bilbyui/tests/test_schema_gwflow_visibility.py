from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.models import EventID, GWFlowJob
from bilbyui.schema import _visible_gwflow_job
from bilbyui.tests.testcases import BilbyTestCase


class TestVisibleGWFlowJob(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()

    def _create_job(self, *, ligo_only=False, is_pruned=False):
        return GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.create_user(id=2),
            ligo_only=ligo_only,
            is_pruned=is_pruned,
        )

    def test_none_job_returns_none(self):
        self.assertIsNone(_visible_gwflow_job(None, self.user))

    def test_pruned_job_returns_none(self):
        job = self._create_job(is_pruned=True)
        self.assertIsNone(_visible_gwflow_job(job, self.user))

    def test_ligo_only_hidden_from_non_ligo_user(self):
        job = self._create_job(ligo_only=True)
        non_ligo = self.create_user(id=3, authentication_method="password")
        self.assertIsNone(_visible_gwflow_job(job, non_ligo))

    def test_ligo_only_visible_to_ligo_user(self):
        job = self._create_job(ligo_only=True)
        ligo = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assertIs(_visible_gwflow_job(job, ligo), job)

    def test_ligo_only_hidden_from_anonymous_user(self):
        job = self._create_job(ligo_only=True)
        self.assertIsNone(_visible_gwflow_job(job, ADACSAnonymousUser()))

    def test_normal_job_visible(self):
        job = self._create_job(ligo_only=False, is_pruned=False)
        self.assertIs(_visible_gwflow_job(job, self.user), job)

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_embargoed_trigger_time_hidden_from_non_ligo_user(self):
        event = EventID.objects.create(event_id="S230601ag", gps_time=1600.0)
        job = self._create_job(ligo_only=False, is_pruned=False)
        job.trigger_time = 1600.0
        job.event_id = event
        job.save()
        non_ligo = self.create_user(id=3, authentication_method="password")
        self.assertIsNone(_visible_gwflow_job(job, non_ligo))

    @override_settings(EMBARGO_START_TIME=1500.0)
    def test_embargoed_trigger_time_visible_to_ligo_user(self):
        event = EventID.objects.create(event_id="S230601ag", gps_time=1600.0)
        job = self._create_job(ligo_only=False, is_pruned=False)
        job.trigger_time = 1600.0
        job.event_id = event
        job.save()
        ligo = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assertIs(_visible_gwflow_job(job, ligo), job)
