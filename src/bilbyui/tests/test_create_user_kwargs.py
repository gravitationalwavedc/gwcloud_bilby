from bilbyui.tests.testcases import BilbyTestCase


class TestCreateUserKwargs(BilbyTestCase):
    def test_create_user_extra_kwargs(self):
        user = self.create_user(id=1, is_ligo_member=True)
        self.assertTrue(user.is_ligo_member)
