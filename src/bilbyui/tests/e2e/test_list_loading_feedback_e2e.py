"""Forced-latency list loading feedback on the GWFlow surface (issue #76)."""

from bilbyui.tests.e2e.base import GWFlowJobsPageBase
from bilbyui.tests.e2e.utils import async_e2e_test


class TestGWFlowForcedLatencyLoading(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_indicator_busy_and_retained_rows_during_inflight_request(self):
        page = self.page
        await page.wait_for_selector(".result-count")

        async def delay_list_request(route):
            await page.wait_for_timeout(1000)
            await route.continue_()

        search = page.locator("#search")
        await page.route("**/gwflow/?*", delay_list_request, times=1)
        await search.focus()
        await search.fill("S2306")
        await search.evaluate("(el) => el.setSelectionRange(3, 3)")
        await page.wait_for_function("() => !document.getElementById('gwflow-loading-indicator').hidden")
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region').getAttribute('aria-busy') === 'true'"
        )
        assert await page.evaluate("document.activeElement.id") == "search"
        assert await search.evaluate("(el) => el.selectionStart") == 3
        assert await page.locator("#gwflow-job-list .result-count").count() == 1
        assert await page.locator("#gwflow-job-list table").count() >= 1

        await page.wait_for_function("() => document.getElementById('gwflow-loading-indicator').hidden === true")
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region').getAttribute('aria-busy') === 'false'"
        )
        assert await page.evaluate("document.activeElement.id") == "search"
        assert await search.evaluate("(el) => el.selectionStart") == 3
        status = (await page.locator("#gwflow-results-status").inner_text()).strip()
        assert "superevent" in status, f"unexpected settled status: {status!r}"
        await page.unroute_all(behavior="ignoreErrors")


class TestGWFlowLoadingFailureRetry(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_failure_clears_loading_and_retry_reenters_loading(self):
        page = self.page
        await page.wait_for_selector(".result-count")

        async def transport_failure(route):
            await route.fulfill(
                status=503,
                content_type="text/plain",
                body="Service unavailable",
            )

        await page.route("**/gwflow/?*", transport_failure, times=1)
        await page.locator("#library").select_option("lib1")

        alert = page.locator("#gwflow-job-list [role='alert']")
        await alert.wait_for()
        retry = alert.get_by_role("button", name="Retry")
        await retry.wait_for()
        await page.wait_for_function("() => document.getElementById('gwflow-loading-indicator').hidden === true")
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region').getAttribute('aria-busy') === 'false'"
        )

        async def delayed_success(route):
            await page.wait_for_timeout(1000)
            await route.continue_()

        await page.route("**/gwflow/?*", delayed_success, times=1)
        await retry.click()
        await page.wait_for_function("() => !document.getElementById('gwflow-loading-indicator').hidden")
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region').getAttribute('aria-busy') === 'true'"
        )
        await page.wait_for_function("() => document.getElementById('gwflow-loading-indicator').hidden === true")
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region').getAttribute('aria-busy') === 'false'"
        )
        await page.unroute_all(behavior="ignoreErrors")
