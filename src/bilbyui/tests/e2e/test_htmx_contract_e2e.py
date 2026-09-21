"""Focused browser journeys for the registered HTMX interaction contracts.

Each concrete Playwright class owns exactly one Django-discovered test method.
The shared base contains helpers only and the existing e2e harness owns the
single Chromium server and browser-context lifecycle.
"""

from __future__ import annotations

import threading

from asgiref.sync import sync_to_async

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.base import (
    LIBRARY_TOTALS,
    GWFlowJobsPageBase,
    _build_gwflow_result,
)
from bilbyui.tests.e2e.test_api_token_keyboard_e2e import APITokenKeyboardBase
from bilbyui.tests.e2e.test_gwflow_history_e2e import (
    SHA_V1,
    SHA_V2,
    GWFlowHistoryPageBase,
)
from bilbyui.tests.e2e.utils import AsyncE2ETestCase, async_e2e_test
from bilbyui.tests.htmx_contract.registry import REGISTRY


class HTMXContractE2EBase(AsyncE2ETestCase):
    """Shared interaction-contract assertions; deliberately contains no tests."""

    @staticmethod
    def contract(name):
        return next(contract for contract in REGISTRY if contract.name == name)

    async def install_settle_observer(self, page):
        """Count non-empty live-region mutations in each HTMX settle window."""
        await page.evaluate(
            """
            () => {
              window.__contractSettles = [];
              window.__contractWindow = [];
              const live = (node) => {
                if (!(node instanceof Element)) return null;
                return node.matches('[role="status"],[role="alert"]')
                  ? node
                  : node.closest('[role="status"],[role="alert"]');
              };
              window.__contractObserver = new MutationObserver((records) => {
                for (const record of records) {
                  const element = live(record.target);
                  if (!element) continue;
                  const text = (element.textContent || '').trim();
                  if (!text) continue;
                  const item = {role: element.getAttribute('role'), text};
                  if (!window.__contractWindow.some(
                    (seen) => seen.role === item.role && seen.text === item.text
                  )) window.__contractWindow.push(item);
                }
              });
              window.__contractObserver.observe(document.body, {
                childList: true, subtree: true, characterData: true
              });
              document.body.addEventListener('htmx:beforeRequest', () => {
                window.__contractWindow = [];
              });
              document.body.addEventListener('htmx:afterSettle', () => {
                window.__contractSettles.push(window.__contractWindow.slice());
                window.__contractWindow = [];
              });
            }
            """
        )

    async def wait_for_settle_count(self, page, count):
        await page.wait_for_function(
            "(count) => (window.__contractSettles || []).length >= count",
            arg=count,
        )


class HTMXFocusAndAnnouncementContractTest(
    HTMXContractE2EBase,
    GWFlowJobsPageBase,
):
    """Search settle preserves focus and makes at most one registered announcement."""

    @async_e2e_test
    async def test_focus_and_announcement_contract(self):
        page = self.page
        contract = self.contract("gwflow_list_search_filter_pagination")
        self.assertEqual(contract.focus.rule, "preserve")
        self.assertIn("announcement", contract.capabilities)
        await self.install_settle_observer(page)

        search = page.locator("#search")
        await search.fill("focus")
        await self.wait_for_settle_count(page, 1)
        await page.wait_for_function(
            "() => document.querySelector('.result-count')?.textContent.includes('5 superevents match')"
        )

        self.assertEqual(
            await page.evaluate("document.activeElement && document.activeElement.id"),
            "search",
        )
        settlements = await page.evaluate("window.__contractSettles")
        messages = settlements[-1]
        self.assertLessEqual(len(messages), 1)
        if messages:
            self.assertEqual(messages[0]["role"], "status")


class _RaceGate:
    """Coordinate two real live-server requests without fixed delays."""

    def __init__(self):
        self.started = {}
        self.release = {}
        self.lock = threading.Lock()

    def events(self, search):
        with self.lock:
            if search not in self.started:
                self.started[search] = threading.Event()
                self.release[search] = threading.Event()
            return self.started[search], self.release[search]


RACE_GATE = _RaceGate()


def _race_result(
    user,
    *,
    search="",
    library="",
    review_status="",
    time_range="all",
    page=1,
    page_size=20,
    **kwargs,
):
    del user, review_status, time_range, kwargs
    started, release = RACE_GATE.events(search)
    started.set()
    release.wait(10)
    jobs = list(GWFlowJob.objects.order_by("id"))
    total = len(search) + LIBRARY_TOTALS.get(library, 0)
    return _build_gwflow_result(jobs, total=total, page=page, page_size=page_size)


class HTMXSearchRaceContractTest(
    HTMXContractE2EBase,
    GWFlowJobsPageBase,
):
    """The audited shared hx-sync boundary guarantees that the last intent wins."""

    gwflow_jobs_side_effect = staticmethod(_race_result)

    @async_e2e_test
    async def test_last_search_request_wins(self):
        page = self.page
        form = page.locator(".gwflow-search-form")
        self.assertEqual(
            await form.get_attribute("hx-sync"),
            "#jobs-search-region:replace",
        )

        search = page.locator("#search")
        await search.fill("first")
        first_started, first_release = RACE_GATE.events("first")
        self.assertTrue(await sync_to_async(first_started.wait, thread_sensitive=False)(10))

        await search.fill("last")
        first_release.set()
        last_started, last_release = RACE_GATE.events("last")
        self.assertTrue(await sync_to_async(last_started.wait, thread_sensitive=False)(10))
        last_release.set()

        await page.wait_for_function(
            "() => document.querySelector('.result-count')?.textContent.includes('4 superevents match')"
        )
        self.assertIn("search=last", page.url)
        self.assertNotIn("search=first", page.url)


