import logging
from unittest import mock

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from bilbyui.services.gwflow_metadata import (
    _iter_leaf_paths,
    _reset_unmapped_warning_cache,
    build_metadata_presentation,
    warn_unmapped_metadata_leaves,
)
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import (
    _render_gwflow_history_section,
    _render_gwflow_metadata_section,
    gwflow_job_history_version_partial,
)


class LeafPathTests(SimpleTestCase):
    def tearDown(self):
        _reset_unmapped_warning_cache()
        super().tearDown()

    def test_walker_normalises_sequences_deduplicates_and_preserves_falsy_leaves(self):
        payload = {
            "items": [
                {"nested": {"zero": 0, "false": False, "blank": "", "none": None}},
                {"nested": {"zero": 2}},
            ],
            "scalars": ("first", "second"),
            "empty_mapping": {},
            "empty_sequence": [],
        }
        self.assertEqual(
            _iter_leaf_paths(payload),
            (
                "items[].nested.blank",
                "items[].nested.false",
                "items[].nested.none",
                "items[].nested.zero",
                "scalars[]",
            ),
        )

    def test_known_canonical_paths_are_silent(self):
        with self.assertNoLogs("bilbyui.services.gwflow_metadata", level="WARNING"):
            warn_unmapped_metadata_leaves(
                {
                    "sname": "S000001a",
                    "is_current": False,
                    "gracedb_events": [{"event_name": "G000001"}],
                    "analyses": [{"uid": "pe_1", "status": "complete"}],
                },
                sname="S-KNOWN",
            )

    def test_raw_payload_and_registered_comparative_descendants_are_silent(self):
        payload = {
            "raw_payload": {"GraceDB": {"Events": [{"secret": "never-walked"}]}},
            "analyses": [
                {
                    "uid": "pe_1",
                    "type": "pe",
                    "analysts": [{"name": "A", "email_address": "private@example.test"}],
                    "reviews": [
                        {
                            "occurrence_uid": "review-1",
                            "name": "Review",
                            "description": "Description",
                            "passed_review": None,
                            "completion_date": None,
                            "review_status": "pending",
                            "reviewers": [{"name": "R", "email_address": "hidden@example.test"}],
                        }
                    ],
                    "input_files": [{"file": {"name": "input.ini"}}],
                }
            ],
        }
        with self.assertNoLogs("bilbyui.services.gwflow_metadata", level="WARNING"):
            warn_unmapped_metadata_leaves(payload, sname="S-OWNED")

    def test_unknown_person_and_review_descendants_still_warn(self):
        payload = {
            "analyses": [
                {
                    "uid": "pe_1",
                    "type": "pe",
                    "analysts": [{"name": "A", "new_person_field": "SECRET-PERSON"}],
                    "reviews": [
                        {
                            "name": "R",
                            "reviewers": [{"name": "Reviewer", "new_reviewer_field": "SECRET-REVIEWER"}],
                            "new_review_field": "SECRET-REVIEW",
                        }
                    ],
                }
            ]
        }
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-NESTED-DRIFT")
        self.assertEqual(
            [record.path for record in captured.records],
            [
                "analyses[].analysts[].new_person_field",
                "analyses[].reviews[].new_review_field",
                "analyses[].reviews[].reviewers[].new_reviewer_field",
            ],
        )
        self.assertNotIn("SECRET", "\n".join(captured.output))

    def test_unregistered_comparative_leaf_still_warns_with_full_path(self):
        payload = {"analyses": [{"uid": "pe_1", "type": "pe", "new_field": {"leaf": "SECRET"}}]}
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-DRIFT")
        self.assertEqual([record.path for record in captured.records], ["analyses[].new_field.leaf"])
        self.assertNotIn("SECRET", "\n".join(captured.output))

    def test_catch_all_descendants_still_warn_by_exact_match_policy(self):
        payload = {
            "detector_configurations": [{"uid": "H1", "subtype_state": "science"}],
            "catalog_connections": [{"catalog_number": 4, "catalog_version": 1}],
        }
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-CATCH-ALL")
        self.assertEqual(
            [record.path for record in captured.records],
            [
                "catalog_connections[].catalog_number",
                "catalog_connections[].catalog_version",
                "detector_configurations[].subtype_state",
                "detector_configurations[].uid",
            ],
        )

    def test_deeply_nested_payload_degrades_with_truncation_warning(self):
        payload = {}
        node = payload
        for _ in range(2000):
            node["next"] = {}
            node = node["next"]
        node["leaf"] = 1
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-DEEP")
        self.assertEqual(len(captured.records), 1)
        self.assertIn("truncated", captured.records[0].getMessage())

    def test_non_mapping_payload_is_silent(self):
        for payload in ("not-a-mapping", None, ["not-a-mapping"]):
            with self.subTest(payload=payload):
                with self.assertNoLogs("bilbyui.services.gwflow_metadata", level="WARNING"):
                    warn_unmapped_metadata_leaves(payload, sname="S-NON-MAPPING")

    def test_warning_records_are_sorted_and_contain_no_values(self):
        payload = {"UnknownExtension": {"z": "SECRET-Z", "a": "SECRET-A"}}
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-WARN")
        self.assertEqual(
            [(record.path, record.sname) for record in captured.records],
            [
                ("UnknownExtension.a", "S-WARN"),
                ("UnknownExtension.z", "S-WARN"),
            ],
        )
        self.assertNotIn("SECRET", " ".join(record.getMessage() for record in captured.records))

    def test_limiter_keys_on_sname_and_path(self):
        logger_name = "bilbyui.services.gwflow_metadata"
        with self.assertLogs(logger_name, level="WARNING") as captured:
            warn_unmapped_metadata_leaves({"Unknown": {"drift": 1}}, sname="S-ONE")
            warn_unmapped_metadata_leaves({"Unknown": {"drift": 2}}, sname="S-ONE")
            warn_unmapped_metadata_leaves({"Unknown": {"drift": 3}}, sname="S-TWO")
            warn_unmapped_metadata_leaves({"Unknown": {"other": 4}}, sname="S-ONE")
        self.assertEqual(
            [(record.path, record.sname) for record in captured.records],
            [
                ("Unknown.drift", "S-ONE"),
                ("Unknown.drift", "S-TWO"),
                ("Unknown.other", "S-ONE"),
            ],
        )

    def test_blank_sname_is_normalised_and_cache_reset_restores_emission(self):
        payload = {"Unknown": {"drift": 1}}
        logger_name = "bilbyui.services.gwflow_metadata"
        with self.assertLogs(logger_name, level="WARNING") as first:
            warn_unmapped_metadata_leaves(payload, sname=" ")
        _reset_unmapped_warning_cache()
        with self.assertLogs(logger_name, level="WARNING") as second:
            warn_unmapped_metadata_leaves(payload, sname=None)
        self.assertEqual(first.records[0].sname, "unknown")
        self.assertEqual(second.records[0].sname, "unknown")


