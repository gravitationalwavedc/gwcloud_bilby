from django.http import Http404
from django.test import override_settings
from graphql_relay.node.node import to_global_id

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.job_ref import parse_job_ref


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestParseJobRef(BilbyTestCase):
    def test_digit_id_returns_int_and_false(self):
        job_id, is_relay_id = parse_job_ref("42")

        self.assertEqual(job_id, 42)
        self.assertFalse(is_relay_id)

    def test_valid_bilby_job_node_relay_id(self):
        relay_id = to_global_id("BilbyJobNode", 123)

        job_id, is_relay_id = parse_job_ref(relay_id)

        self.assertEqual(job_id, 123)
        self.assertTrue(is_relay_id)

    def test_wrong_node_type_raises_404(self):
        relay_id = to_global_id("UserNode", 999)

        with self.assertRaises(Http404):
            parse_job_ref(relay_id)

    def test_invalid_pk_raises_404(self):
        relay_id = to_global_id("BilbyJobNode", "not-a-number")

        with self.assertRaises(Http404):
            parse_job_ref(relay_id)

    def test_malformed_relay_id_raises_404(self):
        with self.assertRaises(Http404):
            parse_job_ref("not-a-valid-relay-id")
