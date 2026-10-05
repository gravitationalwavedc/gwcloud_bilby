from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.models import GWFlowJob
from bilbyui.schema import _visible_gwflow_job
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(EMBARGO_START_TIME=100.0)
class TestVisibleGWFlowJob(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()

    def _create_job(self, *, trigger_time=99.0, is_pruned=False):
        return GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.create_user(id=2),
            trigger_time=trigger_time,
            is_pruned=is_pruned,
        )

    def test_none_job_returns_none(self):
        self.assertIsNone(_visible_gwflow_job(None, self.user))

    def test_pruned_job_returns_none(self):
        job = self._create_job(is_pruned=True)
        self.assertIsNone(_visible_gwflow_job(job, self.user))

    def test_embargoed_job_hidden_from_non_ligo_user(self):
        job = self._create_job(trigger_time=100.0)
        non_ligo = self.create_user(id=3, authentication_method="password")
        self.assertIsNone(_visible_gwflow_job(job, non_ligo))

    def test_embargoed_job_visible_to_ligo_user(self):
        job = self._create_job(trigger_time=100.0)
        ligo = self.create_user(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        self.assertEqual(_visible_gwflow_job(job, ligo), job)

    def test_embargoed_job_hidden_from_anonymous_user(self):
        job = self._create_job(trigger_time=100.0)
        self.assertIsNone(_visible_gwflow_job(job, ADACSAnonymousUser()))

    def test_public_job_visible(self):
        job = self._create_job(trigger_time=99.0, is_pruned=False)
        self.assertEqual(_visible_gwflow_job(job, self.user), job)
