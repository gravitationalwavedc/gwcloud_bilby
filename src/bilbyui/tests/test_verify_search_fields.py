from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.management import CommandError, call_command

from bilbyui.management.commands.verify_search_fields import (
    GWFLOW_ALIASES,
    NUMERIC_TYPES,
)
from bilbyui.services.search_registry import SEARCH_FIELDS
from bilbyui.tests.testcases import BilbyTestCase

COMMAND = "bilbyui.management.commands.verify_search_fields"


def _es_type(type_hint):
    return {
        "number": "double",
        "date": "date",
        "boolean": "boolean",
        "term": "keyword",
        "text": "text",
    }.get(type_hint, "keyword")


def _insert(properties, path, definition):
    parts = path.split(".")
    node = properties
    for part in parts[:-1]:
        node = node.setdefault(part, {"properties": {}})["properties"]
    node[parts[-1]] = definition


def _surface_properties(surface):
    properties = {}
    for entry in SEARCH_FIELDS:
        if entry["surface"] == surface:
            _insert(
                properties,
                str(entry["path"]),
                {"type": _es_type(entry.get("type_hint"))},
            )

    defaults = (
        [
            "_gwcloud.sname",
            "_gwcloud.eventTriggerId",
            "_gwcloud.libraries",
            "_gwcloud.reviewStatuses",
            "metadata.gracedb.events.uid",
            "metadata.pe.results.uid",
            "metadata.pe.results.inference_software",
            "metadata.pe.results.waveform_approximant",
            "metadata.pe.results.run_status",
            "metadata.pe.results.review_status",
            "metadata.pe.status",
            "metadata.gracedb.events.pipeline",
            "metadata.gracedb.events.state",
            "metadata.gracedb.instruments",
        ]
        if surface == "gwflow"
        else [
            "job.name",
            "job.description",
            "labels.name",
            "labels.description",
            "eventId.eventId",
            "eventId.triggerId",
            "eventId.nickname",
            "params.label",
            "params.waveform_approximant",
            "params.likelihood_type",
            "params.detectors",
            "params.frequency_domain_source_model",
            "params.meta_data.bilby_version",
            "params.meta_data.bilby_pipe_version",
            "ini.sampler",
        ]
    )
    for path in defaults:
        _insert(properties, path, {"type": "keyword"})

    if surface == "gwflow":
        for alias, target in GWFLOW_ALIASES.items():
            properties[alias] = {"type": "alias", "path": target}
    return properties


def _delete(properties, path):
    parts = path.split(".")
    node = properties
    for part in parts[:-1]:
        node = node[part]["properties"]
    del node[parts[-1]]


