"""Mapping, digest, cache and golden-document tests for the GWFlow rebuild."""

import json
from copy import deepcopy
from datetime import UTC, datetime

from django.core.cache import caches

from bilbyui.models import EventID, GWFlowJob
from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY
from bilbyui.services.search_registry import _DEFAULT_FIELD, GWFLOW_ALIASES
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_es import (
    build_gwflow_es_doc,
    build_gwflow_es_mapping,
    clear_gwflow_portal_cache,
    compute_protected_identity_digest,
    invalidate_gwflow_facet_caches,
    mapping_satisfies_contract,
)

CANONICAL_SECTIONS = (
    "metadata.analyses",
    "metadata.detector_configurations",
    "metadata.gracedb_events",
    "metadata.catalog_connections",
)


def golden_detail(sname="S000001a", library=None):
    """Return the shared golden canonical detail payload."""
    if library is None:
        library = "o4b" if sname == "S000002b" else "o4a"

    return {
        "sname": sname,
        "libraries": [library],
        "version_number": 1,
        "record_timestamp": "2026-08-31T12:00:00Z",
        "commit_sha": "0" * 40,
        "is_current": True,
        "analyses": [
            {
                "uid": "pe_1",
                "type": "pe",
                "revision": "1",
                "name": "PE",
                "description": "",
                "status": "complete",
                "deprecated": False,
                "software": {"name": "bilby_pipe", "version": "1.2.0"},
                "analysts": [],
                "reviews": [],
                "input_files": [
                    {
                        "direction": "input",
                        "role": "config",
                        "file": {
                            "name": "bilby_config.ini",
                            "description": "Bilby parameter-estimation configuration",
                            "md5sum": "0123456789abcdef0123456789abcdef",
                            "last_modified": "2026-08-31T11:59:00Z",
                            "locations": ["https://example.test/bilby_config.ini"],
                        },
                    }
                ],
                "output_files": [],
                "configurations": [],
                "in_catalog": True,
                "review_status": "approved",
            },
            {
                "uid": "S000001a-validation-report",
                "type": "event_validation",
                "revision": "1",
                "name": "Event validation",
                "description": "",
                "status": "complete",
                "deprecated": False,
                "software": None,
                "analysts": [],
                "reviews": [],
                "input_files": [],
                "output_files": [],
                "configurations": [],
                "suggested_detector_configuration_uids": ["H1"],
                "review_status": "approved",
            },
        ],
        "detector_configurations": [{"uid": "H1"}],
        "gracedb_events": [{"event_name": "G000001", "network_snr": 12.5}],
        "catalog_connections": [{"catalog_number": 4, "catalog_version": 1, "far": 1e-9}],
        "raw_payload": None,
    }