class CanonicalCompletenessTests(SimpleTestCase):
    def test_unknown_nested_and_falsy_values_render_and_warn(self):
        payload = {
            "sname": "",
            "version_number": 0,
            "is_current": False,
            "UnknownExtension": {"nested": "Nested upstream value"},
        }
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-INFO")
        presentation = build_metadata_presentation(payload)
        rendered = render_to_string(
            "bilbyui/_gwflow_metadata.html",
            {"payload": payload, "presentation": presentation},
        )
        self.assertIn("Nested upstream value", rendered)
        self.assertRegex(rendered, r">\s*0\s*<")
        self.assertIn("✗ False", rendered)
        self.assertIn("&quot;&quot;", rendered)
        self.assertEqual(
            [record.path for record in captured.records],
            ["UnknownExtension.nested"],
        )


class RecursionErrorGuardTests(SimpleTestCase):
    def tearDown(self):
        _reset_unmapped_warning_cache()
        super().tearDown()

    @staticmethod
    def deep_payload(depth):
        payload = {}
        node = payload
        for _ in range(depth):
            node["nested"] = {}
            node = node["nested"]
        node["leaf"] = 1
        return payload

    def test_build_and_warning_walk_degrade_on_deep_payload(self):
        payload = self.deep_payload(5000)
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING"):
            presentation = build_metadata_presentation(payload)
        self.assertEqual(presentation.sections, ())
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-DEEP")
        self.assertIn("truncated", captured.records[0].getMessage())


