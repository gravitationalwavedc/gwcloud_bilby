from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBilbyTestCaseCreateUser(BilbyTestCase):
    def test_create_user_existing_with_kwargs(self):
        # The default user already exists via setUpClass; passing kwargs exercises
        # the setattr loop on the existing-user branch of create_user.
        user = self.create_user(id=1, is_staff=True)
        self.assertTrue(user.is_staff)
