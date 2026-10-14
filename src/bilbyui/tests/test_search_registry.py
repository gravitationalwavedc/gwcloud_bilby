from django.test import SimpleTestCase

from bilbyui.services.search_registry import (
    BILBY_GROUPS,
    GWFLOW_GROUPS,
    SEARCH_FIELDS,
    common_fields,
    grouped_fields,
    is_denied,
    typed_note,
)


class TestSearchRegistry(SimpleTestCase):
    required_schema = {
        "surface",
        "path",
        "advertised",
        "description",
        "group",
        "tier",
        "visibility",
        "example",
        "type_hint",
    }

    def test_both_surfaces_are_covered_with_uniform_schema(self):
        self.assertEqual({entry["surface"] for entry in SEARCH_FIELDS}, {"gwflow", "bilby"})
        for entry in SEARCH_FIELDS:
            self.assertEqual(set(entry), self.required_schema)
            self.assertIn(entry["visibility"], {"common", "full"})
            self.assertIsInstance(entry["tier"], int)

    def test_exactly_four_common_fields_per_surface(self):
        self.assertEqual(
            [entry["advertised"] for entry in common_fields("gwflow")],
            [
                "sname",
                "review_statuses",
                "metadata.pe.results.waveform_approximant",
                "metadata.gracedb.events.network_snr",
            ],
        )
        self.assertEqual(
            [entry["advertised"] for entry in common_fields("bilby")],
            [
                "job.name",
                "eventId.eventId",
                "params.waveform_approximant",
                "labels.name",
            ],
        )

    def test_all_approved_groups_are_returned_in_order(self):
        self.assertEqual(
            [group["name"] for group in grouped_fields("gwflow")],
            list(GWFLOW_GROUPS),
        )
        self.assertEqual(
            [group["name"] for group in grouped_fields("bilby")],
            list(BILBY_GROUPS),
        )

    def test_seven_gwflow_aliases_map_to_canonical_envelope_paths(self):
        expected = {
            "sname": "_gwcloud.sname",
            "libraries": "_gwcloud.libraries",
            "review_statuses": "_gwcloud.reviewStatuses",
            "event_trigger_id": "_gwcloud.eventTriggerId",
            "search_trigger_time": "_gwcloud.searchTriggerTime",
            "last_updated_time": "_gwcloud.lastUpdatedTime",
            "is_pruned": "_gwcloud.isPruned",
        }
        actual = {
            entry["advertised"]: entry["path"]
            for entry in SEARCH_FIELDS
            if entry["surface"] == "gwflow" and str(entry["path"]).startswith("_gwcloud.")
        }
        self.assertEqual(actual, expected)

    def test_deny_policy_covers_restricted_and_operational_paths(self):
        denied = (
            "_id",
            "_routing",
            "_doc_count",
            "_index",
            "_nested_path",
            "_ignored",
            "_field_names",
            "_feature",
            "_data_stream_timestamp",
            "metadata.raw_payload.secret",
            "metadata.value.__gwcloud_type__",
            "metadata.__gwcloud_schema__.version",
            "_private_info_.token",
            "user.email",
            "ini.email",
            "ini.accounting_user",
            "params.meta_data.command_line_args.token",
            "result.path",
            "result.md5_sum",
            "result.public_html",
            "result.date_last_modified",
            "result.xml",
            "result.frame_file",
        )
        for path in denied:
            with self.subTest(path=path):
                self.assertTrue(is_denied(path))

        advertised_paths = {entry["path"] for entry in SEARCH_FIELDS}
        self.assertFalse(any(is_denied(str(path)) for path in advertised_paths))

    def test_bilby_ini_fields_are_listed(self):
        ini_paths = {
            entry["path"]
            for entry in SEARCH_FIELDS
            if entry["surface"] == "bilby" and str(entry["path"]).startswith("ini.")
        }
        self.assertEqual(ini_paths, {"ini.conda_env", "ini.psd_dict", "ini.sampler"})
        self.assertIn("ini.sampler", ini_paths)

    def test_accessors_return_plain_independent_values(self):
        common = common_fields("gwflow")
        common[0]["description"] = "changed"
        self.assertNotEqual(common_fields("gwflow")[0]["description"], "changed")

        groups = grouped_fields("bilby")
        self.assertIsInstance(groups, list)
        self.assertIsInstance(groups[0], dict)
        self.assertIsInstance(groups[0]["fields"], list)
        self.assertIn("exact values and ranges", typed_note("bilby"))

    def test_unknown_surface_is_rejected(self):
        with self.assertRaises(ValueError):
            common_fields("unknown")
        with self.assertRaises(ValueError):
            grouped_fields("unknown")
        with self.assertRaises(ValueError):
            typed_note("unknown")
