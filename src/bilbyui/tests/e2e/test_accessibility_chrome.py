"""Isolated axe accessibility scan for shared application chrome."""

from bilbyui.tests.e2e.accessibility_assertions import assert_no_serious_axe_violations
from bilbyui.tests.e2e.base import GWFlowJobsPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe

CHROME_SCOPE = ".app-navbar"


class TestAccessibilityChrome(GWFlowJobsPageBase):
    """Scan shared app shell separately from route content."""

    @async_e2e_test
    async def test_shared_chrome_has_no_blocking_axe_findings(self):
        await self.page.wait_for_selector(CHROME_SCOPE, state="visible")
        await load_axe(self.page)
        await assert_no_serious_axe_violations(self.page, CHROME_SCOPE, context="app-chrome")
