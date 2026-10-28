"""Epic AC2: mixed integer/fractional numeric leaves map to ``double``.

This is an integration proof, not a mapping-shape test. It creates a temporary
index with the authoritative GWFlow mapping, indexes two documents carrying an
integer then a fraction (and the reverse) at the same canonical numeric path,
and asserts Elasticsearch maps that path to ``double`` in both ingestion
orders. It covers all four active metadata collections.

CI has no Elasticsearch service, so the test is skipped unless explicitly
enabled and the configured instance is reachable:

    GWFLOW_ES_INTEGRATION=1 .venv/bin/python manage.py \\
        test bilbyui.tests.test_gwflow_es_numeric_orders
"""

from __future__ import annotations

import os
import unittest
import uuid

from django.conf import settings
from django.test import SimpleTestCase
from elasticsearch import Elasticsearch

from bilbyui.utils.gwflow_es import build_gwflow_es_mapping

COLLECTIONS = (
    "analyses",
    "detector_configurations",
    "gracedb_events",
    "catalog_connections",
)


def _es():
    """Return a live client when integration mode is enabled and reachable."""
    if os.environ.get("GWFLOW_ES_INTEGRATION") != "1":
        return None
    try:
        client = Elasticsearch(hosts=[settings.ELASTIC_SEARCH_HOST], verify_certs=False)
        if not client.ping():
            return None
        return client
    except Exception:
        return None


class TestGWFlowNumericMappingOrders(SimpleTestCase):
    def setUp(self):
        self.es = _es()
        if self.es is None:
            self.skipTest("set GWFLOW_ES_INTEGRATION=1 with a reachable Elasticsearch")

    def test_integer_and_fraction_map_to_double_in_both_orders(self):
        mapping = build_gwflow_es_mapping()
        for collection in COLLECTIONS:
            for order in ((1, 1.5), (1.5, 1)):
                with self.subTest(collection=collection, order=order):
                    index = f"gwflow-numeric-{collection}-{uuid.uuid4().hex[:8]}"
                    try:
                        self.es.indices.create(index=index, body=mapping)
                        for value in order:
                            self.es.index(
                                index=index,
                                document={"metadata": {collection: [{"synthetic_numeric": value}]}},
                            )
                        self.es.indices.refresh(index=index)
                        installed = self.es.indices.get_mapping(index=index)[index]["mappings"]
                        field = installed["properties"]["metadata"]["properties"][collection]["properties"][
                            "synthetic_numeric"
                        ]
                        self.assertEqual(field["type"], "double")
                        self.assertEqual(self.es.count(index=index)["count"], 2)
                    finally:
                        self.es.indices.delete(index=index, ignore_unavailable=True)


if __name__ == "__main__":
    unittest.main()
