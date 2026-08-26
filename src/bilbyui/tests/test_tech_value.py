import re

from django.template import Context, Template
from django.template.loader import get_template

from bilbyui.tests.testcases import BilbyTestCase

WHITESPACE = re.compile(r"\s+")

DEEP_PATH = "/home/buffy/bilby/O3/GW150914/output/posteriors.h5"

COPY_ONCLICK = (
    "var r = this.closest('.tech-value'); "
    "navigator.clipboard.writeText(r.querySelector('.tech-value-full').textContent); "
    "r.querySelector('.tech-value-status').textContent = 'Copied';"
)
TOGGLE_ONCLICK = (
    "var r = this.closest('.tech-value'); var f = r.querySelector('.tech-value-full'); "
    "f.hidden = !f.hidden; "
    "this.setAttribute('aria-expanded', f.hidden ? 'false' : 'true');"
)


def normalise(html):
    return WHITESPACE.sub(" ", html).strip()


class TechValueRenderTestMixin:
    def render_tech_value(self, **context):
        return get_template("bilbyui/_tech_value.html").render(context)

    def label_of(self, html):
        match = re.search(r'<span class="tech-value-label">(.*?)</span>', normalise(html))
        self.assertIsNotNone(match, f"no tech-value-label in output: {html!r}")
        return match.group(1)


class TestTechValuePathKind(TechValueRenderTestMixin, BilbyTestCase):
    def test_basename_default_primary_label(self):
        html = self.render_tech_value(value=DEEP_PATH)
        self.assertEqual(self.label_of(html), "posteriors.h5")
        self.assertIn('<span class="tech-value">', html)

    def test_default_copy_button_visible_text_and_handler(self):
        html = normalise(self.render_tech_value(value=DEEP_PATH))
        self.assertIn('class="tech-value-copy"', html)
        self.assertIn(f'onclick="{COPY_ONCLICK}"', html)
        self.assertIn('<i class="bi-clipboard" aria-hidden="true"></i> Copy path </button>', html)

    def test_disclosure_button_initially_collapsed_with_path_hint(self):
        html = normalise(self.render_tech_value(value=DEEP_PATH))
        self.assertIn('class="tech-value-toggle" aria-expanded="false"', html)
        self.assertIn(f'onclick="{TOGGLE_ONCLICK}"', html)
        self.assertIn('<span class="sr-only">Show full path</span>', html)

    def test_full_value_rendered_server_side_in_hidden_block(self):
        html = normalise(self.render_tech_value(value=DEEP_PATH))
        self.assertIn(f'<span class="tech-value-full" hidden>{DEEP_PATH}</span>', html)

    def test_empty_status_region_present_after_full_value(self):
        html = normalise(self.render_tech_value(value=DEEP_PATH))
        self.assertIn(
            f'<span class="tech-value-full" hidden>{DEEP_PATH}</span>'
            '<span class="tech-value-status" role="status"></span>',
            html,
        )

    def test_no_element_ids_emitted(self):
        html = self.render_tech_value(value=DEEP_PATH)
        self.assertNotIn('id="', html)

    def test_custom_primary_and_copy_label_override_defaults(self):
        html = normalise(self.render_tech_value(value=DEEP_PATH, primary="posteriors", copy_label="Copy file"))
        self.assertEqual(self.label_of(html), "posteriors")
        self.assertNotIn("Copy path", html)
        self.assertIn(" Copy file </button>", html)

    def test_trailing_slash_falls_back_to_full_value_label(self):
        html = self.render_tech_value(value="/a/b/data/")
        self.assertEqual(self.label_of(html), "/a/b/data/")

    def test_slashless_path_uses_whole_value_as_label(self):
        html = self.render_tech_value(value="results.h5")
        self.assertEqual(self.label_of(html), "results.h5")