class TestGWFlowMapping(BilbyTestCase):
    def setUp(self):
        self.mapping = build_gwflow_es_mapping()

    def test_default_fields_match_search_registry(self):
        self.assertEqual(
            self.mapping["settings"]["index"]["query"]["default_field"],
            _DEFAULT_FIELD,
        )

    def test_aliases_match_registry_and_all_targets_exist(self):
        from bilbyui.management.commands.verify_search_fields import (
            _flatten_properties,
        )

        fields = _flatten_properties(self.mapping["mappings"]["properties"])
        aliases = {path: definition["path"] for path, definition in fields.items() if definition.get("type") == "alias"}
        self.assertEqual(aliases, GWFLOW_ALIASES)
        self.assertTrue(set(aliases.values()) <= fields.keys())
        self.assertNotIn("pastro", aliases)

    def test_search_trigger_time_is_explicit_double(self):
        gwcloud = self.mapping["mappings"]["properties"]["_gwcloud"]["properties"]
        self.assertEqual(gwcloud["searchTriggerTime"], {"type": "double"})

    def test_canonical_sections_have_exact_numeric_templates(self):
        self.assertEqual(
            self.mapping["mappings"]["dynamic_templates"],
            [
                {
                    "analyses_numbers_long": {
                        "path_match": "metadata.analyses.*",
                        "match_mapping_type": "long",
                        "mapping": {"type": "double"},
                    }
                },
                {
                    "analyses_numbers_double": {
                        "path_match": "metadata.analyses.*",
                        "match_mapping_type": "double",
                        "mapping": {"type": "double"},
                    }
                },
                {
                    "detector_configuration_numbers_long": {
                        "path_match": "metadata.detector_configurations.*",
                        "match_mapping_type": "long",
                        "mapping": {"type": "double"},
                    }
                },
                {
                    "detector_configuration_numbers_double": {
                        "path_match": "metadata.detector_configurations.*",
                        "match_mapping_type": "double",
                        "mapping": {"type": "double"},
                    }
                },
                {
                    "gracedb_event_numbers_long": {
                        "path_match": "metadata.gracedb_events.*",
                        "match_mapping_type": "long",
                        "mapping": {"type": "double"},
                    }
                },
                {
                    "gracedb_event_numbers_double": {
                        "path_match": "metadata.gracedb_events.*",
                        "match_mapping_type": "double",
                        "mapping": {"type": "double"},
                    }
                },
                {
                    "catalog_connection_numbers_long": {
                        "path_match": "metadata.catalog_connections.*",
                        "match_mapping_type": "long",
                        "mapping": {"type": "double"},
                    }
                },
                {
                    "catalog_connection_numbers_double": {
                        "path_match": "metadata.catalog_connections.*",
                        "match_mapping_type": "double",
                        "mapping": {"type": "double"},
                    }
                },
            ],
        )

    def test_legacy_raw_payload_is_stored_but_not_indexed(self):
        metadata = self.mapping["mappings"]["properties"]["metadata"]["properties"]
        self.assertEqual(metadata["raw_payload"], {"type": "object", "enabled": False})

    def test_no_metadata_array_is_nested(self):
        serialized = json.dumps(self.mapping)
        self.assertNotIn('"nested"', serialized)

    def test_templates_cannot_leak_to_other_sections(self):
        allowed = {f"{section}.*" for section in CANONICAL_SECTIONS}
        for entry in self.mapping["mappings"]["dynamic_templates"]:
            [(_, body)] = entry.items()
            self.assertIn(body["path_match"], allowed)

    def test_analysis_query_fields_are_keyword_and_deprecated_boolean(self):
        analyses = self.mapping["mappings"]["properties"]["metadata"]["properties"]["analyses"]["properties"]
        for field in ("uid", "type", "status", "review_status"):
            self.assertEqual(analyses[field], {"type": "keyword"})
        self.assertEqual(analyses["deprecated"], {"type": "boolean"})
        self.assertEqual(analyses["software"]["properties"]["name"], {"type": "keyword"})
        self.assertEqual(analyses["software"]["properties"]["version"], {"type": "keyword"})

    def test_contract_check_accepts_elasticsearch_normalisation(self):
        expected = self.mapping["mappings"]
        actual = deepcopy(expected)
        # ES returns stringified booleans, omits the default date format and
        # adds fields it inferred from indexed documents.
        actual["properties"]["metadata"]["dynamic"] = "true"
        del actual["properties"]["_gwcloud"]["properties"]["lastUpdatedTime"]["format"]
        del actual["properties"]["metadata"]["type"]
        del actual["properties"]["_gwcloud"]["type"]
        actual["properties"]["metadata"]["properties"]["analyses"]["properties"]["extra_inferred"] = {"type": "text"}
        self.assertTrue(mapping_satisfies_contract(expected, actual))

    def test_contract_check_rejects_wrong_declared_type(self):
        expected = self.mapping["mappings"]
        actual = deepcopy(expected)
        actual["properties"]["_gwcloud"]["properties"]["searchTriggerTime"] = {"type": "keyword"}
        self.assertFalse(mapping_satisfies_contract(expected, actual))

    def test_contract_check_rejects_missing_template(self):
        expected = self.mapping["mappings"]
        actual = deepcopy(expected)
        actual["dynamic_templates"] = actual["dynamic_templates"][:-1]
        self.assertFalse(mapping_satisfies_contract(expected, actual))


