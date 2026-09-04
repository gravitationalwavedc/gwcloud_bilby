from pathlib import Path

from django.template import Context, Template

from bilbyui.templatetags.frontend_tags import basename, parent_dir
from bilbyui.tests.testcases import BilbyTestCase


class TestBasenameFilter(BilbyTestCase):
    def test_deep_path_returns_text_after_last_slash(self):
        self.assertEqual(basename("/home/buffy/bilby/O3/GW150914/output/posteriors.h5"), "posteriors.h5")

    def test_slashless_string_returned_unchanged(self):
        self.assertEqual(basename("results.h5"), "results.h5")

    def test_trailing_slash_falls_back_to_full_value(self):
        self.assertEqual(basename("/a/b/data/"), "/a/b/data/")

    def test_empty_string_returned_unchanged(self):
        self.assertEqual(basename(""), "")

    def test_none_returns_empty_string(self):
        self.assertEqual(basename(None), "")

    def test_non_string_input_coerced_via_str(self):
        self.assertEqual(basename(42), "42")

    def test_filter_registered_in_template_engine(self):
        template = Template("{% load frontend_tags %}{{ value|basename }}")
        rendered = template.render(Context({"value": "/x/y/data.h5"}))
        self.assertEqual(rendered, "data.h5")


class TestParentDirFilter(BilbyTestCase):
    def test_deep_path_returns_text_before_last_slash(self):
        self.assertEqual(
            parent_dir("/home/buffy/bilby/O3/GW150914/output/posteriors.h5"),
            "/home/buffy/bilby/O3/GW150914/output",
        )

    def test_slashless_string_returns_empty(self):
        self.assertEqual(parent_dir("results.h5"), "")

    def test_trailing_slash_returns_head_without_trailing_slash(self):
        self.assertEqual(parent_dir("/a/b/data/"), "/a/b/data")

    def test_empty_string_returns_empty(self):
        self.assertEqual(parent_dir(""), "")

    def test_none_returns_empty_string(self):
        self.assertEqual(parent_dir(None), "")

    def test_non_string_input_coerced_via_str(self):
        self.assertEqual(parent_dir(Path("/a/b/data.h5")), "/a/b")

    def test_filter_registered_in_template_engine(self):
        template = Template("{% load frontend_tags %}{{ value|parent_dir }}")
        rendered = template.render(Context({"value": "/x/y/data.h5"}))
        self.assertEqual(rendered, "/x/y")
