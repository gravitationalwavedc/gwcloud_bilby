from django.template import Context, Template

from bilbyui.tests.testcases import BilbyTestCase


class GWFlowDiffRenderTagTestCase(BilbyTestCase):
    def render(self, value):
        source = "{% load gwflow_diff_render %}{% render_diff_value value %}"
        return Template(source).render(Context({"value": value}))

    def test_scalar_presence_values_are_distinct(self):
        cases = (
            (None, "Not provided"),
            (False, "No"),
            (True, "Yes"),
            (0, "0"),
            (0.0, "0"),
            ("", ""),
            ([], "(none)"),
        )

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.render(value), expected)

    def test_nested_dict_renders_recursive_definition_lists(self):
        rendered = self.render({"outer_label": {"inner_label": "value"}})

        self.assertEqual(
            rendered,
            "<dl><dt>Outer label</dt><dd><dl><dt>Inner label</dt><dd>value</dd></dl></dd></dl>",
        )

    def test_nested_mixed_list_dispatches_each_item_independently(self):
        rendered = self.render([{"answer": True}, ["text", None, 0], False])

        self.assertEqual(
            rendered,
            "<ul>"
            "<li><dl><dt>Answer</dt><dd>Yes</dd></dl></li>"
            "<li><ul><li>text</li><li>Not provided</li><li>0</li></ul></li>"
            "<li>No</li>"
            "</ul>",
        )

    def test_value_beyond_depth_six_uses_escaped_string_fallback(self):
        value = [[[[[[["<script>alert(1)</script>"]]]]]]]

        rendered = self.render(value)

        self.assertEqual(
            rendered,
            "<ul><li><ul><li><ul><li><ul><li><ul><li><ul><li>"
            "[&#x27;&lt;script&gt;alert(1)&lt;/script&gt;&#x27;]"
            "</li></ul></li></ul></li></ul></li></ul></li></ul></li></ul>",
        )
        self.assertNotIn("<script>", rendered)

    def test_hostile_markup_is_escaped_in_keys_and_all_value_positions(self):
        hostile = "<script>alert(1)</script>"
        rendered = self.render(
            {
                hostile: hostile,
                "nested": [hostile, {hostile: hostile}],
            },
        )

        self.assertNotIn("<script>", rendered)
        self.assertEqual(rendered.count("&lt;script&gt;"), 5)
        self.assertEqual(rendered.count("&lt;/script&gt;"), 5)
