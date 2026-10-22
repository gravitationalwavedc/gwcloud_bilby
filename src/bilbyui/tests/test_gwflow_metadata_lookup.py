from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import build_metadata_presentation


class GWFlowMetadataLookupTests(SimpleTestCase):
    def _pe_row(self, analysis):
        presentation = build_metadata_presentation(
            {"analyses": [{"uid": "pe_1", "type": "pe", **analysis}]}
        )
        pe = next(section for section in presentation.sections if section.id == "pe")
        return {
            column.key: cell.raw_value
            for column, cell in zip(
                pe.comparative_sets[0].columns,
                pe.comparative_sets[0].rows[0].cells,
                strict=True,
            )
        }

    def test_nested_software_fields_resolve_for_populated_null_and_missing_values(self):
        populated = self._pe_row(
            {"software": {"name": "bilby_pipe", "version": "1.2.0"}}
        )
        self.assertEqual(populated["software.name"], "bilby_pipe")
        self.assertEqual(populated["software.version"], "1.2.0")

        for analysis in ({"software": None}, {}):
            with self.subTest(analysis=analysis):
                row = self._pe_row(analysis)
                self.assertIsNone(row["software.name"])
                self.assertIsNone(row["software.version"])

    def test_pe_filter_keeps_pe_and_drops_event_validation(self):
        presentation = build_metadata_presentation(
            {
                "analyses": [
                    {
                        "uid": "S000001a-validation-report",
                        "type": "event_validation",
                        "software": None,
                    },
                    {
                        "uid": "pe_1",
                        "type": "pe",
                        "software": {"name": "bilby_pipe", "version": "1.2.0"},
                    },
                ]
            }
        )
        pe = next(section for section in presentation.sections if section.id == "pe")
        self.assertEqual(
            [row.identity for row in pe.comparative_sets[0].rows],
            ["pe_1"],
        )

        validation_only = build_metadata_presentation(
            {
                "analyses": [
                    {
                        "uid": "S000001a-validation-report",
                        "type": "event_validation",
                    }
                ]
            }
        )
        self.assertNotIn("pe", [section.id for section in validation_only.sections])

    def test_canonical_selector_cannot_be_shadowed_by_unknown_root_key(self):
        presentation = build_metadata_presentation(
            {
                "GraceDB": {
                    "events": [{"event_name": "UNKNOWN-SHADOW"}],
                },
                "gracedb_events": [{"event_name": "G000001"}],
            }
        )

        self.assertEqual(
            [section.id for section in presentation.sections],
            ["gracedb", "unknown:GraceDB"],
        )
        gracedb = presentation.sections[0]
        self.assertEqual(
            [row.identity for row in gracedb.comparative_sets[0].rows],
            ["G000001"],
        )
        self.assertEqual(presentation.sections[1].source_key, "GraceDB")
