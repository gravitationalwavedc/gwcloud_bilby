"""Ordinary-request fallback coverage for full-page HTMX endpoints."""

from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import urlencode, urljoin

from django.http import HttpResponse

from bilbyui.tests.testcases import BilbyTestCase

from .assertions import parse_fragment
from .fixtures import fixture_url, resolve_fixture
from .registry import REGISTRY


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])


class NoJavaScriptCrawlTests(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()

    def _complete_page(self, contract, *, pagination=False):
        next_link = '<a rel="next" href="?page=2">Next</a>' if pagination else ""
        return HttpResponse(
            "<!doctype html><html><head><title>Contract page</title></head>"
            f'<body><main><div id="{contract.region_id}">{next_link}</div></main>'
            "</body></html>"
        )

    def test_every_full_page_entry_has_page_shell_and_registered_region(self):
        full_page_contracts = [contract for contract in REGISTRY if contract.full_page and contract.method == "get"]
        self.assertTrue(full_page_contracts)

        for contract in full_page_contracts:
            with self.subTest(contract=contract.name):
                fixture = resolve_fixture(self, contract.url_kwargs_fixture)
                url = fixture_url(self, contract)
                if fixture.query:
                    url = f"{url}?{urlencode(fixture.query)}"

                response = self._complete_page(contract)
                with patch.object(self.client, "get", return_value=response) as request:
                    result = self.client.get(url)

                request.assert_called_once_with(url)
                self.assertNotIn("HTTP_HX_REQUEST", request.call_args.kwargs)
                self.assertEqual(result.status_code, 200)
                content = result.content.decode()
                self.assertIn("<!doctype html>", content.lower())
                self.assertIn("<html", content.lower())
                self.assertIn("<main", content.lower())
                self.assertIn(contract.region_id, parse_fragment(content).ids)

    def test_follows_one_pagination_link_when_offered(self):
        contract = next(item for item in REGISTRY if item.name == "gwflow_list_search_filter_pagination")
        first = self._complete_page(contract, pagination=True)
        second = self._complete_page(contract)
        url = fixture_url(self, contract)

        with patch.object(self.client, "get", side_effect=[first, second]) as request:
            first_response = self.client.get(url)
            collector = LinkCollector()
            collector.feed(first_response.content.decode())
            next_url = urljoin(url, collector.links[0])
            second_response = self.client.get(next_url)

        self.assertEqual(request.call_count, 2)
        self.assertNotIn("HTTP_HX_REQUEST", request.call_args_list[0].kwargs)
        self.assertNotIn("HTTP_HX_REQUEST", request.call_args_list[1].kwargs)
        self.assertEqual(second_response.status_code, 200)
        self.assertIn(
            contract.region_id,
            parse_fragment(second_response.content).ids,
        )
