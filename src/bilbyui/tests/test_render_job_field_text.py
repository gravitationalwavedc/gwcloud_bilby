from types import SimpleNamespace

from django.test import RequestFactory

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _render_job_field_text


def _job(user_id=1, name="Test job", description="A description"):
    return SimpleNamespace(id=1, user_id=user_id, name=name, description=description)


class TestRenderJobFieldText(BilbyTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = self.create_user(id=1)

    def _request(self, user=None):
        request = self.factory.get("/")
        request.user = user or self.user
        return request

    def _context(self, **kwargs):
        response = _render_job_field_text(self._request(), _job(), **kwargs)
        return response.context_data

    def test_name_field_selects_job_name(self):
        context = self._context(field="name")
        self.assertEqual(context["field"], "name")
        self.assertEqual(context["value"], "Test job")

    def test_description_field_selects_job_description(self):
        context = self._context(field="description")
        self.assertEqual(context["field"], "description")
        self.assertEqual(context["value"], "A description")

    def test_editing_flag_passed_through(self):
        context = self._context(field="name", editing=True)
        self.assertTrue(context["editing"])

    def test_not_editing_by_default(self):
        context = self._context(field="name")
        self.assertFalse(context["editing"])

    def test_error_passed_through(self):
        context = self._context(field="name", error="Something went wrong")
        self.assertEqual(context["error"], "Something went wrong")

    def test_empty_error_by_default(self):
        context = self._context(field="name")
        self.assertEqual(context["error"], "")

    def test_modifiable_defaults_to_owner(self):
        context = self._context(field="name")
        self.assertTrue(context["modifiable"])

    def test_modifiable_defaults_to_false_for_non_owner(self):
        other = self.create_user(id=2)
        context = _render_job_field_text(self._request(user=other), _job(user_id=1), field="name").context_data
        self.assertFalse(context["modifiable"])

    def test_modifiable_override_respected(self):
        context = self._context(field="name", modifiable=False)
        self.assertFalse(context["modifiable"])

    def test_job_id_passed_through(self):
        context = self._context(field="name")
        self.assertEqual(context["job_id"], 1)

    def test_status_code_passed_through(self):
        response = _render_job_field_text(self._request(), _job(), field="name", status=400)
        self.assertEqual(response.status_code, 400)
