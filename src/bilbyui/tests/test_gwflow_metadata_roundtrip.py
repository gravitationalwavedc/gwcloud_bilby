import copy
import json
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import (
    FIELD_REGISTRY,
    KNOWN_KEYS,
    RECOGNISED_NON_DISPLAYED_PATHS,
    _reset_unmapped_warning_cache,
    build_metadata_presentation,
    warn_unmapped_metadata_leaves,
)
from bilbyui.templatetags.gwflow_tags import format_value

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "metadata_corpus"
VALID_FIXTURES = (
    "complete_curated.json",
    "absent_optional_highlights.json",
    "historical_curated.json",
)
NON_DISPLAYED = RECOGNISED_NON_DISPLAYED_PATHS
CATCH_ALL = frozenset({"detector_configurations[]", "catalog_connections[]"})
EXPECTED_UNKNOWN_EXTENSIONS = frozenset({"future_section.unsafe"})
NULLABLE_REGISTERED_CONTAINERS = {
    "analyses[].software": (
        "analyses[].software.name",
        "analyses[].software.version",
    ),
}
FORMATTER_BY_PATH = {field.key: field.formatter for fields in FIELD_REGISTRY.values() for field in fields}


class VisibleMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.excluded_depth = 0
        self.sr_only_depth = 0
        self.text_parts = []
        self.paths = Counter()

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.excluded_depth += 1
            return
        attributes = dict(attrs)
        if "sr-only" in attributes.get("class", "").split():
            self.sr_only_depth += 1
        path = attributes.get("data-metadata-path")
        if path:
            self.paths[path] += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.excluded_depth:
            self.excluded_depth -= 1
        elif self.sr_only_depth:
            self.sr_only_depth -= 1

    def handle_data(self, data):
        if not self.excluded_depth and not self.sr_only_depth:
            self.text_parts.append(data)

    @property
    def text(self):
        return " ".join(" ".join(self.text_parts).split())


def load_fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text())


def fixture_scalar_leaves(value, path="", atomic_paths=frozenset()):
    if path in NULLABLE_REGISTERED_CONTAINERS and value is None:
        for registered_path in NULLABLE_REGISTERED_CONTAINERS[path]:
            yield registered_path, value
        return
    if path in atomic_paths:
        yield path, value
        return
    if isinstance(value, dict):
        if not value:
            yield path, value
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            yield from fixture_scalar_leaves(child, child_path, atomic_paths)
        return
    if isinstance(value, list):
        if not value:
            yield path, value
            return
        for child in value:
            yield from fixture_scalar_leaves(child, f"{path}[]", atomic_paths)
        return
    yield path, value


def registered_owner(path):
    if path in NON_DISPLAYED or path.startswith("raw_payload."):
        return "non-displayed"
    if path in EXPECTED_UNKNOWN_EXTENSIONS:
        return "unknown-extension"
    if path in KNOWN_KEYS():
        return path
    for catch_all in CATCH_ALL:
        if path.startswith(f"{catch_all}."):
            return catch_all
    return None


def unmapped_paths(payload):
    return sorted(
        {
            path
            for path, _value in fixture_scalar_leaves(
                payload,
                atomic_paths=KNOWN_KEYS() | NON_DISPLAYED,
            )
            if registered_owner(path) is None
        }
    )


def presentation_paths(presentation):
    paths = Counter()

    def visit(node):
        paths[node.path] += 1
        for child in node.children:
            visit(child)

    for field in presentation.summary:
        paths[field.path] += 1
    for section in presentation.sections:
        for field in (*section.summary, *section.detail):
            paths[field.path] += 1
        for node in section.disclosure:
            visit(node)
        for comparative_set in section.comparative_sets:
            for row in comparative_set.rows:
                for cell in row.cells:
                    paths[cell.path] += 1
    return paths


def rendered_fixture(payload, historical=False):
    presentation = build_metadata_presentation(payload, historical=historical)
    html = render_to_string(
        "bilbyui/_gwflow_metadata.html",
        {"payload": payload, "presentation": presentation},
    )
    parser = VisibleMetadataParser()
    parser.feed(html)
    parser.close()
    return presentation, html, parser


