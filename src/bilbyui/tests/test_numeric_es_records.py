from django.test import SimpleTestCase

from bilbyui.services.jobs import _numeric_es_records


class TestNumericEsRecords(SimpleTestCase):
    def test_keeps_int_id(self):
        record = {"_id": 123, "source": "job"}
        self.assertEqual(_numeric_es_records([record]), [record])

    def test_normalizes_numeric_string_id(self):
        record = {"_id": "123", "source": "job"}
        self.assertEqual(_numeric_es_records([record]), [{"_id": 123, "source": "job"}])

    def test_drops_non_numeric_string_id(self):
        record = {"_id": "corrupt-non-numeric-id"}
        self.assertEqual(_numeric_es_records([record]), [])

    def test_drops_missing_id(self):
        record = {"_source": {"job": "missing-id-hit"}}
        self.assertEqual(_numeric_es_records([record]), [])

    def test_drops_none_id(self):
        record = {"_id": None}
        self.assertEqual(_numeric_es_records([record]), [])

    def test_drops_non_dict_records(self):
        records = [{"_id": 1}, "corrupt-non-dict-hit", 42, None]
        self.assertEqual(_numeric_es_records(records), [{"_id": 1}])

    def test_mixed_records_keeps_only_numeric_dicts(self):
        kept = {"_id": 7}
        records = [
            kept,
            {"_id": "8"},
            {"_id": "not-a-number"},
            {"_id": None},
            "string",
        ]
        self.assertEqual(_numeric_es_records(records), [kept, {"_id": 8}])