class TestGoldenDocument(BilbyTestCase):
    def test_document_rejects_malformed_present_analysis(self):
        user = self.create_user()
        job = GWFlowJob.objects.create(sname="S000001a", user=user)
        detail = golden_detail()
        detail["analyses"][0]["status"] = "not-canonical"

        from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata

        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(job, detail)

    def test_document_rejects_each_malformed_analysis_field(self):
        from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata

        user = self.create_user()
        job = GWFlowJob.objects.create(sname="S000001a", user=user)
        cases = (
            ("entry", None, "must be an object"),
            ("uid", "", ".uid must be a non-empty string"),
            ("type", "tgr", ".type must be 'pe' or 'event_validation'"),
            ("deprecated", "false", ".deprecated must be a boolean"),
            ("revision", True, ".revision must be an integer or a string"),
            ("revision", 1.5, ".revision must be an integer or a string"),
            ("name", None, ".name must be a string"),
            ("description", [], ".description must be a string"),
            ("analysts", {}, ".analysts must be an array"),
            ("reviews", {}, ".reviews must be an array"),
            ("input_files", {}, ".input_files must be an array"),
            ("output_files", {}, ".output_files must be an array"),
            ("configurations", {}, ".configurations must be an array"),
            ("software", "bilby", ".software must be an object or null"),
            ("software.name", None, ".software.name must be a string"),
            ("software.version", 1, ".software.version must be a string"),
            ("in_catalog", None, ".in_catalog must be a boolean"),
            ("review", "approved", ".reviews[0] must be an object"),
            ("review.review_status", "unknown", ".reviews[0].review_status is not canonical"),
            ("review_status", "unknown", ".review_status is not canonical"),
        )

        for field, value, message in cases:
            with self.subTest(field=field):
                detail = golden_detail()
                analysis = detail["analyses"][0]
                if field == "entry":
                    detail["analyses"][0] = value
                elif field == "software.name":
                    analysis["software"]["name"] = value
                elif field == "software.version":
                    analysis["software"]["version"] = value
                elif field == "review":
                    analysis["reviews"] = [value]
                elif field == "review.review_status":
                    analysis["reviews"] = [{"review_status": value}]
                else:
                    analysis[field] = value

                with self.assertRaisesRegex(InvalidGWFlowMetadata, message.replace("[", r"\[").replace("]", r"\]")):
                    build_gwflow_es_doc(job, detail)

    def test_document_rejects_missing_required_analysis_fields_together(self):
        from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata

        user = self.create_user()
        job = GWFlowJob.objects.create(sname="S000001a", user=user)
        detail = golden_detail()
        del detail["analyses"][0]["uid"]
        del detail["analyses"][0]["software"]

        with self.assertRaisesRegex(
            InvalidGWFlowMetadata,
            r"missing required field\(s\): uid, software",
        ):
            build_gwflow_es_doc(job, detail)

    def test_event_validation_requires_suggested_detector_configurations(self):
        from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata

        user = self.create_user()
        job = GWFlowJob.objects.create(sname="S000001a", user=user)
        detail = golden_detail()
        analysis = detail["analyses"][0]
        analysis["type"] = "event_validation"
        analysis.pop("in_catalog")
        analysis.pop("suggested_detector_configuration_uids", None)

        with self.assertRaisesRegex(
            InvalidGWFlowMetadata,
            "suggested_detector_configuration_uids must be an array",
        ):
            build_gwflow_es_doc(job, detail)

    def test_review_status_is_derived_from_canonical_reviews(self):
        cases = (
            ([], "pending"),
            ([{"review_status": "pending"}], "pending"),
            ([{"review_status": "approved"}, {"review_status": "approved"}], "approved"),
            ([{"review_status": "approved"}, {"review_status": "rejected"}], "rejected"),
        )
        for reviews, expected in cases:
            with self.subTest(expected=expected):
                detail = golden_detail()
                detail["analyses"][0].pop("review_status")
                detail["analyses"][0]["reviews"] = reviews
                from bilbyui.utils.gwflow_es import parse_analyses

                analyses = parse_analyses(detail)
                self.assertEqual(analyses[0]["review_status"], expected)

    def test_document_accepts_absent_analyses_and_rejects_null(self):
        from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata

        user = self.create_user()
        job = GWFlowJob.objects.create(sname="S000001a", user=user)

        absent = golden_detail()
        absent.pop("analyses")
        self.assertNotIn("analyses", build_gwflow_es_doc(job, absent)["metadata"])

        null = golden_detail()
        null["analyses"] = None
        with self.assertRaises(InvalidGWFlowMetadata):
            build_gwflow_es_doc(job, null)

    def test_document_identity_and_envelope(self):
        user = self.create_user()
        event = EventID.objects.create(event_id="G000001", trigger_id="S000001a", gps_time=100.0)
        job = GWFlowJob.objects.create(
            sname="S000001a",
            user=user,
            libraries=["o4a"],
            event_id=event,
            trigger_time=100.0,
            current_history_timestamp=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
        )
        doc = build_gwflow_es_doc(job, golden_detail())

        self.assertEqual(str(job.pk), "1")
        self.assertEqual(doc["_gwcloud"]["sname"], "S000001a")
        self.assertEqual(doc["_gwcloud"]["searchTriggerTime"], 100.0)
        self.assertEqual(doc["_gwcloud"]["eventTriggerId"], "S000001a")
        self.assertEqual(doc["metadata"]["analyses"][0]["uid"], "pe_1")
        validation = doc["metadata"]["analyses"][1]
        self.assertEqual(validation["uid"], "S000001a-validation-report")
        self.assertEqual(validation["type"], "event_validation")
        self.assertEqual(
            validation["suggested_detector_configuration_uids"],
            ["H1"],
        )
        config_inputs = [
            relationship
            for relationship in doc["metadata"]["analyses"][0]["input_files"]
            if relationship["role"] == "config"
        ]
        self.assertEqual(len(config_inputs), 1)
        self.assertEqual(config_inputs[0]["direction"], "input")
        self.assertEqual(config_inputs[0]["file"]["name"], "bilby_config.ini")
        self.assertEqual(
            config_inputs[0]["file"]["locations"],
            ["https://example.test/bilby_config.ini"],
        )

    def test_golden_second_event_uses_o4b_library(self):
        detail = golden_detail("S000002b")

        self.assertEqual(detail["sname"], "S000002b")
        self.assertEqual(detail["libraries"], ["o4b"])


