from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob
from bilbyui.services.jobs import _apply_search_filter
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class ApplySearchFilterTestCase(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ini = create_test_ini_string({"detectors": "['H1']"})

    def setUp(self):
        self.authenticate()

    def _make_job(self, name, description):
        return BilbyJob.objects.create(
            user_id=self.user.id,
            name=name,
            description=description,
            ini_string=self.ini,
            job_type=BilbyJobType.NORMAL,
            job_controller_id=None,
        )

    def test_empty_search_returns_queryset_unchanged(self):
        qs = BilbyJob.objects.all()
        result = _apply_search_filter(qs, "")

        self.assertIs(result, qs)

    def test_search_filters_by_name(self):
        self._make_job("alpha", "unrelated")
        self._make_job("beta", "unrelated")

        qs = _apply_search_filter(BilbyJob.objects.all(), "alpha")

        names = set(qs.values_list("name", flat=True))
        self.assertEqual(names, {"alpha"})

    def test_search_filters_by_description(self):
        self._make_job("one", "contains needle")
        self._make_job("two", "does not")

        qs = _apply_search_filter(BilbyJob.objects.all(), "needle")

        names = set(qs.values_list("name", flat=True))
        self.assertEqual(names, {"one"})

    def test_search_matches_name_or_description(self):
        self._make_job("named", "unrelated")
        self._make_job("other", "described needle")
        self._make_job("third", "unrelated")

        qs = _apply_search_filter(BilbyJob.objects.all(), "needle")

        names = set(qs.values_list("name", flat=True))
        self.assertEqual(names, {"other"})
