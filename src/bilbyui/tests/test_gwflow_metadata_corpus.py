import copy
import json
import re
from pathlib import Path

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import (
    FIELD_REGISTRY,
    KNOWN_KEYS,
    build_metadata_presentation,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "metadata_corpus"
VALID_FIXTURES = (
    "complete_curated.json",
    "absent_optional_highlights.json",
    "historical_curated.json",
)
PROBE_FIXTURE = "unmapped_probe.json"

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
CANONICAL_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)*$")


def load_fixture(name):
    with (FIXTURE_DIR / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def fixture_scalar_leaves(value, path="", known_keys=frozenset()):
    """Enumerate fixture leaves only; this is not production enforcement."""
    if path in known_keys:
        yield path, value
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            yield from fixture_scalar_leaves(child, child_path, known_keys)
        return
    if isinstance(value, list):
        list_path = f"{path}[]"
        if not value:
            yield path, value
            return
        for child in value:
            yield from fixture_scalar_leaves(child, list_path, known_keys)
        return
    yield path, value


def unmapped_paths(payload):
    recognised = KNOWN_KEYS() | COMPARATIVE_COLUMNS
    return sorted(
        {
            path
            for path, _value in fixture_scalar_leaves(
                payload,
                known_keys=recognised,
            )
            if path not in recognised
        }
    )


def assert_fixture_complete(testcase, payload):
    unknown = unmapped_paths(payload)
    testcase.assertEqual([], unknown, f"Unmapped canonical paths: {', '.join(unknown)}")


class GWFlowMetadataCorpusTests(SimpleTestCase):
    maxDiff = None

    def test_valid_fixture_scalar_leaves_are_registered(self):
        for fixture_name in VALID_FIXTURES:
            with self.subTest(fixture=fixture_name):
                assert_fixture_complete(self, load_fixture(fixture_name))

    def test_canonical_path_grammar_is_consistent(self):
        all_paths = KNOWN_KEYS() | COMPARATIVE_COLUMNS
        for path in all_paths:
            with self.subTest(path=path):
                self.assertRegex(path, CANONICAL_PATH)
                self.assertNotRegex(path, r"\[\d+\]")
        for fixture_name in VALID_FIXTURES:
            payload = load_fixture(fixture_name)
            for path, _value in fixture_scalar_leaves(
                payload,
                known_keys=all_paths,
            ):
                with self.subTest(fixture=fixture_name, path=path):
                    self.assertRegex(path, CANONICAL_PATH)

    def test_comparative_shapes_are_locked(self):
        payload = load_fixture("complete_curated.json")
        grace_keys = tuple(payload["gracedb"]["events"][0])
        pe_keys = tuple(payload["pe"]["results"][0])
        self.assertEqual(
            tuple(path.rsplit(".", 1)[-1] for path in COMPARATIVE_COLUMNS if path.startswith("never.")),
            (),
        )
        expected_grace = tuple(
            path.removeprefix("gracedb.events[].")
            for path in (
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
            )
        )
        expected_pe = tuple(
            path.removeprefix("pe.results[].")
            for path in (
                "pe.results[].uid",
                "pe.results[].inference_software",
                "pe.results[].waveform_approximant",
                "pe.results[].run_status",
                "pe.results[].review_status",
                "pe.results[].analysts",
                "pe.results[].reviewers",
                "pe.results[].deprecated",
            )
        )
        self.assertEqual(grace_keys, expected_grace)
        self.assertEqual(pe_keys, expected_pe)
        self.assertEqual(len(grace_keys), 12)
        self.assertEqual(len(pe_keys), 8)

    def test_every_registered_field_is_exercised(self):
        payload = load_fixture("complete_curated.json")
        exercised = {
            path
            for path, _value in fixture_scalar_leaves(
                payload,
                known_keys=KNOWN_KEYS() | COMPARATIVE_COLUMNS,
            )
        }
        expected = {f"{section}.{field.key}" for section, fields in FIELD_REGISTRY.items() for field in fields}
        self.assertEqual(expected, exercised)

    def test_negative_clone_reports_full_canonical_probe_path(self):
        payload = copy.deepcopy(load_fixture("complete_curated.json"))
        payload["UnmappedProbe"] = {"deep": {"sentinel": "UX8_PROBE"}}
        with self.assertRaisesRegex(
            AssertionError,
            r"UnmappedProbe\.deep\.sentinel",
        ):
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
