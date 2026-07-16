from bilbyui.tests.testcases import BilbyTestCase


class TestBilbyTestCaseHelper(BilbyTestCase):
    def test_create_user_extra_kwargs(self):
        user = self.create_user(id=1, is_staff=True)
        self.assertTrue(user.is_staff)

    def test_assert_response_has_no_errors_redirect(self):
        response = self.query("query { allLabels { edges { node { id } } } }")
        self.assertResponseHasNoErrors(response)

    def test_create_user_unique_email_for_new_id(self):
        user = self.create_user(id=50)
        self.assertEqual(user.primary_email, "user50@test.com")
