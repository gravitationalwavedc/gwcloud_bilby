"""Registry contracts driven through production Django views.

The portal-backed detail metadata and history/version families use real URL
resolution, authentication, database visibility checks, view branching, and
template rendering. Only the external portal functions are patched. Each
reachable response branch is driven through the shared ``assert_contract``
façade, so status, fragment shape, state markers, announcements, focus and retry
semantics all come from the one registry oracle.

The files family is covered by focused HTTP tests: a "content" response can
contain one empty per-analysis fragment, so its announcement cardinality is
fixture-dependent rather than a single contract invariant. The empty branch does
flow through ``assert_response_contract``.

Other registry families are covered by their focused HTTP tests and registry
schema/audit tests. They are deliberately not represented by fabricated HTML
here: several registered states describe browser lifecycle behaviour or
validation scenarios rather than a single server-boundary state.
"""

from unittest.mock import patch
from urllib.parse import urlencode

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS

from bilbyui.tests.testcases import BilbyTestCase

from .assertions import assert_contract, assert_response_contract, parse_fragment
from .fixtures import fixture_url, resolve_fixture
from .registry import REGISTRY

PORTAL_CONTRACTS = {
    "gwflow_detail_metadata",
    "gwflow_detail_history",
    "gwflow_version_select_compare",
}

LIVE_METADATA = {
    "schema_version": "v3",
    "commit_sha": "contract-history",
    "gracedb": {"events": [{"uid": "E-CONTRACT", "pipeline": "gstlal"}]},
}
CONTENT_METADATA = {
    "schema_version": "v3",
    "commit_sha": "contract-history",
    "gracedb": {"events": [{"uid": "E-CONTRACT", "pipeline": "gstlal"}]},
    "ParameterEstimation": [
        {
            "uid": "U-CONTRACT",
            "inference_software": "bilby",
            "waveform_approximant": "IMRPhenomD",
            "run_status": "complete",
        }
    ],
}
LIVE_VERSIONS = [
    {
        "commit_sha": "contract-history",
        "commit_timestamp": "2026-09-18 00:00:00 UTC",
        "schema_version": "v3",
        "is_current": True,
    }
]
LIVE_VERSION = {
    "schema_version": "v3",
    "commit_sha": "contract-history",
    "commit_timestamp": "2026-09-18 00:00:00 UTC",
    "gracedb": {"events": [{"uid": "E-CONTRACT", "pipeline": "gstlal"}]},
    "raw_payload": CONTENT_METADATA,
}

# contract name -> response state -> {view function: return value}
PORTAL_STATE_PATCHES = {
    "gwflow_detail_metadata": {
        "content": {"get_superevent": (CONTENT_METADATA, "live")},
        "empty": {"get_superevent": (None, "live")},
        "stale": {"get_superevent": (CONTENT_METADATA, "stale")},
        "error": {"get_superevent": (None, "down")},
    },
    "gwflow_detail_history": {
        "content": {
            "get_versions": (LIVE_VERSIONS, "live"),
            "get_version": (LIVE_VERSION, "live"),
        },
        "empty": {"get_versions": ([], "live")},
        "stale": {
            "get_versions": (LIVE_VERSIONS, "stale"),
            "get_version": (LIVE_VERSION, "stale"),
        },
        "error": {"get_versions": (None, "down")},
    },
    "gwflow_version_select_compare": {
        "content": {
            "get_versions": (LIVE_VERSIONS, "live"),
            "get_version": (LIVE_VERSION, "live"),
        },
        "empty": {"get_versions": ([], "live")},
        "stale": {
            "get_versions": (LIVE_VERSIONS, "stale"),
            "get_version": (LIVE_VERSION, "stale"),
        },
        "error": {"get_versions": (None, "down")},
    },
}


