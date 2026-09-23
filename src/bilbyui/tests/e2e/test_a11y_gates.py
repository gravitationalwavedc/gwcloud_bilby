"""Axe accessibility gate for rendered page content regions."""

from bilbyui.tests.e2e.accessibility_assertions import assert_no_serious_axe_violations
from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe

CONTENT_SCOPE = "main"


class TestContentAxe(GWFlowJobsPageBase):
    """Scan the reachable GWFlow list state without attributing shell defects."""

    @async_e2e_test
    async def test_reachable_content_has_no_blocking_axe_findings(self):
        contract = "gwflow_list_search_filter_pagination"
        state = "initial"
        await self.page.wait_for_selector(CONTENT_SCOPE, state="visible")
        await load_axe(self.page)
        await assert_no_serious_axe_violations(
            self.page,
            CONTENT_SCOPE,
            context=f"contract={contract!r} state={state!r} scope={CONTENT_SCOPE!r}",
        )


async def _assert_axe_gate(case, scope, contract, state="initial"):
    await case.page.wait_for_selector(scope, state="visible")
    await load_axe(case.page)
    await assert_no_serious_axe_violations(
        case.page,
        scope,
        context=f"contract={contract!r} state={state!r} scope={scope!r}",
    )


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
