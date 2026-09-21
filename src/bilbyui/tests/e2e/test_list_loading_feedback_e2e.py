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

        await page.route("**/gwflow/?*", delay_list_request, times=1)
        await page.locator("#library").select_option("lib1")
        await page.wait_for_function(
            "() => !document.getElementById('gwflow-loading-indicator').hidden"
        )
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region')"
            ".getAttribute('aria-busy') === 'true'"
        )
        assert await page.locator("#gwflow-job-list .result-count").count() == 1
        assert await page.locator("#gwflow-job-list table").count() >= 1

        await page.wait_for_function(
            "() => document.getElementById('gwflow-loading-indicator').hidden === true"
        )
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region')"
            ".getAttribute('aria-busy') === 'false'"
        )
        status = (await page.locator("#gwflow-results-status").inner_text()).strip()
        assert "superevent" in status, f"unexpected settled status: {status!r}"
        await page.unroute_all(behavior="ignoreErrors")


class TestGWFlowLoadingFailureRetry(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_failure_clears_loading_and_retry_reenters_loading(self):
        page = self.page
        await page.wait_for_selector(".result-count")

        async def error_fragment(route):
            await route.fulfill(
                status=200,
                content_type="text/html",
                body="""
                <div class="list-fragment" data-settled-kind="error">
                  <div class="async-error" role="alert" aria-label="GWFlow job list">
                    <p>Couldn't load the GWFlow jobs.</p>
                    <button
                      type="button"
                      class="btn btn-primary"
                      hx-get="/gwflow/?page=1"
                      hx-target="#gwflow-job-list"
                      hx-swap="innerHTML"
                      hx-indicator="#gwflow-loading-indicator"
                    >Retry</button>
                  </div>
                </div>
                """,
            )

        await page.route("**/gwflow/?*", error_fragment, times=1)
        await page.locator("#library").select_option("lib1")

        await page.wait_for_selector("#gwflow-job-list [role='alert']")
        await page.wait_for_function(
            "() => document.getElementById('gwflow-loading-indicator').hidden === true"
        )
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region')"
            ".getAttribute('aria-busy') === 'false'"
        )

        async def delay_list_request(route):
            await page.wait_for_timeout(1000)
            await route.continue_()

        await page.route("**/gwflow/?*", delay_list_request, times=1)
        await page.get_by_role("button", name="Retry").click()
        await page.wait_for_function(
            "() => !document.getElementById('gwflow-loading-indicator').hidden"
        )
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region')"
            ".getAttribute('aria-busy') === 'true'"
        )
        await page.wait_for_function(
            "() => document.getElementById('gwflow-loading-indicator').hidden === true"
        )
        await page.wait_for_function(
            "() => document.getElementById('gwflow-results-region')"
            ".getAttribute('aria-busy') === 'false'"
        )
        await page.unroute_all(behavior="ignoreErrors")