class RegistryContractTests(BilbyTestCase):
    """Exercise reachable portal response branches through production views."""

    def setUp(self):
        super().setUp()
        user = self.create_user(
            id=60,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=user)

    def _contract(self, name):
        return next(contract for contract in REGISTRY if contract.name == name)

    def _url_for(self, contract):
        fixture = resolve_fixture(self, contract.url_kwargs_fixture)
        url = fixture_url(self, contract)
        if fixture.query:
            url = f"{url}?{urlencode(fixture.query)}"
        return fixture, url

    def _request(self, contract):
        fixture, url = self._url_for(contract)
        return self.client.get(url, fixture.data, HTTP_HX_REQUEST="true")

    def _portal_state_driver(self, contract, state):
        """Patch only the external portal boundary for one real response state.

        Patchers stay started until clean-up so they remain active during the
        request that ``execute_contract`` issues after this returns.
        """
        fixture, url = self._url_for(contract)
        for target, value in PORTAL_STATE_PATCHES[contract.name][state].items():
            patcher = patch(f"bilbyui.views.{target}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        return {"url": url, "data": fixture.data}

    def test_metadata_real_states_satisfy_contract(self):
        contract = self._contract("gwflow_detail_metadata")
        _, url = self._url_for(contract)
        assert_contract(
            url,
            contract.region_id,
            test_case=self,
            state_driver=self._portal_state_driver,
        )

    def test_history_real_states_satisfy_contract(self):
        contract = self._contract("gwflow_detail_history")
        _, url = self._url_for(contract)
        assert_contract(
            url,
            contract.region_id,
            test_case=self,
            state_driver=self._portal_state_driver,
        )

    def test_version_real_states_satisfy_contract(self):
        contract = self._contract("gwflow_version_select_compare")
        _, url = self._url_for(contract)
        assert_contract(
            url,
            contract.region_id,
            test_case=self,
            state_driver=self._portal_state_driver,
        )

    def test_metadata_content_evidence(self):
        contract = self._contract("gwflow_detail_metadata")
        with patch("bilbyui.views.get_superevent", return_value=(LIVE_METADATA, "live")):
            response = self._request(contract)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "E-CONTRACT")
        assert_response_contract(self, contract, response, state="content")

    def test_history_content_evidence(self):
        contract = self._contract("gwflow_detail_history")
        with (
            patch("bilbyui.views.get_versions", return_value=(LIVE_VERSIONS, "live")),
            patch("bilbyui.views.get_version", return_value=(LIVE_VERSION, "live")),
        ):
            response = self._request(contract)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="gwflow-history-region"')
        assert_response_contract(self, contract, response, state="content")

    def test_files_content_renders_analysis_blocks(self):
        contract = self._contract("gwflow_detail_files")
        with patch(
            "bilbyui.views.get_superevent",
            return_value=(CONTENT_METADATA, "live"),
        ):
            response = self._request(contract)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gw-analysis-block")
        self.assertContains(response, "U-CONTRACT")

    def test_files_empty_flows_through_contract_assertion(self):
        contract = self._contract("gwflow_detail_files")
        with patch("bilbyui.views.get_superevent", return_value=(None, "live")):
            response = self._request(contract)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-empty")
        assert_response_contract(self, contract, response, state="empty")

    def test_event_id_modal_open_target_resolves_to_response_root(self):
        contract = self._contract("event_id_modal_open")
        fixture = resolve_fixture(self, contract.url_kwargs_fixture)
        response = self.client.get(fixture_url(self, contract), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        parser = parse_fragment(response.content)
        expected = contract.region_id.replace(
            "{job_id}", str(fixture.kwargs["job_id"])
        )
        self.assertEqual(parser.start_tags[0][1].get("id"), expected)

    def test_server_executor_scope_is_explicit_and_non_synthetic(self):
        names = {contract.name for contract in REGISTRY}
        self.assertLessEqual(PORTAL_CONTRACTS, names)
        server_names = {contract.name for contract in REGISTRY if contract.method}
        client_names = {contract.name for contract in REGISTRY if contract.method is None}
        self.assertEqual(server_names | client_names, names)
        self.assertEqual(server_names & client_names, set())
        self.assertEqual(client_names, {"token_copy"})

    def test_registered_response_semantics_are_complete(self):
        for contract in REGISTRY:
            with self.subTest(contract=contract.name):
                self.assertTrue(contract.accepted_statuses)
                self.assertEqual(set(contract.announcement), set(contract.response_states))
                for expectation in contract.announcement.values():
                    self.assertNotEqual(
                        bool(expectation.role),
                        bool(expectation.silence_reason),
                    )
