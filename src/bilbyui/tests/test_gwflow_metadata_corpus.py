import copy
import json
import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import (
    FIELD_REGISTRY,
    KNOWN_KEYS,
    RECOGNISED_NON_DISPLAYED_PATHS,
    build_metadata_presentation,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "metadata_corpus"
VALID_FIXTURES = (
    "complete_curated.json",
    "absent_optional_highlights.json",
    "historical_curated.json",
)
PROBE_FIXTURE = "unmapped_probe.json"
NON_DISPLAYED = RECOGNISED_NON_DISPLAYED_PATHS
CATCH_ALL = frozenset({"detector_configurations[]", "catalog_connections[]"})
EXPECTED_UNKNOWN_EXTENSIONS = frozenset({"future_section.unsafe"})
NULLABLE_REGISTERED_CONTAINERS = {
    "analyses[].software": (
        "analyses[].software.name",
        "analyses[].software.version",
    ),
}
COMPARATIVE_COLUMNS = frozenset(
    {
        path
        for section in ("gracedb", "pe")
        for path in (field.key for field in FIELD_REGISTRY[section])
    }
)
CANONICAL_PATH = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)*$"
)


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
        list_path = f"{path}[]"
        for child in value:
            yield from fixture_scalar_leaves(child, list_path, atomic_paths)
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
        prefix = catch_all.removesuffix("[]")
        if path == prefix or path.startswith(f"{catch_all}."):
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


def assert_fixture_complete(testcase, payload):
    unknown = unmapped_paths(payload)
    testcase.assertEqual([], unknown, f"Unmapped canonical paths: {', '.join(unknown)}")


class GWFlowMetadataCorpusTests(SimpleTestCase):
    maxDiff = None

    def test_valid_fixture_scalar_leaves_have_registered_or_non_displayed_owner(self):
        for fixture_name in VALID_FIXTURES:
            with self.subTest(fixture=fixture_name):
                assert_fixture_complete(self, load_fixture(fixture_name))

    def test_exact_and_catch_all_owner_policies_are_distinct(self):
        self.assertEqual(registered_owner("sname"), "sname")
        self.assertEqual(
            registered_owner("gracedb_events[].event_name"),
            "gracedb_events[].event_name",
        )
        self.assertEqual(
            registered_owner("analyses[].software.name"),
            "analyses[].software.name",
        )
        self.assertEqual(
            tuple(
                path
                for path, value in fixture_scalar_leaves(
                    None,
                    "analyses[].software",
                    KNOWN_KEYS() | NON_DISPLAYED,
                )
                if value is None
            ),
            (
                "analyses[].software.name",
                "analyses[].software.version",
            ),
        )
        self.assertEqual(
            registered_owner("detector_configurations[].subtype_state"),
            "detector_configurations[]",
        )
        self.assertEqual(
            registered_owner("catalog_connections[].custom_probability"),
            "catalog_connections[]",
        )
        self.assertIsNone(registered_owner("UnmappedProbe.deep.sentinel"))

    def test_canonical_path_grammar_is_consistent(self):
        for path in KNOWN_KEYS() | COMPARATIVE_COLUMNS | NON_DISPLAYED:
            with self.subTest(path=path):
                self.assertRegex(path, CANONICAL_PATH)
                self.assertNotRegex(path, r"\[\d+\]")
        for fixture_name in VALID_FIXTURES:
            for path, _value in fixture_scalar_leaves(
                load_fixture(fixture_name),
                atomic_paths=KNOWN_KEYS() | NON_DISPLAYED,
            ):
                with self.subTest(fixture=fixture_name, path=path):
                    self.assertRegex(path, CANONICAL_PATH)

    def test_complete_fixture_covers_lossless_lists_and_protocol_obligations(self):
        payload = load_fixture("complete_curated.json")
        pe = next(record for record in payload["analyses"] if record["type"] == "pe")
        self.assertGreaterEqual(len(pe["input_files"]), 4)
        self.assertGreaterEqual(len(pe["reviews"]), 4)
        self.assertIsNone(pe["input_files"][0]["file"]["provenance"])
        self.assertEqual(
            set(pe["reviews"][0]),
            {
                "occurrence_uid",
                "name",
                "description",
                "passed_review",
                "completion_date",
                "review_status",
                "reviewers",
            },
        )
        self.assertEqual(
            next(record for record in payload["analyses"] if record["type"] == "event_validation")["uid"],
            "S000001a-validation-report",
        )
        self.assertIn("<script>", payload["future_section"]["unsafe"])
        self.assertEqual(pe["analysts"][0]["name"], "Sanitised Analyst")
        self.assertEqual(pe["configurations"][0]["uid"], "pe-config-1")

    def test_comparative_shapes_match_fixture_records(self):
        payload = load_fixture("complete_curated.json")
        grace_keys = tuple(payload["gracedb_events"][0])
        pe_record = next(item for item in payload["analyses"] if item["type"] == "pe")
        self.assertEqual(
            grace_keys,
            tuple(field.key.removeprefix("gracedb_events[].") for field in FIELD_REGISTRY["gracedb"]),
        )
        for field in FIELD_REGISTRY["pe"]:
            root_key = field.key.removeprefix("analyses[].").split(".", 1)[0]
            self.assertIn(root_key, pe_record)

    def test_every_registered_field_is_exercised(self):
        payload = load_fixture("complete_curated.json")
        exercised = {
            registered_owner(path)
            for path, _value in fixture_scalar_leaves(
                payload,
                atomic_paths=KNOWN_KEYS() | NON_DISPLAYED,
            )
        }
        self.assertTrue(KNOWN_KEYS().issubset(exercised))

    def test_negative_clone_reports_full_canonical_probe_path(self):
        payload = copy.deepcopy(load_fixture("complete_curated.json"))
        payload["UnmappedProbe"] = {"deep": {"sentinel": "UX8_PROBE"}}
        with self.assertRaisesRegex(AssertionError, r"UnmappedProbe\.deep\.sentinel"):
            assert_fixture_complete(self, payload)

    def test_unknown_disclosure_is_lossless_but_mapping_still_fails(self):
        payload = load_fixture(PROBE_FIXTURE)
        presentation = build_metadata_presentation(payload)
        html = render_to_string(
            "bilbyui/_gwflow_metadata.html",
            {"payload": payload, "presentation": presentation},
        )
        self.assertIn("UX8_PROBE", html)
        self.assertIn("UnmappedProbe.deep.sentinel", unmapped_paths(payload))
        with self.assertRaises(AssertionError):
            assert_fixture_complete(self, payload)

    def test_historical_flag_changes_context_not_payload_values(self):
        payload = load_fixture("historical_curated.json")
        current = build_metadata_presentation(payload)
        historical = build_metadata_presentation(payload, historical=True)
        self.assertFalse(current.historical)
        self.assertTrue(historical.historical)
        self.assertEqual(current.summary, historical.summary)
        self.assertEqual(current.sections, historical.sections)
