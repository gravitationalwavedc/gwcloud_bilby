from django.test import override_settings

from bilbyui.models import _safe_json_loads
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestSafeJsonLoads(BilbyTestCase):
    def test_valid_json_parses(self):
        self.assertEqual(_safe_json_loads('{"a": 1}'), {"a": 1})
        self.assertEqual(_safe_json_loads("[1, 2]"), [1, 2])
        self.assertEqual(_safe_json_loads('"text"'), "text")

    def test_malformed_json_returns_none(self):
        self.assertIsNone(_safe_json_loads("not-json{{"))
        self.assertIsNone(_safe_json_loads("{unclosed"))

    def test_none_returns_none(self):
        self.assertIsNone(_safe_json_loads(None))

    def test_non_string_inputs_return_none(self):
        self.assertIsNone(_safe_json_loads(123))
        self.assertIsNone(_safe_json_loads({"a": 1}))
        self.assertIsNone(_safe_json_loads(["a"]))
