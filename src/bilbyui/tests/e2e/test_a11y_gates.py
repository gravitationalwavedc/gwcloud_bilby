"""Axe accessibility gate for rendered page content regions."""

from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe

CONTENT_SCOPE = "main"
BLOCKING_IMPACTS = {"serious", "critical"}


def _format_findings(violations, contract, state, scope):
    """Return blocking findings and actionable diagnostics."""
    blocking = [violation for violation in violations if violation.get("impact") in BLOCKING_IMPACTS]
    lines = []
    for violation in blocking:
        for node in violation.get("nodes", []):
            target = " > ".join(str(part) for part in node.get("target", []))
            html = " ".join(node.get("html", "").split())[:240]
            lines.append(
                f"rule={violation.get('id')} impact={violation.get('impact')} "
                f"selector={target!r} html={html!r} contract={contract!r} "
                f"state={state!r} scope={scope!r}"
            )
    return blocking, "\n".join(lines)


class TestContentAxe(GWFlowJobsPageBase):
    """Scan the reachable GWFlow list state without attributing shell defects."""

    @async_e2e_test
    async def test_reachable_content_has_no_blocking_axe_findings(self):
        contract = "gwflow_list_search_filter_pagination"
        state = "initial"
        await self.page.wait_for_selector(CONTENT_SCOPE, state="visible")
        await load_axe(self.page)
        violations = await run_axe(self.page, CONTENT_SCOPE)
        blocking, diagnostics = _format_findings(
            violations,
            contract,
            state,
            CONTENT_SCOPE,
        )
        self.assertEqual(
            [],
            blocking,
            "Serious/critical content-region axe findings:\n" + diagnostics,
        )


async def _assert_axe_gate(case, scope, contract, state="initial"):
    await case.page.wait_for_selector(scope, state="visible")
    await load_axe(case.page)
    blocking, diagnostics = _format_findings(await run_axe(case.page, scope), contract, state, scope)
    case.assertEqual([], blocking, "Serious/critical content-region axe findings:\n" + diagnostics)


class TestDetailContentAxe(GWFlowDetailShellBase):
    @async_e2e_test
    async def test_metadata_content_has_no_blocking_axe_findings(self):
        await _assert_axe_gate(self, ".detail-shell", "gwflow_detail_metadata")


class TestFilesContentAxe(GWFlowFilesPageBase):
    @async_e2e_test
    async def test_files_content_has_no_blocking_axe_findings(self):
        await _assert_axe_gate(self, "#detail-pane", "gwflow_detail_files")


class TestDemoContentAxe(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_content_has_no_blocking_axe_findings(self):
        await _assert_axe_gate(self, ".app-container", "tech_value_demo")


class TestListErrorContentAxe(GWFlowJobsPageBase):
    """A genuinely reachable list-service error response."""

    @staticmethod
    def gwflow_jobs_side_effect(*args, **kwargs):
        return {
            "jobs": {},
            "records": [],
            "has_next": False,
            "page": 1,
            "page_size": 20,
            "total": 0,
            "state": "down",
        }

    @async_e2e_test
    async def test_error_content_has_no_blocking_axe_findings(self):
        await self.page.wait_for_selector(".async-error")
        await _assert_axe_gate(self, "#gwflow-job-list", "gwflow_list_search_filter_pagination", "error")
