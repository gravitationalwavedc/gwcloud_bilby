from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import BilbyJob, BilbyPermissionError
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


@override_settings(EMBARGO_START_TIME=None)
class TestGetById(BilbyTestCase):
    def setUp(self):
        self.ini_string = create_test_ini_string({"detectors": "['H1']"})
        self.user, _ = User.objects.update_or_create(
            id=1,
            defaults={"name": "buffy summers", "primary_email": "buffy@test.com"},
        )
        self.create_user(id=1)

    def _create_job(self, *, user_id=1, private=False, is_ligo_job=False, name=None):
        return BilbyJob.objects.create(
            user_id=user_id,
            name=name or f"job-{user_id}-{private}-{is_ligo_job}",
            private=private,
            is_ligo_job=is_ligo_job,
            ini_string=self.ini_string,
        )

    def test_anonymous_user_cannot_fetch_ligo_job(self):
        job = self._create_job(private=False, is_ligo_job=True, name="public-ligo")

        with self.assertRaises(BilbyPermissionError):
            BilbyJob.get_by_id(job.id, ADACSAnonymousUser())

    def test_non_ligo_user_cannot_fetch_ligo_job(self):
        self.authenticate()
        job = self._create_job(private=False, is_ligo_job=True, name="public-ligo")

        with self.assertRaises(BilbyPermissionError):
            BilbyJob.get_by_id(job.id, self.user)

    def test_ligo_user_can_fetch_ligo_job(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        job = self._create_job(private=False, is_ligo_job=True, name="public-ligo")

        self.assertEqual(BilbyJob.get_by_id(job.id, self.user), job)

    def test_non_ligo_user_can_fetch_own_non_ligo_job(self):
        self.authenticate()
        job = self._create_job(private=True, is_ligo_job=False, name="own-private")

        self.assertEqual(BilbyJob.get_by_id(job.id, self.user), job)
