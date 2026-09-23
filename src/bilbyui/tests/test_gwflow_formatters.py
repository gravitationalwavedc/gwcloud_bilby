from datetime import datetime, timedelta, timezone

from django.template import Context, Engine
from django.test import SimpleTestCase
from django.utils.safestring import SafeString

from bilbyui.templatetags.gwflow_tags import (
    EMPTY_LIST,
    EMPTY_MAPPING,
    FORMATTERS,
    boolean,
    format_value,
    get_item,
    human_value,
    link,
    list_accessible,
    list_value,
    person,
    probability,
    scientific,
    sort_items,
    status,
    text,
    utc_timestamp,
)


class GwflowFormatterTests(SimpleTestCase):
    def test_text_none(self):
        self.assertEqual(text(None), "—")

    def test_text_false(self):
        self.assertEqual(text(False), "✗ False")

    def test_text_true(self):
        self.assertEqual(text(True), "✓ True")

    def test_text_zero(self):
        self.assertEqual(text(0), "0")

    def test_text_empty_string(self):
        self.assertEqual(text(""), '""')

    def test_text_empty_list(self):
        self.assertEqual(text([]), EMPTY_LIST)

    def test_text_empty_mapping(self):
        self.assertEqual(text({}), EMPTY_MAPPING)

    def test_utc_timestamp_converts_aware_values_and_adds_suffix(self):
        value = datetime(
            2026,
            8,
            21,
            0,
            32,
            tzinfo=timezone(timedelta(hours=10)),
        )
        self.assertEqual(utc_timestamp(value), "2026-08-20 14:32:00 UTC")
        self.assertEqual(
            utc_timestamp("2026-08-20T14:32:00Z"),
            "2026-08-20 14:32:00 UTC",
        )

    def test_utc_timestamp_identifies_malformed_and_naive_values(self):
        self.assertEqual(
            utc_timestamp("not-a-date"),
            "Invalid timestamp: not-a-date",
        )
        self.assertTrue(utc_timestamp("2026-08-20T14:32:00").startswith("Unknown timezone:"))
        self.assertEqual(utc_timestamp(None), "—")

    def test_person_name(self):
        self.assertEqual(person({"name": "Ada Lovelace"}), "Ada Lovelace")

    def test_person_display_name(self):
        self.assertEqual(
            person({"display_name": "Grace Hopper"}),
            "Grace Hopper",
        )

    def test_person_given_and_family_names(self):
        self.assertEqual(
            person(
                {
                    "givenName": "Katherine",
                    "familyName": "Johnson",
                }
            ),
            "Katherine Johnson",
        )

    def test_person_partial_name(self):
        self.assertEqual(
            person({"first_name": None, "last_name": "Ng"}),
            "Ng",
        )

    def test_person_email(self):
        self.assertEqual(
            person({"email": "researcher@example.test"}),
            "researcher@example.test",
        )

    def test_person_scalar(self):
        self.assertEqual(person("Single Name"), "Single Name")

    def test_boolean_formats_both_values_and_preserves_zero(self):
        self.assertEqual(boolean(True), "✓ True")
        self.assertEqual(boolean(False), "✗ False")
        self.assertEqual(boolean(0), "0")

    def test_probability_preserves_bounds_and_formats_decimal(self):
        self.assertEqual(probability(0), "0")
        self.assertEqual(probability(1), "1")
        self.assertEqual(probability(0.125), "0.125")

    def test_scientific_formats_small_negative_zero_and_units(self):
        self.assertEqual(scientific(3.1e-9, "Hz"), "3.1×10⁻⁹ Hz")
        self.assertEqual(scientific(-2.5e-4, "s"), "-2.5×10⁻⁴ s")
        self.assertEqual(scientific(0, "Hz"), "0 Hz")

    def test_list_short_long_empty_and_all_items_accessible(self):
        self.assertEqual(list_value(["H1", "L1"]), "H1, L1")
        self.assertEqual(
            list_value(["H1", "L1", "V1", "K1"], 2),
            "H1, L1, +2 more",
        )
        self.assertEqual(list_value([]), EMPTY_LIST)

        rendered = str(list_accessible(["H1", "L1", "V1", "K1"], 2))
        self.assertIn("H1, L1, +2 more", rendered)
        for item in ("H1", "L1", "V1", "K1"):
            self.assertIn(item, rendered)
        self.assertIn("All items:", rendered)

    def test_link_allows_only_http_and_https_and_escapes_values(self):
        safe = link(
            "https://example.test/?q=<script>",
            "Open <record>",
        )
        self.assertIsInstance(safe, SafeString)
        self.assertIn('rel="noopener noreferrer"', safe)
        self.assertIn('target="_blank"', safe)
        self.assertIn("&lt;script&gt;", safe)
        self.assertIn("Open &lt;record&gt;", safe)

        unsafe = link("javascript:alert(1)")
        self.assertEqual(unsafe, "javascript:alert(1)")
        template_output = (
            Engine(libraries={"gwflow_tags": ("bilbyui.templatetags.gwflow_tags")})
            .from_string("{% load gwflow_tags %}{% link value %}")
            .render(Context({"value": "<script>alert(1)</script>"}))
        )
        self.assertNotIn("<script>", template_output)
        self.assertIn("&lt;script&gt;", template_output)

    def test_status_maps_known_and_preserves_unknown(self):
        self.assertEqual(status("running"), "Running")
        self.assertEqual(status("science-review"), "science-review")

    def test_text_is_autoescaped_by_template_engine(self):
        output = (
            Engine(libraries={"gwflow_tags": ("bilbyui.templatetags.gwflow_tags")})
            .from_string("{% load gwflow_tags %}{{ value|text }}")
            .render(Context({"value": "<strong>unsafe</strong>"}))
        )
        self.assertEqual(
            output,
            "&lt;strong&gt;unsafe&lt;/strong&gt;",
        )

    def test_human_value_never_drops_mappings_or_falsy_values(self):
        self.assertEqual(
            human_value({"count": 0, "approved": False}),
            "count: 0, approved: ✗ False",
        )
        self.assertEqual(human_value(0), "0")
        self.assertEqual(human_value(False), "✗ False")
        self.assertEqual(human_value(""), '""')
        self.assertEqual(
            human_value([0, False, ""]),
            '0, ✗ False, ""',
        )

    def test_get_item_returns_value_for_existing_key(self):
        self.assertEqual(get_item({"name": "Ada Lovelace"}, "name"), "Ada Lovelace")

    def test_get_item_returns_none_for_missing_key(self):
        self.assertIsNone(get_item({"name": "Ada Lovelace"}, "missing"))

    def test_get_item_returns_none_for_non_dict(self):
        self.assertIsNone(get_item(["name"], "name"))
        self.assertIsNone(get_item("name", "name"))
        self.assertIsNone(get_item(None, "name"))

    def test_sort_items_sorts_dict_items(self):
        self.assertEqual(
            sort_items({"b": 2, "a": 1}),
            [("a", 1), ("b", 2)],
        )

    def test_sort_items_returns_empty_list_for_non_dict(self):
        self.assertEqual(sort_items(["b", "a"]), [])
        self.assertEqual(sort_items("ab"), [])
        self.assertEqual(sort_items(None), [])

    def test_formatter_dispatch_is_explicit_and_rejects_unknown_names(self):
        self.assertEqual(
            set(FORMATTERS),
            {
                "boolean",
                "link",
                "list",
                "person",
                "probability",
                "scientific",
                "status",
                "text",
                "utc_timestamp",
            },
        )
        self.assertEqual(format_value(0, "probability"), "0")
        with self.assertRaisesRegex(
            ValueError,
            "Unknown metadata formatter",
        ):
            format_value("value", "unknown")