class TestTechValueTruncated(TechValueRenderTestMixin, BilbyTestCase):
    def test_truncated_adds_modifier_class_and_ellipsis_marker(self):
        html = normalise(self.render_tech_value(value=DEEP_PATH, truncated=True))
        self.assertIn('<span class="tech-value tech-value--truncated">', html)
        self.assertIn('<span class="tech-value-ellipsis" aria-hidden="true">…</span>', html)

    def test_not_truncated_omits_modifier_and_marker(self):
        html = self.render_tech_value(value=DEEP_PATH)
        self.assertNotIn("tech-value--truncated", html)
        self.assertNotIn("tech-value-ellipsis", html)


class TestTechValueIdKind(TechValueRenderTestMixin, BilbyTestCase):
    def test_root_has_id_modifier_class(self):
        html = self.render_tech_value(value="S230518h", kind="id")
        self.assertIn('<span class="tech-value tech-value--id">', html)

    def test_default_primary_label_is_the_raw_value(self):
        html = self.render_tech_value(value="S230518h", kind="id")
        self.assertEqual(self.label_of(html), "S230518h")

    def test_id_kind_keeps_slashed_value_whole_as_label(self):
        html = self.render_tech_value(value="sha256:a1b2/c3d4", kind="id")
        self.assertEqual(self.label_of(html), "sha256:a1b2/c3d4")

    def test_id_kind_default_copy_label_and_toggle_hint(self):
        html = normalise(self.render_tech_value(value="S230518h", kind="id"))
        self.assertIn(" Copy identifier </button>", html)
        self.assertIn('<span class="sr-only">Show full identifier</span>', html)


class TestTechValueEscaping(TechValueRenderTestMixin, BilbyTestCase):
    def test_hostile_script_tag_rendered_escaped(self):
        hostile = '<script>alert("x")'
        html = self.render_tech_value(value=hostile)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertEqual(self.label_of(html), "&lt;script&gt;alert(&quot;x&quot;)")
        self.assertIn(
            '<span class="tech-value-full" hidden>&lt;script&gt;alert(&quot;x&quot;)</span>',
            normalise(html),
        )

    def test_hostile_closing_tag_slash_escaped_and_peel_safe(self):
        html = self.render_tech_value(value="<script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertNotIn("</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn(
            '<span class="tech-value-full" hidden>&lt;script&gt;alert(1)&lt;/script&gt;</span>',
            normalise(html),
        )
        self.assertEqual(self.label_of(html), "script&gt;")

    def test_hostile_slashed_path_rendered_escaped(self):
        html = self.render_tech_value(value="<script>alert(1)</script>/tmp/pw.h5")
        self.assertNotIn("<script>", html)
        self.assertEqual(self.label_of(html), "pw.h5")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;/tmp/pw.h5", normalise(html))

    def test_quotes_in_value_do_not_break_inline_handlers(self):
        value = '/a/b/it\'s "the" one.h5'
        html = normalise(self.render_tech_value(value=value))
        self.assertIn(f'onclick="{COPY_ONCLICK}"', html)
        self.assertIn(f'onclick="{TOGGLE_ONCLICK}"', html)
        self.assertIn("&#x27;", html)
        self.assertIn("&quot;the&quot;", html)
        self.assertNotIn('"the"', html)
        self.assertEqual(self.label_of(html), "it&#x27;s &quot;the&quot; one.h5")


class TestTechValueIncludeSignature(TechValueRenderTestMixin, BilbyTestCase):
    def test_contract_include_signature_renders_default_path_variant(self):
        template = Template('{% include "bilbyui/_tech_value.html" with value=value %}')
        html = template.render(Context({"value": "/x/y/data.h5"}))
        self.assertEqual(self.label_of(html), "data.h5")
        self.assertIn("Copy path", html)
        self.assertIn('aria-expanded="false"', html)

    def test_contract_include_signature_passes_optional_params(self):
        template = Template(
            '{% include "bilbyui/_tech_value.html" '
            'with value=value primary="run01" kind="id" copy_label="Copy run" truncated=True %}'
        )
        html = normalise(template.render(Context({"value": "GW150914/run01"})))
        self.assertEqual(self.label_of(html), "run01")
        self.assertIn('<span class="tech-value tech-value--id tech-value--truncated">', html)
        self.assertIn(" Copy run </button>", html)
        self.assertIn('<span class="sr-only">Show full identifier</span>', html)
