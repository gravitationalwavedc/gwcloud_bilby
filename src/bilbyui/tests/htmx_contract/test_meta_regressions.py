"""Seeded regressions proving that HTMX contract violations fail closed."""

from dataclasses import replace
from types import MappingProxyType

from django.http import HttpResponse

from bilbyui.tests.testcases import BilbyTestCase

from .assertions import assert_response_contract
from .audit import AuditError, extract_rendered, extract_source
from .registry import REGISTRY, AnnouncementExpectation, validate_registry


class ContractMetaRegressionTests(BilbyTestCase):
    def test_wrong_target_id_is_detected(self):
        contract = next(
            item for item in REGISTRY if item.name == "gwflow_version_select_compare"
        )
        response = HttpResponse(
            '<div id="wrong-target"></div>'
        )
        with self.assertRaisesRegex(AssertionError, "fragment root must match target"):
            assert_response_contract(self, contract, response, state="content")

    def test_innerhtml_swap_tolerates_a_non_target_root(self):
        contract = REGISTRY[0]
        self.assertEqual(contract.swap, "innerHTML")
        response = HttpResponse(
            '<div id="some-other-root"><p role="status">3 superevents match</p></div>'
        )
        assert_response_contract(self, contract, response, state="content")

    def test_retry_control_must_match_the_registered_selector(self):
        contract = REGISTRY[0]
        response = HttpResponse(
            '<div class="async-error" role="alert">Failed</div>'
            '<button hx-get="/retry/" hx-target="#gwflow-job-list">Retry</button>'
        )
        with self.assertRaisesRegex(AssertionError, "retry control matching"):
            assert_response_contract(self, contract, response, state="error")

    def test_missing_state_partial_is_detected(self):
        contract = REGISTRY[0]
        response = HttpResponse('<div id="gwflow-job-list"></div>')
        with self.assertRaisesRegex(AssertionError, r"async-empty.*role='status'"):
            assert_response_contract(self, contract, response, state="empty")

    def test_duplicate_announcement_is_detected(self):
        contract = REGISTRY[0]
        response = HttpResponse(
            '<div id="gwflow-job-list">'
            '<div class="async-error" role="alert">First</div>'
            '<p role="alert">Second</p></div>'
        )
        with self.assertRaisesRegex(AssertionError, "duplicate announcements"):
            assert_response_contract(self, contract, response, state="error")

    def test_stale_semantic_expectation_is_detected(self):
        contract = REGISTRY[0]
        announcements = dict(contract.announcement)
        announcements.pop("stale")
        invalid = replace(
            contract,
            announcement=MappingProxyType(announcements),
        )
        with self.assertRaisesRegex(ValueError, "missing announcement semantics for stale"):
            validate_registry((invalid,))

    def test_stale_announcement_role_is_detected(self):
        contract = REGISTRY[0]
        announcements = dict(contract.announcement)
        announcements["content"] = AnnouncementExpectation(role="alert")
        stale = replace(
            contract,
            announcement=MappingProxyType(announcements),
        )
        response = HttpResponse(
            '<div id="gwflow-job-list"></div>'
        )
        with self.assertRaisesRegex(AssertionError, "expected one announcement"):
            assert_response_contract(self, stale, response, state="content")

    def test_unknown_source_hx_syntax_is_detected(self):
        with self.assertRaisesRegex(AuditError, "unknown HTMX attribute 'hx-frob'"):
            extract_source('<button hx-frob="yes">Broken</button>', "seed.html")

    def test_unknown_rendered_hx_syntax_is_detected(self):
        with self.assertRaisesRegex(AuditError, "rendered unknown HTMX"):
            extract_rendered('<button hx-frob="yes">Broken</button>', "/seed/")