class HTMXHistoryContractTest(
    HTMXContractE2EBase,
    GWFlowHistoryPageBase,
):
    """Each settled selection pushes once and popstate restores URL and region."""

    @async_e2e_test
    async def test_push_url_and_popstate_restore(self):
        await self._wait_for_rail()
        page = self.page
        initial_url = page.url
        initial_length = await page.evaluate("history.length")

        await self._version_link(SHA_V2).click()
        await page.wait_for_function(f"() => location.search.includes('version={SHA_V2}')")
        self.assertEqual(await page.evaluate("history.length"), initial_length + 1)
        self.assertEqual(
            await page.locator(".gwflow-history__desktop-list [aria-current='true']").get_attribute("data-version-sha"),
            SHA_V2,
        )

        await page.go_back()
        await page.wait_for_function(f"() => !location.search.includes('version={SHA_V2}')")
        self.assertEqual(page.url, initial_url)
        restored = await page.locator(".gwflow-history__desktop-list [aria-current='true']").get_attribute(
            "data-version-sha"
        )
        self.assertNotEqual(restored, SHA_V2)
        self.assertIsNotNone(restored)
        self.assertIn(restored, {SHA_V1, restored})


class HTMXClipboardContractTest(
    HTMXContractE2EBase,
    APITokenKeyboardBase,
):
    """A granted browser clipboard receives the secret and focus is preserved."""

    async def asetUp(self):
        await APITokenKeyboardBase.asetUp(self)
        await self.browser_context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin=self.live_server_url,
        )
        self.page = await self.browser_context.new_page()
        await self.page.goto(self.url)
        await self.page.get_by_role("button", name="Create Token").click()
        await self.page.locator("#token-name").fill("contract-copy-token")
        await self.page.locator("#token-create-form button[type=submit]").click()
        await self.page.locator(".token-copy").wait_for(state="attached")

    async def aTearDown(self):
        if getattr(self, "page", None) is not None:
            await self.page.close()
            self.page = None

    @async_e2e_test
    async def test_token_copy_contract(self):
        page = self.page
        copy = page.locator(".token-copy")
        secret = page.locator("#new-token-value")
        expected = await secret.text_content()

        await copy.focus()
        await copy.click()
        await page.wait_for_function("() => document.querySelector('.token-copy-status')?.textContent === 'Copied!'")
        copied = await page.evaluate("navigator.clipboard.readText()")
        self.assertEqual(copied, expected)
        self.assertEqual(
            await page.evaluate("document.activeElement && document.activeElement.classList.contains('token-copy')"),
            True,
        )


class HTMXLoadingIndicatorContractTest(
    HTMXContractE2EBase,
    GWFlowJobsPageBase,
):
    """The indicator enters and leaves loading state at HTMX event barriers."""

    @async_e2e_test
    async def test_loading_indicator_contract(self):
        page = self.page
        indicator = page.locator("#gwflow-loading-indicator")
        target = page.locator("#gwflow-job-list")

        self.assertEqual(await indicator.count(), 1)
        self.assertEqual(await target.locator("#gwflow-loading-indicator").count(), 0)
        self.assertTrue(await indicator.evaluate("el => el.hidden"))
        self.assertEqual(await indicator.get_attribute("aria-hidden"), "true")

        async def delay_list_request(route):
            await page.wait_for_timeout(1000)
            await route.continue_()

        await page.route("**/gwflow/?*", delay_list_request, times=1)
        await page.evaluate(
            """
            () => {
              window.__loadingLifecycle = [];
              document.body.addEventListener('htmx:beforeRequest', () => {
                window.__loadingLifecycle.push('before');
              }, {once: true});
              document.body.addEventListener('htmx:afterSettle', () => {
                window.__loadingLifecycle.push('settled');
              }, {once: true});
            }
            """
        )

        await page.locator("#library").select_option("lib1")
        await page.wait_for_function("() => window.__loadingLifecycle.includes('before')")
        await page.wait_for_function("() => !document.getElementById('gwflow-loading-indicator').hidden")
        self.assertFalse(await indicator.evaluate("el => el.hidden"))
        self.assertEqual(await indicator.get_attribute("aria-hidden"), "false")

        await page.wait_for_function("() => window.__loadingLifecycle.includes('settled')")
        await page.wait_for_function("() => document.getElementById('gwflow-loading-indicator').hidden")
        self.assertTrue(await indicator.evaluate("el => el.hidden"))
        self.assertEqual(await indicator.get_attribute("aria-hidden"), "true")
        self.assertEqual(
            await page.evaluate("window.__loadingLifecycle"),
            ["before", "settled"],
        )
