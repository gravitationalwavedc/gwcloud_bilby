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
    build_metadata_presentation,
)
from bilbyui.templatetags.gwflow_tags import format_value

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "metadata_corpus"
VALID_FIXTURES = (
    "complete_curated.json",
    "absent_optional_highlights.json",
    "historical_curated.json",
)

COMPARATIVE_COLUMNS = frozenset(
    {
        "gracedb.events[].uid",
        "gracedb.events[].pipeline",
        "gracedb.events[].state",
        "gracedb.events[].gps_time",
        "gracedb.events[].far",
        "gracedb.events[].network_snr",
        "gracedb.events[].pastro",
        "gracedb.events[].p_bbh",
        "gracedb.events[].p_bns",
        "gracedb.events[].p_nsbh",
        "gracedb.events[].mass_1",
        "gracedb.events[].mass_2",
        "pe.results[].uid",
        "pe.results[].inference_software",
        "pe.results[].waveform_approximant",
        "pe.results[].run_status",
        "pe.results[].review_status",
        "pe.results[].analysts",
        "pe.results[].reviewers",
        "pe.results[].deprecated",
    }
)
REGISTERED_PATHS = KNOWN_KEYS() | COMPARATIVE_COLUMNS
FORMATTER_BY_PATH = {
    f"{section}.{field.key}": field.formatter for section, fields in FIELD_REGISTRY.items() for field in fields
}