class GWFlowMetadataRoundTripTests(SimpleTestCase):
    maxDiff = None

    def test_every_valid_fixture_display_leaf_is_reachable_in_html(self):
        exercised = set()
        for fixture_name in VALID_FIXTURES:
            payload = load_fixture(fixture_name)
            presentation, _html, parsed = rendered_fixture(payload)
            built_paths = presentation_paths(presentation)
            self.assertEqual([], unmapped_paths(payload))

            display_payload = {
                **payload,
                "analyses": [
                    record
                    for record in payload.get("analyses", ())
                    if isinstance(record, dict) and record.get("type") == "pe"
                ],
            }
            for leaf_path, value in fixture_scalar_leaves(
                display_payload,
                atomic_paths=KNOWN_KEYS() | NON_DISPLAYED,
            ):
                owner = registered_owner(leaf_path)
                self.assertIsNotNone(owner, leaf_path)
                if owner == "non-displayed":
                    continue
                if owner == "unknown-extension":
                    concrete_path = leaf_path
                    self.assertGreater(
                        parsed.paths[concrete_path],
                        0,
                        f"{leaf_path} is not reachable in rendered HTML",
                    )
                    continue
                exercised.add(owner)
                if owner in CATCH_ALL:
                    section = {
                        "detector_configurations[]": "detchar",
                        "catalog_connections[]": "catalog_tracking",
                    }[owner]
                    concrete_path = f"{section}.{leaf_path.replace('[]', '[0]')}"
                    self.assertGreater(
                        parsed.paths[concrete_path],
                        0,
                        f"{leaf_path} is not reachable in rendered HTML",
                    )
                else:
                    section = self.section_for(owner)
                    presentation_path = f"{section}.{owner}"
                    self.assertGreater(built_paths[presentation_path], 0)
                    formatted = VisibleMetadataParser()
                    formatted.feed(str(format_value(value, FORMATTER_BY_PATH[owner])))
                    formatted.close()
                    self.assertIn(formatted.text, parsed.text)

            for path in built_paths:
                with self.subTest(fixture=fixture_name, rendered_path=path):
                    self.assertGreater(parsed.paths[path], 0)

        self.assertTrue(KNOWN_KEYS().issubset(exercised))

    def test_long_pe_lists_keep_fourth_and_later_items_reachable(self):
        payload = load_fixture("complete_curated.json")
        _presentation, html, parsed = rendered_fixture(payload)
        self.assertIn("bilby_config_4.ini", parsed.text)
        self.assertIn("Review 4", parsed.text)
        self.assertIn("Reviewer 4", parsed.text)
        self.assertIn("Canonical review 4", parsed.text)
        self.assertIn("2026-08-04 12:00:00 UTC", parsed.text)
        self.assertNotIn('class="sr-only">All items:', html)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_falsy_literals_all_render(self):
        payload = {
            "sname": "",
            "version_number": 0,
            "commit_sha": None,
            "is_current": False,
            "analyses": [
                {
                    "uid": "pe_1",
                    "type": "pe",
                    "name": "",
                    "status": "complete",
                    "review_status": "pending",
                    "deprecated": False,
                    "in_catalog": True,
                }
            ],
        }
        _presentation, _html, parsed = rendered_fixture(payload)
        for literal in ("0", "✗ False", "✓ True", '""', "—"):
            with self.subTest(literal=literal):
                self.assertIn(literal, parsed.text)

    def test_unmapped_probe_renders_but_fails_completeness(self):
        payload = copy.deepcopy(load_fixture("complete_curated.json"))
        payload["UnmappedProbe"] = {"deep": {"sentinel": "UX8_PROBE"}}
        _presentation, _html, parsed = rendered_fixture(payload)
        self.assertIn("UX8_PROBE", parsed.text)
        self.assertEqual(unmapped_paths(payload), ["UnmappedProbe.deep.sentinel"])

    def test_comparative_unknown_fields_render_in_disclosure(self):
        payload = {
            "gracedb_events": [{"event_name": "G1", "new_metric": 5, "new_nested": {"sentinel": "UX8"}}],
            "analyses": [{"uid": "P1", "type": "pe", "extra": {"deep": "PEUX8"}}],
        }
        presentation, _html, parsed = rendered_fixture(payload)
        paths = presentation_paths(presentation)
        self.assertGreater(paths["gracedb.gracedb_events[0].new_metric"], 0)
        self.assertGreater(paths["gracedb.gracedb_events[0].new_nested"], 0)
        self.assertGreater(paths["pe.analyses[0].extra"], 0)
        self.assertIn("UX8", parsed.text)
        self.assertIn("PEUX8", parsed.text)

    def test_catch_all_record_unknown_leaf_is_lossless_and_warned(self):
        payload = {
            "detector_configurations": [{"uid": "H1", "new_subtype_leaf": "DET-UX8"}],
            "catalog_connections": [
                {
                    "catalog_number": 4,
                    "catalog_version": 1,
                    "new_catalog_leaf": "CAT-UX8",
                }
            ],
        }
        _presentation, _html, parsed = rendered_fixture(payload)
        self.assertIn("DET-UX8", parsed.text)
        self.assertIn("CAT-UX8", parsed.text)
        self.assertEqual(unmapped_paths(payload), [])

        _reset_unmapped_warning_cache()
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-CATCH-ALL")
        _reset_unmapped_warning_cache()
        self.assertIn(
            "detector_configurations[].new_subtype_leaf",
            [record.path for record in captured.records],
        )
        self.assertIn(
            "catalog_connections[].new_catalog_leaf",
            [record.path for record in captured.records],
        )

    def test_historical_flag_changes_only_chrome(self):
        payload = load_fixture("historical_curated.json")
        current, _current_html, current_parser = rendered_fixture(payload)
        historical, _historical_html, historical_parser = rendered_fixture(
            payload,
            historical=True,
        )
        self.assertEqual(current.summary, historical.summary)
        self.assertEqual(current.sections, historical.sections)
        self.assertNotIn("Viewing historical metadata", current_parser.text)
        historical_body = historical_parser.text.replace(
            "⚠ Viewing historical metadata — not the current record",
            "",
        )
        self.assertEqual(current_parser.text, " ".join(historical_body.split()))

    def test_unmapped_warning_is_deduplicated_without_values(self):
        payload = {
            "gracedb_events": [
                {"event_name": "G1", "new_metric": 5},
                {"event_name": "G2", "new_metric": 6},
            ],
            "UnmappedProbe": {"deep": {"sentinel": "UX8"}},
        }
        _reset_unmapped_warning_cache()
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-TEST")
        _reset_unmapped_warning_cache()
        self.assertEqual(
            [record.path for record in captured.records],
            ["UnmappedProbe.deep.sentinel", "gracedb_events[].new_metric"],
        )
        self.assertNotIn("UX8", "\n".join(captured.output))

    @staticmethod
    def section_for(path):
        if path in {field.key for field in FIELD_REGISTRY["info"]}:
            return "info"
        if path.startswith("gracedb_events[]"):
            return "gracedb"
        if path.startswith("analyses[]"):
            return "pe"
        raise AssertionError(f"No section for {path}")