class VerifySearchFieldsTests(BilbyTestCase):
    def _run(
        self,
        *,
        gwflow=None,
        bilby=None,
        surface=None,
        live_defaults=None,
        omit_live_defaults=False,
    ):
        mappings = {
            settings.ELASTIC_SEARCH_GWFLOW_INDEX: {"mappings": {"properties": gwflow or _surface_properties("gwflow")}},
            settings.ELASTIC_SEARCH_INDEX: {"mappings": {"properties": bilby or _surface_properties("bilby")}},
        }
        configured_defaults = {
            settings.ELASTIC_SEARCH_GWFLOW_INDEX: [
                "_gwcloud.sname",
                "_gwcloud.eventTriggerId",
                "_gwcloud.libraries",
                "_gwcloud.reviewStatuses",
                "metadata.gracedb.events.uid",
                "metadata.pe.results.uid",
                "metadata.pe.results.inference_software",
                "metadata.pe.results.waveform_approximant",
                "metadata.pe.results.run_status",
                "metadata.pe.results.review_status",
                "metadata.pe.status",
                "metadata.gracedb.events.pipeline",
                "metadata.gracedb.events.state",
                "metadata.gracedb.instruments",
            ],
            settings.ELASTIC_SEARCH_INDEX: [
                "job.name",
                "job.description",
                "labels.name",
                "labels.description",
                "eventId.eventId",
                "eventId.triggerId",
                "eventId.nickname",
                "params.label",
                "params.waveform_approximant",
                "params.likelihood_type",
                "params.detectors",
                "params.frequency_domain_source_model",
                "params.meta_data.bilby_version",
                "params.meta_data.bilby_pipe_version",
                "ini.sampler",
            ],
        }
        es = mock.MagicMock()
        es.indices.get_mapping.side_effect = lambda *, index: {index: mappings[index]}

        def get_settings(*, index):
            if omit_live_defaults:
                return {index: {"settings": {}}}
            defaults = live_defaults if live_defaults is not None else configured_defaults[index]
            return {index: {"settings": {"index": {"query": {"default_field": defaults}}}}}

        es.indices.get_settings.side_effect = get_settings
        output = StringIO()
        args = ["--surface", surface] if surface else []
        with mock.patch(f"{COMMAND}.get_es_client", return_value=es):
            try:
                code = call_command(
                    "verify_search_fields",
                    *args,
                    stdout=output,
                )
            except CommandError as error:
                code = error.returncode
        return code, output.getvalue(), es

    def test_clean_both_surfaces_exit_zero(self):
        code, output, es = self._run()

        self.assertEqual(code, 0)
        self.assertIn("Summary: failures=0, triage=0", output)
        self.assertEqual(es.indices.get_mapping.call_count, 2)

    def test_surface_argument_checks_only_requested_surface(self):
        code, _, es = self._run(surface="bilby")

        self.assertEqual(code, 0)
        es.indices.get_mapping.assert_called_once_with(index=settings.ELASTIC_SEARCH_INDEX)

    def test_matching_live_default_fields_do_not_fail(self):
        code, output, es = self._run(surface="bilby")

        self.assertEqual(code, 0)
        self.assertNotIn("live default_field mismatch", output)
        es.indices.get_settings.assert_called_once_with(index=settings.ELASTIC_SEARCH_INDEX)

    def test_extra_live_default_field_fails(self):
        defaults = [
            "job.name",
            "job.description",
            "labels.name",
            "labels.description",
            "eventId.eventId",
            "eventId.triggerId",
            "eventId.nickname",
            "params.label",
            "params.waveform_approximant",
            "params.likelihood_type",
            "params.detectors",
            "params.frequency_domain_source_model",
            "params.meta_data.bilby_version",
            "params.meta_data.bilby_pipe_version",
            "ini.sampler",
            "unexpected.extra",
        ]

        code, output, _ = self._run(
            surface="bilby",
            live_defaults=defaults,
        )

        self.assertEqual(code, 1)
        self.assertIn("FAIL live default_field mismatch:", output)
        self.assertIn("unexpected.extra", output)

    def test_missing_live_default_field_fails(self):
        defaults = [
            "job.name",
            "job.description",
            "labels.name",
            "labels.description",
            "eventId.eventId",
            "eventId.triggerId",
            "eventId.nickname",
            "params.label",
            "params.waveform_approximant",
            "params.likelihood_type",
            "params.detectors",
            "params.frequency_domain_source_model",
            "params.meta_data.bilby_version",
            "params.meta_data.bilby_pipe_version",
        ]

        code, output, _ = self._run(
            surface="bilby",
            live_defaults=defaults,
        )

        self.assertEqual(code, 1)
        self.assertIn("FAIL live default_field mismatch:", output)
        self.assertIn("ini.sampler", output)

    def test_no_live_default_field_setting_fails(self):
        code, output, _ = self._run(
            surface="bilby",
            omit_live_defaults=True,
        )

        self.assertEqual(code, 1)
        self.assertIn("FAIL live default_field mismatch:", output)
        self.assertIn("live []", output)

    def test_missing_documented_field_fails(self):
        properties = _surface_properties("bilby")
        _delete(properties, "params.minimum_frequency")

        code, output, _ = self._run(bilby=properties, surface="bilby")

        self.assertEqual(code, 1)
        self.assertIn(
            "FAIL documented field missing: params.minimum_frequency",
            output,
        )

    def test_missing_required_alias_fails(self):
        properties = _surface_properties("gwflow")
        del properties["review_statuses"]

        code, output, _ = self._run(gwflow=properties, surface="gwflow")

        self.assertEqual(code, 1)
        self.assertIn("FAIL required GWFlow alias missing: review_statuses", output)

    def test_changed_alias_target_fails(self):
        properties = _surface_properties("gwflow")
        properties["sname"]["path"] = "_gwcloud.eventTriggerId"

        code, output, _ = self._run(gwflow=properties, surface="gwflow")

        self.assertEqual(code, 1)
        self.assertIn("FAIL GWFlow alias target changed: sname", output)

    def test_unexpected_camelcase_alias_fails(self):
        properties = _surface_properties("gwflow")
        properties["reviewStatuses"] = {
            "type": "alias",
            "path": "_gwcloud.reviewStatuses",
        }

        code, output, _ = self._run(gwflow=properties, surface="gwflow")

        self.assertEqual(code, 1)
        self.assertIn(
            "FAIL unexpected bare camelCase compatibility alias: reviewStatuses",
            output,
        )

    def test_missing_default_field_fails(self):
        properties = _surface_properties("bilby")
        _delete(properties, "params.label")

        code, output, _ = self._run(bilby=properties, surface="bilby")

        self.assertEqual(code, 1)
        self.assertIn(
            "FAIL configured default_field missing: params.label",
            output,
        )

    def test_syntax_relevant_type_change_fails(self):
        properties = _surface_properties("bilby")
        node = properties["params"]["properties"]
        node["sampling_frequency"] = {"type": "keyword"}

        code, output, _ = self._run(bilby=properties, surface="bilby")

        self.assertEqual(code, 1)
        self.assertIn(
            "FAIL syntax-relevant type changed: params.sampling_frequency expects number, live type is keyword",
            output,
        )
        self.assertIn("double", NUMERIC_TYPES)

    def test_uncatalogued_eligible_field_is_triage_only(self):
        properties = _surface_properties("bilby")
        _insert(properties, "params.new_public_metric", {"type": "double"})

        code, output, _ = self._run(bilby=properties, surface="bilby")

        self.assertEqual(code, 0)
        self.assertIn(
            "TRIAGE eligible live field is not in the registry: params.new_public_metric",
            output,
        )
        self.assertIn("Summary: failures=0, triage=1", output)

    def test_denied_live_field_is_ignored(self):
        properties = _surface_properties("bilby")
        _insert(properties, "ini.email", {"type": "keyword"})
        _insert(properties, "params.output.path", {"type": "keyword"})

        code, output, _ = self._run(bilby=properties, surface="bilby")

        self.assertEqual(code, 0)
        self.assertIn("Summary: failures=0, triage=0", output)
        self.assertNotIn("ini.email", output)
        self.assertNotIn("params.output.path", output)

    def test_live_default_fields_accepts_resolved_index_key(self):
        from bilbyui.management.commands import verify_search_fields as vsf

        class _Indices:
            def get_settings(self, *, index):
                return {"resolved-concrete-index": {"settings": {"index": {"query": {"default_field": ["a", "b"]}}}}}

        class _Client:
            indices = _Indices()

        self.assertEqual(
            vsf._live_default_fields(_Client(), "gwcloud-bilbyjob"),
            ("a", "b"),
        )

    def test_live_default_fields_handles_non_mapping_response(self):
        # elastic_transport.ObjectApiResponse is dict-like but is NOT a
        # collections.abc.Mapping; parsing must not rely on isinstance.
        from bilbyui.management.commands import verify_search_fields as vsf

        class _Resp:
            def __init__(self, data):
                self._data = data

            def get(self, key, default=None):
                return self._data.get(key, default)

            def values(self):
                return self._data.values()

            def __len__(self):
                return len(self._data)

        class _Indices:
            def get_settings(self, *, index):
                return _Resp({"gwcloud-bilbyjob": {"settings": {"index": {"query": {"default_field": ["x", "y"]}}}}})

        class _Client:
            indices = _Indices()

        self.assertFalse(isinstance(_Resp({}), __import__("collections.abc", fromlist=["Mapping"]).Mapping))
        self.assertEqual(
            vsf._live_default_fields(_Client(), "gwcloud-bilbyjob"),
            ("x", "y"),
        )
