from django.test import override_settings

from bilbyui.tests.test_utils import create_test_ini_string
from gw_bilby.jwt_tools import GWCloudUser

from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.embargo import user_subject_to_embargo, should_embargo_job, embargo_filter


class TestUserSubjectToEmbargo(BilbyTestCase):
    def setUp(self):
        self.user = GWCloudUser(username="buffy")

    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo(self):
        # If no embargo, no users embargoed
        self.user.is_anonymous = True
        self.user.is_ligo = False
        self.assertFalse(user_subject_to_embargo(self.user))

        self.user.is_ligo = True
        self.assertFalse(user_subject_to_embargo(self.user))

        self.user.is_anonymous = False
        self.user.is_ligo = False
        self.assertFalse(user_subject_to_embargo(self.user))

        self.user.is_ligo = True
        self.assertFalse(user_subject_to_embargo(self.user))

    @override_settings(EMBARGO_START_TIME=1)
    def test_with_embargo(self):
        # User is only exempt from embargo if they are a LIGO user
        self.user.is_anonymous = True
        self.user.is_ligo = False
        self.assertTrue(user_subject_to_embargo(self.user))

        self.user.is_ligo = True
        self.assertTrue(user_subject_to_embargo(self.user))

        self.user.is_anonymous = False
        self.user.is_ligo = False
        self.assertTrue(user_subject_to_embargo(self.user))

        self.user.is_ligo = True
        self.assertFalse(user_subject_to_embargo(self.user))


class TestShouldEmbargoJob(BilbyTestCase):
    def setUp(self):
        self.user = GWCloudUser(username="buffy")

    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo(self):
        # If no embargo, no jobs embargoed
        self.user.is_anonymous = True
        self.user.is_ligo = False
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.is_ligo = True
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.is_anonymous = False
        self.user.is_ligo = False
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.is_ligo = True
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_with_embargo(self):
        # Jobs should be embargoed is the trigger time is later than EMBARGO_START_TIME,
        # the job is run on real data, and the user is not a LIGO user
        self.user.is_anonymous = True
        self.user.is_ligo = False
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, 2.0, True))
        self.assertTrue(should_embargo_job(self.user, 2.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.is_ligo = True
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, 2.0, True))
        self.assertTrue(should_embargo_job(self.user, 2.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.is_anonymous = False
        self.user.is_ligo = False
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, 2.0, True))
        self.assertTrue(should_embargo_job(self.user, 2.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))

        self.user.is_ligo = True
        self.assertFalse(should_embargo_job(self.user, 1.0, True))
        self.assertFalse(should_embargo_job(self.user, 1.0, False))
        self.assertFalse(should_embargo_job(self.user, 2.0, True))
        self.assertFalse(should_embargo_job(self.user, 2.0, False))
        self.assertFalse(should_embargo_job(self.user, None, True))
        self.assertFalse(should_embargo_job(self.user, None, False))


class TestEmbargoFilter(BilbyTestCase):
    def setUp(self):
        for i, vals in enumerate([(1.0, 1), (2.0, 1), (1.0, 0), (2.0, 0)]):
            BilbyJob.objects.create(
                user_id=i,
                name=f"test job {i}",
                description=f"test job {i}",
                ini_string=create_test_ini_string(
                    {"detectors": "['H1']", "trigger-time": vals[0], "n-simulation": vals[1]}
                ),
            )

        self.user = GWCloudUser(username="buffy")

    @override_settings(EMBARGO_START_TIME=None)
    def test_no_embargo(self):
        # If no embargo, filter returns input queryset
        input_qs = BilbyJob.objects.all()
        self.user.is_anonymous = True
        self.user.is_ligo = False
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))

        self.user.is_ligo = True
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))

        self.user.is_anonymous = False
        self.user.is_ligo = False
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))

        self.user.is_ligo = True
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))

    @override_settings(EMBARGO_START_TIME=1.5)
    def test_with_embargo(self):
        # When embargo is in place, should modify a filter method to force it to return embargoed jobs
        # only for known, LIGO users
        input_qs = BilbyJob.objects.all()
        self.user.is_anonymous = True
        self.user.is_ligo = False
        self.assertQuerySetEqual(
            BilbyJob.objects.filter(pk__in=[1, 2, 3]), embargo_filter(input_qs, self.user)
        )

        self.user.is_ligo = True
        self.assertQuerySetEqual(
            BilbyJob.objects.filter(pk__in=[1, 2, 3]), embargo_filter(input_qs, self.user)
        )

        self.user.is_anonymous = False
        self.user.is_ligo = False
        self.assertQuerySetEqual(
            BilbyJob.objects.filter(pk__in=[1, 2, 3]), embargo_filter(input_qs, self.user)
        )

        self.user.is_ligo = True
        self.assertQuerySetEqual(input_qs, embargo_filter(input_qs, self.user))