class MetadataWarningViewIntegrationTests(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.request = RequestFactory().get("/")

    @mock.patch("bilbyui.views.build_metadata_presentation")
    @mock.patch("bilbyui.views.warn_unmapped_metadata_leaves")
    @mock.patch("bilbyui.views.get_superevent")
    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    def test_current_path_builds_then_warns(self, get_job, get_superevent, warn, build):
        payload = {"sname": "S-CURRENT"}
        get_job.return_value = mock.Mock()
        get_superevent.return_value = (payload, "live")
        events = []
        build.side_effect = lambda *args, **kwargs: events.append("build") or mock.Mock()
        warn.side_effect = lambda *args, **kwargs: events.append("warn")
        response, stale = _render_gwflow_metadata_section(self.request, "S-CURRENT")
        self.assertFalse(stale)
        self.assertEqual(events, ["build", "warn"])
        warn.assert_called_once_with(payload, sname="S-CURRENT")
        self.assertEqual(response.context_data["payload"], payload)

    @mock.patch("bilbyui.views.build_metadata_presentation")
    @mock.patch("bilbyui.views.warn_unmapped_metadata_leaves")
    @mock.patch("bilbyui.views.get_version")
    @mock.patch(
        "bilbyui.views.get_versions",
        return_value=([{"commit_sha": "version-1", "version_number": 1}], "live"),
    )
    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    def test_historical_partial_builds_then_warns(
        self,
        get_job,
        get_versions,
        get_version,
        warn,
        build,
    ):
        payload = {"sname": "S-HISTORY"}
        get_job.return_value = mock.Mock()
        get_version.return_value = (payload, "live")
        events = []
        build.side_effect = lambda *args, **kwargs: events.append("build") or mock.Mock()
        warn.side_effect = lambda *args, **kwargs: events.append("warn")
        response = gwflow_job_history_version_partial(
            self.request,
            "S-HISTORY",
            "version-1",
        )
        self.assertEqual(events, ["build", "warn"])
        build.assert_called_once_with(payload, historical=True)
        warn.assert_called_once_with(payload, sname="S-HISTORY")
        self.assertEqual(response.context_data["payload"], payload)

    @mock.patch("bilbyui.views.adapt_semantic_diff")
    @mock.patch("bilbyui.views.get_diff", return_value=(None, "live"))
    @mock.patch("bilbyui.views.build_metadata_presentation")
    @mock.patch("bilbyui.views.warn_unmapped_metadata_leaves")
    @mock.patch("bilbyui.views.get_version")
    @mock.patch("bilbyui.views.resolve_history_selection")
    @mock.patch("bilbyui.views.prepare_version_snapshots")
    @mock.patch("bilbyui.views.get_versions", return_value=([], "live"))
    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    def test_history_section_builds_from_canonical_detail_not_raw_payload(
        self,
        get_job,
        get_versions,
        prepare,
        resolve,
        get_version,
        warn,
        build,
        get_diff,
        adapt,
    ):
        selected = mock.Mock(version_number=7, is_current=False)
        get_job.return_value = mock.Mock(current_history_id="sha-current")
        prepare.return_value = (selected,)
        resolve.return_value = (selected, None, "prev")
        detail = {
            "sname": "S-HISTORY",
            "gracedb_events": [{"event_name": "G000001"}],
            "raw_payload": {"Info": {"status": "legacy"}},
        }
        get_version.return_value = (detail, "live")
        build.return_value = mock.Mock()
        adapt.return_value = mock.Mock(status="no_baseline", rows=())
        _render_gwflow_history_section(self.request, "S-HISTORY")
        build.assert_called_once_with(detail, historical=True)
        warn.assert_called_once_with(detail, sname="S-HISTORY")


class ProductionLoggingRoutingTests(SimpleTestCase):
    def test_service_warning_inherits_warning_capable_bilbyui_route(self):
        import os

        environment = {
            "GWOSC_INGEST_USER": "1",
            "GWFLOW_INGEST_USER": "1",
            "PERMITTED_EVENT_CREATION_USER_IDS": "[]",
            "CLUSTERS": "{}",
        }
        with mock.patch.dict(os.environ, environment):
            from gw_bilby.prod import LOGGING

        config = LOGGING["loggers"]["bilbyui"]
        self.assertEqual(config["level"], "INFO")
        self.assertFalse(config["propagate"])
        self.assertEqual(config["handlers"], ["console", "file", "error_file"])
        self.assertTrue(logging.getLogger("bilbyui.services.gwflow_metadata").name.startswith("bilbyui."))
