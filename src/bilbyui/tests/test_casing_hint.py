from django.template.loader import render_to_string

from bilbyui.tests.testcases import BilbyTestCase

HINT_TEXT = "Field names are case-sensitive. Check the supported field reference."
FRAGMENTS = (
    "bilbyui/_gwflow_job_list_fragment.html",
    "bilbyui/_job_list_fragment.html",
)


class CasingHintTemplateTests(BilbyTestCase):
    def render_fragment(self, template_name, *, eligible, total, search):
        return render_to_string(
            template_name,
            {
                "casing_hint_eligible": eligible,
                "service_state": "ok",
                "total": total,
                "search": search,
                "jobs": [],
                "superevents": [],
                "object_list": [],
            },
        )

    def test_hint_present_for_eligible_zero_result_fielded_search(self):
        for template_name in FRAGMENTS:
            with self.subTest(template_name=template_name):
                rendered = self.render_fragment(template_name, eligible=True, total=0, search="status:complete")
                self.assertIn(HINT_TEXT, rendered)

    def test_hint_absent_for_empty_search(self):
        for template_name in FRAGMENTS:
            with self.subTest(template_name=template_name):
                rendered = self.render_fragment(template_name, eligible=False, total=0, search="")
                self.assertNotIn(HINT_TEXT, rendered)

    def test_hint_absent_for_non_zero_result_set(self):
        for template_name in FRAGMENTS:
            with self.subTest(template_name=template_name):
                rendered = self.render_fragment(template_name, eligible=False, total=1, search="status:complete")
                self.assertNotIn(HINT_TEXT, rendered)
