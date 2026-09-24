from django.test import SimpleTestCase

from bilbyui.services.gwflow_metadata import build_metadata_presentation


def _disclosure_paths(payload):
    presentation = build_metadata_presentation(payload)
    section = next(section for section in presentation.sections if section.id == "lensing")
    return {node.path for node in section.disclosure}


class GWFlowMetadataLookupDefensiveTests(SimpleTestCase):
    def test_non_list_value_for_record_list_path_drops_the_field(self):
        paths = _disclosure_paths({"lensing": {"multiplet_groups": "not-a-list"}})
        self.assertNotIn("lensing.multiplet_groups[].companion_sname", paths)

    def test_non_mapping_record_in_record_list_path_drops_the_field(self):
        paths = _disclosure_paths({"lensing": {"multiplet_groups": ["not-a-dict"]}})
        self.assertNotIn("lensing.multiplet_groups[].companion_sname", paths)