class TestProtectedIdentityDigest(BilbyTestCase):
    def test_digest_is_stable_without_writes(self):
        user = self.create_user()
        GWFlowJob.objects.create(sname="S000001a", user=user)
        self.assertEqual(compute_protected_identity_digest(), compute_protected_identity_digest())

    def test_digest_changes_when_a_protected_row_changes(self):
        user = self.create_user()
        first_event = EventID.objects.create(event_id="G000001")
        second_event = EventID.objects.create(event_id="G000002")
        job = GWFlowJob.objects.create(sname="S000001a", user=user, event_id=first_event)
        before = compute_protected_identity_digest()
        GWFlowJob.objects.filter(pk=job.pk).update(event_id_id=second_event.pk)
        self.assertNotEqual(before, compute_protected_identity_digest())

    def test_digest_does_not_change_when_metadata_changes(self):
        user = self.create_user()
        job = GWFlowJob.objects.create(sname="S000001a", user=user)
        before = compute_protected_identity_digest()
        GWFlowJob.objects.filter(pk=job.pk).update(sname="S000002b")
        self.assertEqual(before, compute_protected_identity_digest())

    def test_digest_covers_every_protected_model(self):
        self.assertEqual(
            sorted(compute_protected_identity_digest()),
            ["BilbyJob", "EventID", "ExternalBilbyJob", "GWFlowJob", "combined"],
        )


class TestGWFlowCacheHelpers(BilbyTestCase):
    def setUp(self):
        self.cache = caches["default"]

    def test_portal_detail_key_is_cleared(self):
        self.cache.set("gwflow:se:S000001a", {"sname": "S000001a"}, 60)
        clear_gwflow_portal_cache("S000001a")
        self.assertIsNone(self.cache.get("gwflow:se:S000001a"))

    def test_facet_caches_are_invalidated(self):
        self.cache.set(LIBRARIES_CACHE_KEY, ["o4a"], 60)
        self.cache.set(REVIEW_STATUSES_CACHE_KEY, ["approved"], 60)
        invalidate_gwflow_facet_caches()
        self.assertIsNone(self.cache.get(LIBRARIES_CACHE_KEY))
        self.assertIsNone(self.cache.get(REVIEW_STATUSES_CACHE_KEY))
