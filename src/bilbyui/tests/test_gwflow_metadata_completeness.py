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
from bilbyui.views import _render_gwflow_metadata_section, gwflow_job_history_version_partial


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

    def test_known_paths_are_silent(self):
        with self.assertNoLogs("bilbyui.services.gwflow_metadata", level="WARNING"):
            warn_unmapped_metadata_leaves(
                {"info": {"notes": "known", "status": False}},
                sname="S-KNOWN",
            )

    def test_warning_records_are_exact_sorted_and_contain_no_values(self):
        payload = {"info": {"z_unknown": "SECRET-Z", "a_unknown": "SECRET-A"}}

        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-WARN")

        self.assertEqual(
            [(record.getMessage(), record.path, record.sname) for record in captured.records],
            [
                ("unmapped gwflow metadata leaf", "info.a_unknown", "S-WARN"),
                ("unmapped gwflow metadata leaf", "info.z_unknown", "S-WARN"),
            ],
        )
        self.assertNotIn("SECRET", " ".join(record.getMessage() for record in captured.records))

    def test_limiter_suppresses_same_key_but_keeps_sname_and_path_independent(self):
        logger_name = "bilbyui.services.gwflow_metadata"
        with self.assertLogs(logger_name, level="WARNING") as captured:
            warn_unmapped_metadata_leaves({"info": {"drift": 1}}, sname="S-ONE")
            warn_unmapped_metadata_leaves({"info": {"drift": 2}}, sname="S-ONE")
            warn_unmapped_metadata_leaves({"info": {"drift": 3}}, sname="S-TWO")
            warn_unmapped_metadata_leaves({"info": {"other": 4}}, sname="S-ONE")

        self.assertEqual(
            [(record.path, record.sname) for record in captured.records],
            [
                ("info.drift", "S-ONE"),
                ("info.drift", "S-TWO"),
                ("info.other", "S-ONE"),
            ],
        )

    def test_blank_sname_is_normalised_and_cache_reset_restores_emission(self):
        logger_name = "bilbyui.services.gwflow_metadata"
        payload = {"info": {"drift": 1}}
        with self.assertLogs(logger_name, level="WARNING") as first:
            warn_unmapped_metadata_leaves(payload, sname=" ")
        _reset_unmapped_warning_cache()
        with self.assertLogs(logger_name, level="WARNING") as second:
            warn_unmapped_metadata_leaves(payload, sname=None)

        self.assertEqual(first.records[0].sname, "unknown")
        self.assertEqual(second.records[0].sname, "unknown")


class InfoCompletenessTests(SimpleTestCase):
    def tearDown(self):
        _reset_unmapped_warning_cache()
        super().tearDown()

    def test_info_notes_nested_unknown_and_falsy_values_render_and_warn(self):
        payload = {
            "info": {
                "notes": "Complete notes",
                "status": "",
                "is_public": False,
                "review_count": 0,
                "upstream": {"nested": "Nested upstream value"},
            }
        }
        with self.assertLogs("bilbyui.services.gwflow_metadata", level="WARNING") as captured:
            warn_unmapped_metadata_leaves(payload, sname="S-INFO")

        presentation = build_metadata_presentation(payload)
        rendered = render_to_string(
            "bilbyui/_gwflow_metadata.html",
            {"payload": payload, "presentation": presentation, "stale": False},
        )

        self.assertIn("Complete notes", rendered)
        self.assertIn("Nested upstream value", rendered)
        self.assertIn(">0<", rendered)
        self.assertIn("✗ False", rendered)
        self.assertIn("&quot;&quot;", rendered)
        warned_paths = [record.path for record in captured.records]
        self.assertIn("info.upstream.nested", warned_paths)


class MetadataWarningViewIntegrationTests(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.request = RequestFactory().get("/")

    @mock.patch("bilbyui.views.build_metadata_presentation")
    @mock.patch("bilbyui.views.warn_unmapped_metadata_leaves")
    @mock.patch("bilbyui.views.get_superevent")
    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    def test_current_path_warns_immediately_before_build(
        self, get_job, get_superevent, warn, build
    ):
        payload = {"info": {"upstream": "visible"}}
        get_job.return_value = mock.Mock()
        get_superevent.return_value = (payload, "live")
        events = []
        warn.side_effect = lambda *args, **kwargs: events.append(("warn", args, kwargs))
        build.side_effect = lambda *args, **kwargs: events.append(("build", args, kwargs)) or mock.Mock()

        response, stale = _render_gwflow_metadata_section(self.request, "S-CURRENT")

        self.assertFalse(stale)
        self.assertEqual([event[0] for event in events], ["warn", "build"])
        warn.assert_called_once_with(payload, sname="S-CURRENT")
        self.assertEqual(response.context_data["payload"], payload)

    @mock.patch("bilbyui.views.build_metadata_presentation")
    @mock.patch("bilbyui.views.warn_unmapped_metadata_leaves")
    @mock.patch("bilbyui.views.get_version")
    @mock.patch("bilbyui.views._get_gwflow_job_or_404")
    def test_historical_path_warns_immediately_before_build(
        self, get_job, get_version, warn, build
    ):
        payload = {"info": {"upstream": "visible"}}
        get_job.return_value = mock.Mock()
        get_version.return_value = (payload, "live")
        events = []
        warn.side_effect = lambda *args, **kwargs: events.append(("warn", args, kwargs))
        build.side_effect = lambda *args, **kwargs: events.append(("build", args, kwargs)) or mock.Mock()

        response = gwflow_job_history_version_partial(
            self.request, "S-HISTORY", "version-1"
        )

        self.assertEqual([event[0] for event in events], ["warn", "build"])
        warn.assert_called_once_with(payload, sname="S-HISTORY")
        build.assert_called_once_with(payload, historical=True)
        self.assertEqual(response.context_data["payload"], payload)


class ProductionLoggingRoutingTests(SimpleTestCase):
    def test_service_warning_inherits_one_warning_capable_bilbyui_route(self):
        import os

        production_environment = {
            "GWOSC_INGEST_USER": "1",
            "GWFLOW_INGEST_USER": "1",
            "PERMITTED_EVENT_CREATION_USER_IDS": "[]",
            "CLUSTERS": "{}",
        }
        with mock.patch.dict(os.environ, production_environment):
            from gw_bilby.prod import LOGGING

        config = LOGGING["loggers"]["bilbyui"]
        self.assertEqual(config["level"], "INFO")
        self.assertFalse(config["propagate"])
        self.assertEqual(config["handlers"], ["console", "file", "error_file"])
        self.assertEqual(LOGGING["handlers"]["console"]["level"], "INFO")
        self.assertEqual(LOGGING["handlers"]["file"]["level"], "INFO")
        self.assertEqual(LOGGING["handlers"]["error_file"]["level"], "ERROR")

        service_logger = logging.getLogger("bilbyui.services.gwflow_metadata")
        self.assertTrue(service_logger.name.startswith("bilbyui."))
