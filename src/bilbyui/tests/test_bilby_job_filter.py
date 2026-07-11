from adacs_sso_plugin.anonymous_user import ADACSAnonymousUser
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


@override_settings(EMBARGO_START_TIME=None)
class TestBilbyJobFilter(BilbyTestCase):
    def setUp(self):
        self.ini_string = create_test_ini_string({"detectors": "['H1']"})
        self.other_user, _ = User.objects.update_or_create(
            id=4,
            defaults={"name": "Other User", "primary_email": "other@test.com"},
        )

    def _create_job(self, *, user_id=1, private=False, is_ligo_job=False, name=None):
        return BilbyJob.objects.create(
            user_id=user_id,
            name=name or f"job-{user_id}-{private}-{is_ligo_job}",
            private=private,
            is_ligo_job=is_ligo_job,
            ini_string=self.ini_string,
        )

    def _filtered_ids(self, user):
        return set(BilbyJob.bilby_job_filter(BilbyJob.objects.all(), user).values_list("id", flat=True))

    def test_anonymous_user_sees_only_public_non_ligo_jobs(self):
        visible = self._create_job(private=False, is_ligo_job=False, name="public-non-ligo")
        self._create_job(private=True, is_ligo_job=False, name="private-non-ligo")
        self._create_job(private=False, is_ligo_job=True, name="public-ligo")
        other_public = self._create_job(user_id=4, private=False, is_ligo_job=False, name="other-public")

        anonymous = ADACSAnonymousUser()
        self.assertEqual(self._filtered_ids(anonymous), {visible.id, other_public.id})

    def test_non_ligo_user_sees_own_and_public_non_ligo_jobs(self):
        self.authenticate()
        own_private = self._create_job(private=True, is_ligo_job=False, name="own-private")
        own_public = self._create_job(private=False, is_ligo_job=False, name="own-public")
        other_public = self._create_job(user_id=4, private=False, is_ligo_job=False, name="other-public")
        self._create_job(user_id=4, private=True, is_ligo_job=False, name="other-private")
        self._create_job(private=False, is_ligo_job=True, name="public-ligo")
        self._create_job(private=True, is_ligo_job=True, name="private-ligo")

        self.assertEqual(
            self._filtered_ids(self.user),
            {own_private.id, own_public.id, other_public.id},
        )

    def test_ligo_user_sees_own_jobs_and_all_public_jobs(self):
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
        own_private_ligo = self._create_job(private=True, is_ligo_job=True, name="own-private-ligo")
        own_public = self._create_job(private=False, is_ligo_job=False, name="own-public")
        other_public_ligo = self._create_job(user_id=4, private=False, is_ligo_job=True, name="other-public-ligo")
        self._create_job(user_id=4, private=True, is_ligo_job=False, name="other-private")

        self.assertEqual(
            self._filtered_ids(self.user),
            {own_private_ligo.id, own_public.id, other_public_ligo.id},
        )
