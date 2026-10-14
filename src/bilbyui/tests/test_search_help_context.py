from django.test import SimpleTestCase

from bilbyui.services.search_help import build_search_help, casing_hint_eligible


class TestSearchHelpContext(SimpleTestCase):
    def test_builder_returns_four_common_fields_and_grouped_fields(self):
        for surface in ("gwflow", "bilby"):
            with self.subTest(surface=surface):
                context = build_search_help(surface)
                self.assertEqual(len(context["common"]), 4)
                self.assertIsInstance(context["groups"], list)
                self.assertTrue(context["groups"])

    def test_builder_returns_surface_specific_placeholders(self):
        self.assertEqual(
            build_search_help("gwflow")["placeholder"],
            "Try sname:S2306*",
        )
        self.assertEqual(
            build_search_help("bilby")["placeholder"],
            "Try job.name:GW150914*",
        )

    def test_builder_returns_locked_surface_examples(self):
        self.assertEqual(
            build_search_help("gwflow")["examples"],
            [
                "sname:S2306*",
                "review_statuses:pass",
                "snr:>10",
            ],
        )
        self.assertEqual(
            build_search_help("bilby")["examples"],
            [
                "job.name:GW150914*",
                "params.waveform_approximant:IMRPhenomXPHM",
                "eventId.eventId:GW150914*",
            ],
        )

    def test_casing_hint_eligibility_truth_table(self):
        cases = (
            ("", 0, False),
            ("sname:S2306*", 3, False),
            ("S2306", 0, False),
            ("sname:S2306*", 0, True),
        )
        for search, result_count, expected in cases:
            with self.subTest(search=search, result_count=result_count):
                self.assertEqual(
                    casing_hint_eligible(search, result_count),
                    expected,
                )
