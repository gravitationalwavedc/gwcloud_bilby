"""Tests for the fail-closed HTMX declaration audit."""

from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from bilbyui.tests.testcases import BilbyTestCase

from .audit import (
    AuditError,
    extract_rendered,
    extract_source,
    extract_templates,
    reconcile,
    rendered_shapes,
)
from .registry import REGISTRY

TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "templates"


def contract(url_name):
    return SimpleNamespace(url_name=url_name)


class SourceExtractorTests(SimpleTestCase):
    def test_supported_dynamic_url_and_simple_variable(self):
        declarations = extract_source(
            """<button hx-get="{% url 'bilbyui:event_id_modal' job.id %}?q={{ query }}">x</button>""",
            "modal.html",
        )
        self.assertEqual(declarations[0].url_name, "bilbyui:event_id_modal")
        self.assertEqual(declarations[0].line, 1)

    def test_include_and_loop_context_are_retained(self):
        declarations = extract_source(
            """{% include "header.html" %}
{% for job in jobs %}
<a hx-get="{% url 'bilbyui:view_job' job.id %}">Job</a>
{% endfor %}""",
            "jobs.html",
        )
        self.assertTrue(any("{% include" in item for item in declarations[0].context))
        self.assertTrue(any("{% for" in item for item in declarations[0].context))

    def test_colon_qualified_attribute_is_supported(self):
        declaration = extract_source('<div hx-on:token-revoked="this.remove()"></div>', "token.html")[0]
        self.assertEqual(declaration.name, "hx-on:token-revoked")

    def test_unknown_attribute_fails_with_file_and_line(self):
        with self.assertRaisesRegex(AuditError, r"broken\.html:2: unknown HTMX attribute 'hx-frob'"):
            extract_source('\n<div hx-frob="yes"></div>', "broken.html")

    def test_unquoted_and_unsupported_dynamic_values_fail_closed(self):
        with self.assertRaisesRegex(AuditError, r"broken\.html:1: unsupported"):
            extract_source("<div hx-get={{ endpoint }}></div>", "broken.html")
        declaration = extract_source(
            '\n\n<div hx-target="{% if ready %}#yes{% endif %}"></div>',
            "broken.html",
        )[0]
        self.assertTrue(declaration.dynamic)


class RenderedExtractorTests(SimpleTestCase):
    def test_loop_elements_use_shape_and_cardinality_not_database_ids(self):
        rendered = extract_rendered(
            """
            <div id="jobs">
              <a hx-get="/jobs/41/" hx-target="#job-41">one</a>
              <a hx-get="/jobs/99/" hx-target="#job-99">two</a>
            </div>
            """,
            "/jobs/",
        )
        get_shapes = rendered_shapes([item for item in rendered if item.name == "hx-get"])
        self.assertEqual(sum(get_shapes.values()), 2)
        self.assertEqual(len(get_shapes), 1)

    def test_included_fragment_uses_route_and_nearest_stable_root(self):
        rendered = extract_rendered(
            '<section id="result"><div><button hx-post="/save/">Save</button></div></section>',
            "/fixture/",
        )
        post = next(item for item in rendered if item.name == "hx-post")
        self.assertEqual(post.route, "/fixture/")
        self.assertEqual(post.root, "#result")

    def test_boost_is_inherited_by_descendant_links(self):
        rendered = extract_rendered(
            '<main id="content" hx-boost="true"><nav><a href="/next/">Next</a></nav></main>',
            "/fixture/",
        )
        inherited = [item for item in rendered if item.name == "hx-boost" and item.tag == "a"]
        self.assertEqual(len(inherited), 1)
        self.assertTrue(inherited[0].effective_boost)

    def test_rendered_unknown_attribute_fails_closed(self):
        with self.assertRaisesRegex(AuditError, "rendered unknown HTMX"):
            extract_rendered('<div hx-made-up="x"></div>', "/fixture/")


class ReconciliationTests(SimpleTestCase):
    def test_request_maps_to_exactly_one_registry_entry(self):
        source = extract_source(
            "<button hx-get=\"{% url 'bilbyui:event_id_modal' %}\">Open</button>",
            "modal.html",
        )
        rendered = extract_rendered('<button hx-get="/jobs/event_id_modal/">Open</button>', "/fixture/")
        with self.assertRaisesRegex(AuditError, "maps to 0 registry entries"):
            reconcile(
                source,
                rendered,
                [contract("bilbyui:event_id_modal")],
            )

    def test_duplicate_registry_mapping_fails_closed(self):
        source = extract_source(
            "<button hx-post=\"{% url 'bilbyui:api_token_create' %}\">Create</button>",
            "token.html",
        )
        rendered = extract_rendered('<button hx-post="/synthetic/">Create</button>', "/fixture/")
        with self.assertRaisesRegex(AuditError, "2 registry entries"):
            reconcile(
                source,
                rendered,
                [
                    contract("bilbyui:api_token_create"),
                    contract("bilbyui:api_token_create"),
                ],
            )

    def test_requestless_declarations_receive_reasoned_exemptions(self):
        source = extract_source(
            '<div hx-boost="true" hx-indicator="#busy" hx-swap-oob="true"></div>',
            "fragment.html",
        )
        rendered = extract_rendered(
            '<div hx-boost="true" hx-indicator="#busy" hx-swap-oob="true"></div>',
            "/fixture/",
        )
        exemptions = reconcile(source, rendered, [], require_rendered=True)
        self.assertEqual(
            {item.name for item in exemptions},
            {"hx-boost", "hx-indicator", "hx-swap-oob"},
        )


class ProductionDeclarationAuditTests(BilbyTestCase):
    """Repository-wide source audit; HTTP fixtures are owned by task 4."""

    def test_full_template_surface_is_bounded_and_registered(self):
        declarations = extract_templates(TEMPLATE_ROOT)
        self.assertTrue(declarations)
        request_declarations = [item for item in declarations if item.name in {"hx-get", "hx-post"}]
        requestless = [item for item in declarations if item.name not in {"hx-get", "hx-post"}]
        exemptions = reconcile(
            request_declarations + requestless,
            [],
            REGISTRY,
            require_rendered=False,
        )
        self.assertTrue(exemptions)
