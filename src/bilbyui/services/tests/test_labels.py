from bilbyui.models import Label
from bilbyui.services.labels import list_labels
from bilbyui.tests.testcases import BilbyTestCase


class TestLabelsService(BilbyTestCase):
    def test_list_labels_returns_all_seeded_labels(self):
        labels = list(list_labels().order_by("name").values_list("name", flat=True))
        expected = list(Label.all().order_by("name").values_list("name", flat=True))

        self.assertEqual(labels, expected)
        self.assertEqual(
            labels,
            [
                "Bad Run",
                "Official",
                "Production Run",
                "Review Requested",
                "Reviewed",
            ],
        )

    def test_list_labels_matches_label_all(self):
        self.assertQuerySetEqual(list_labels(), Label.all(), ordered=False)
