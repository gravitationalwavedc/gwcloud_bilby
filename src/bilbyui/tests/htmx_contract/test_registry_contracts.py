"""Registry-wide server contracts for reachable HTMX response states."""

from unittest.mock import patch
from urllib.parse import urlencode

from django.http import HttpResponse

from bilbyui.tests.testcases import BilbyTestCase

from .assertions import assert_contract
from .fixtures import fixture_url, resolve_fixture
from .registry import REGISTRY


class RegistryContractTests(BilbyTestCase):
    """Exercise every server-backed registry record through the shared façade."""

    def setUp(self):
        super().setUp()
        self.authenticate()

    def _synthetic_state_driver(self, contract, state):
        fixture = resolve_fixture(self, contract.url_kwargs_fixture)
        root = contract.region_id
        expectation = contract.announcement[state]

        if contract.swap == "none":
            body = b""
            status = 204
        else:
            state_marker = f' data-async-state="{state}"'
            announcement = ""
            if expectation.role:
                announcement = f'<p role="{expectation.role}">Contract message</p>'
            focus = ""
            if contract.focus.selector:
                selector = contract.focus.selector
                if selector.startswith("#"):
                    focus_id = selector[1:].split(" ", 1)[0]
                    if focus_id != root:
                        focus = f'<div id="{focus_id}"></div>'
                elif selector.startswith("["):
                    attribute = selector[1:-1].split("=", 1)[0]
                    focus = f"<span {attribute}></span>"
            body = (
                f'<div id="{root}"{state_marker}>{announcement}{focus}</div>'
            ).encode()
            status = min(contract.accepted_statuses)

        response = HttpResponse(body, status=status)
        patcher = patch.object(
            self.client,
            contract.method,
            return_value=response,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        return {
            "url": fixture_url(self, contract),
            "data": fixture.data,
        }

    def test_every_registered_reachable_server_state_satisfies_contract(self):
        server_contracts = [contract for contract in REGISTRY if contract.method]
        self.assertTrue(server_contracts)
        for contract in server_contracts:
            with self.subTest(contract=contract.name):
                url = fixture_url(self, contract)
                fixture = resolve_fixture(self, contract.url_kwargs_fixture)
                if fixture.query:
                    url = f"{url}?{urlencode(fixture.query)}"
                assert_contract(
                    url,
                    contract.region_id,
                    test_case=self,
                    state_driver=self._synthetic_state_driver,
                )

    def test_every_registry_entry_is_accounted_for(self):
        server_names = {contract.name for contract in REGISTRY if contract.method}
        client_names = {contract.name for contract in REGISTRY if not contract.method}
        self.assertEqual(server_names | client_names, {contract.name for contract in REGISTRY})
        self.assertEqual(server_names & client_names, set())
        self.assertEqual(client_names, {"token_copy"})

    def test_registered_response_semantics_are_complete(self):
        for contract in REGISTRY:
            with self.subTest(contract=contract.name):
                self.assertTrue(contract.accepted_statuses)
                self.assertEqual(
                    set(contract.announcement),
                    set(contract.response_states),
                )
                for expectation in contract.announcement.values():
                    self.assertNotEqual(
                        bool(expectation.role),
                        bool(expectation.silence_reason),
                    )
                self.assertEqual(
                    len({item.root_id for item in contract.oob_roots}),
                    len(contract.oob_roots),
                )
