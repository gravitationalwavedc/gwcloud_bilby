"""Shape checks for the deterministic GWFlow pathological fixtures."""

from bilbyui.services.gwflow_metadata import build_metadata_presentation
from bilbyui.tests.e2e.pathological_fixtures import (
    METADATA_COLUMN_COUNT,
    PATH_LENGTH,
    SUPEREVENT_EVENT_COUNT,
    VERSION_COUNT,
    build_pathological_fixtures,
)
from bilbyui.tests.testcases import BilbyTestCase


class PathologicalFixturesTests(BilbyTestCase):
    def test_factories_build_required_pathological_shapes(self):
        fixtures = build_pathological_fixtures(type(self))

        self.assertEqual(len(fixtures["file"].path), PATH_LENGTH)
        self.assertEqual(fixtures["file"].path, "p" * PATH_LENGTH)

        events = fixtures["superevent"]["gracedb"]["events"]
        self.assertEqual(len(events), SUPEREVENT_EVENT_COUNT)

        metadata = fixtures["metadata"]
        event = metadata["gracedb"]["events"][0]
        self.assertEqual(len(event), METADATA_COLUMN_COUNT)
        presentation = build_metadata_presentation(metadata)
        gracedb = next(section for section in presentation.sections if section.id == "gracedb")
        self.assertEqual(len(gracedb.comparative_sets[0].columns), METADATA_COLUMN_COUNT)

        versions = fixtures["versions"]
        self.assertEqual(len(versions), VERSION_COUNT)
        self.assertEqual(sum(version["is_current"] for version in versions), 1)
        self.assertTrue(
            all(
                {"commit_sha", "commit_timestamp", "schema_version", "is_current", "payload"} <= version.keys()
                for version in versions
            )
        )