class VisibleMetadataParser(HTMLParser):
    """Collect body text and rendered path hooks, never attribute values as text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._excluded_depth = 0
        self.text_parts = []
        self.paths = Counter()

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._excluded_depth += 1
            return
        attributes = dict(attrs)
        path = attributes.get("data-metadata-path")
        if path:
            self.paths[path] += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._excluded_depth:
            self._excluded_depth -= 1

    def handle_data(self, data):
        if not self._excluded_depth:
            self.text_parts.append(data)

    @property
    def text(self):
        return " ".join(" ".join(self.text_parts).split())


def load_fixture(name):
    with (FIXTURE_DIR / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def fixture_scalar_leaves(value, path=""):
    """Walk fixture content only, using [] rather than concrete list indices."""
    if isinstance(value, dict):
        if not value:
            yield path, value
            return
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            yield from fixture_scalar_leaves(child, child_path)
        return
    if isinstance(value, list):
        if not value:
            yield path, value
            return
        list_path = f"{path}[]"
        for child in value:
            yield from fixture_scalar_leaves(child, list_path)
        return
    yield path, value


def registered_owner(path):
    """Return the most-specific registered field containing a fixture leaf."""
    owners = [
        candidate
        for candidate in REGISTERED_PATHS
        if path == candidate or path.startswith(f"{candidate}.") or path.startswith(f"{candidate}[]")
    ]
    if not owners:
        return None
    return max(owners, key=len)


def unmapped_paths(payload):
    return sorted({path for path, _value in fixture_scalar_leaves(payload) if registered_owner(path) is None})


def assert_fixture_complete(testcase, payload):
    unknown = unmapped_paths(payload)
    testcase.assertEqual([], unknown, f"Unmapped canonical paths: {', '.join(unknown)}")


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

    def test_every_valid_fixture_leaf_round_trips_through_complete_fragment(self):
        exercised = set()
        for fixture_name in VALID_FIXTURES:
            payload = load_fixture(fixture_name)
            presentation, _html, parsed = rendered_fixture(payload)
            built_paths = presentation_paths(presentation)

            with self.subTest(fixture=fixture_name, check="mapping"):
                assert_fixture_complete(self, payload)

            grouped_leaves = {}
            for leaf_path, value in fixture_scalar_leaves(payload):
                owner = registered_owner(leaf_path)
                self.assertIsNotNone(owner, leaf_path)
                exercised.add(owner)
                grouped_leaves.setdefault(owner, []).append((leaf_path, value))

            for owner, leaves in grouped_leaves.items():
                formatter = FORMATTER_BY_PATH[owner]
                with self.subTest(fixture=fixture_name, path=owner):
                    self.assertGreater(
                        built_paths[owner],
                        0,
                        f"{owner} has fixture leaves but no presentation field/node",
                    )
                    # The canonical field formatter owns container formatting.
                    # Scalar descendants are additionally checked when their
                    # formatted value is independently visible.
                    owner_value = self._registered_value(payload, owner)
                    expected = str(format_value(owner_value, formatter))
                    self.assertIn(expected, parsed.text)
                    for leaf_path, scalar in leaves:
                        scalar_text = str(format_value(scalar, formatter))
                        if scalar_text in expected:
                            self.assertIn(
                                scalar_text,
                                parsed.text,
                                f"{leaf_path} did not survive canonical formatting",
                            )

            # Equal scalar values cannot pass merely because another field
            # rendered the same substring: every owning path must be built.
            duplicate_values = Counter(
                json.dumps(value, sort_keys=True) for _path, value in fixture_scalar_leaves(payload)
            )
            for leaf_path, value in fixture_scalar_leaves(payload):
                if duplicate_values[json.dumps(value, sort_keys=True)] > 1:
                    owner = registered_owner(leaf_path)
                    with self.subTest(fixture=fixture_name, duplicate_path=leaf_path):
                        self.assertGreater(built_paths[owner], 0)

            # Every prepared field and disclosure node has a corresponding
            # rendered path hook. Root-summary duplicates may share the same
            # canonical path, so reachability rather than equal counts is used.
            for path in built_paths:
                with self.subTest(fixture=fixture_name, rendered_path=path):
                    self.assertGreater(
                        parsed.paths[path],
                        0,
                        f"presentation path {path} is not reachable in rendered HTML",
                    )

        expected_exercised = {
            f"{section}.{field.key}" for section, fields in FIELD_REGISTRY.items() for field in fields
        }
        self.assertEqual(expected_exercised, exercised)

    def test_falsy_values_are_literal_and_only_none_is_missing(self):
        payload = load_fixture("complete_curated.json")
        _presentation, _html, parsed = rendered_fixture(payload)
        for literal in ("0", "✗ False", "✓ True", '""'):
            with self.subTest(literal=literal):
                self.assertIn(literal, parsed.text)
        self.assertIn("—", parsed.text)
        self.assertEqual("0", format_value(0, "text"))
        self.assertEqual("✗ False", format_value(False, "boolean"))
        self.assertEqual("✓ True", format_value(True, "boolean"))
        self.assertEqual('""', format_value("", "text"))
        self.assertEqual("—", format_value(None, "text"))
        self.assertNotEqual("—", format_value([], "text"))
        self.assertNotEqual("—", format_value({}, "text"))

    def test_unmapped_probe_is_rendered_but_fails_with_full_path(self):
        payload = copy.deepcopy(load_fixture("complete_curated.json"))
        payload["UnmappedProbe"] = {"deep": {"sentinel": "UX8_PROBE"}}
        _presentation, _html, parsed = rendered_fixture(payload)
        self.assertIn("UX8_PROBE", parsed.text)
        with self.assertRaisesRegex(
            AssertionError,
            r"UnmappedProbe\.deep\.sentinel",
        ):
            assert_fixture_complete(self, payload)

    def test_unknown_leaves_in_comparative_records_render_in_disclosure(self):
        payload = {
            "gracedb": {"events": [{"uid": "E1", "new_metric": 5, "new_nested": {"sentinel": "UX8"}}]},
            "pe": {"results": [{"uid": "P1", "extra": {"deep": "PEUX8"}}]},
        }
        presentation, _html, parsed = rendered_fixture(payload)
        paths = presentation_paths(presentation)
        self.assertGreater(paths["gracedb.events[0].new_metric"], 0)
        self.assertGreater(paths["gracedb.events[0].new_nested"], 0)
        self.assertGreater(paths["pe.results[0].extra"], 0)
        self.assertIn("UX8", parsed.text)
        self.assertIn("PEUX8", parsed.text)

    def test_unmapped_paths_are_logged_deduplicated_without_values(self):
        payload = {
            "gracedb": {
                "events": [
                    {"uid": "E1", "new_metric": 5},
                    {"uid": "E2", "new_metric": 6},
                ]
            },
            "UnmappedProbe": {"deep": {"sentinel": "UX8"}},
        }
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as cm:
            build_metadata_presentation(payload)
        combined = "\n".join(cm.output)
        self.assertEqual(combined.count("gracedb.events[].new_metric"), 1)
        self.assertIn("UnmappedProbe.deep.sentinel", combined)
        self.assertNotIn("UX8", combined)

    def test_historical_context_does_not_change_scientific_body(self):
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

    def _registered_value(self, payload, canonical_path):
        current = payload
        parts = canonical_path.split(".")
        section = parts.pop(0)
        current = payload[section]
        for part in parts:
            if part.endswith("[]"):
                key = part[:-2]
                current = current[key]
                # Corpus records use one row where a scalar canonical field is
                # resolved; all rows are still independently represented by
                # presentation path coverage.
                current = current[0]
            else:
                current = current[part]
        return current
