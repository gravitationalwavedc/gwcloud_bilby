"""URL-backed detail shell regression tests (issue #53 review findings).

Covers the review-discovered DOM swap defect: the pane heading and skeleton
lived inside ``#detail-pane`` and were destroyed by every ``hx-swap="innerHTML"``
section navigation, silently breaking keyboard focus (focus rule D), document
title updates and skeleton availability on every subsequent navigation.

This test asserts that after an HTMX section swap the persistent heading
(``#detail-heading``, outside the swap target) survives and tracks the active
section, the skeleton is re-present for the next request, ``aria-current`` stays
in sync with the URL, pointer navigation keeps focus on the link, and unmodified
Enter navigation moves focus to the heading after a settled swap.
"""

from django.urls import reverse

from bilbyui.tests.e2e.base import GWFlowDetailShellBase, GWFlowFilesPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe

META = 'document.getElementById("detail-heading")'
ACTIVE = "document.activeElement"


def _title(section: str) -> str:
    return f"{section} — S230601ag — GWCloud"


class TestGWFlowDetailShellSwapPersistence(GWFlowFilesPageBase):
    @property
    def metadata_url(self) -> str:
        return f"{self.live_server_url}{reverse('bilbyui:gwflow_job_metadata', args=[self.sname])}"

    async def _heading_text(self) -> str:
        return await self.page.evaluate(f"{META} ? {META}.textContent.trim() : null")

    async def _skeleton_present(self) -> bool:
        return await self.page.evaluate(
            "document.getElementById('detail-pane') && "
            "!!document.getElementById('detail-pane').querySelector('#detail-skeleton')"
        )

    @async_e2e_test
    async def test_shell_persistence_and_focus(self):
        page = self.page

        # asetUp already swapped into Files via HTMX from /metadata/ — the
        # state where the old bug destroyed the heading/skeleton.
        self.assertEqual(await self._heading_text(), "Files", "heading must survive an HTMX swap")
        self.assertTrue(await self._skeleton_present(), "skeleton must be re-present after a swap")
        self.assertEqual(await page.title(), _title("Files"), "document title must reflect the active section")
        files_link = page.locator('a[data-gwflow-section][href*="/files/"]')
        metadata_link = page.locator('a[data-gwflow-section][href*="/metadata/"]')
        self.assertEqual(await files_link.get_attribute("aria-current"), "page")
        self.assertIsNone(await metadata_link.get_attribute("aria-current"))

        # Second swap (pointer) — heading/skeleton must survive repeated swaps
        # and aria-current must move to History.
        history_link = page.locator('a[data-gwflow-section][href*="/history/"]')
        await history_link.click()
        await page.wait_for_function(
            f"({META} && {META}.textContent.trim() === 'History') && ({ACTIVE} === {META}) === false"
        )
        self.assertEqual(await self._heading_text(), "History")
        self.assertTrue(await self._skeleton_present())
        self.assertEqual(await history_link.get_attribute("aria-current"), "page")
        self.assertIsNone(await files_link.get_attribute("aria-current"))
        self.assertEqual(await page.title(), _title("History"))

        # Pointer navigation keeps focus on the activated link (focus rule D).
        self.assertEqual(
            await page.evaluate(f"{ACTIVE} && {ACTIVE}.classList.contains('section-nav-link')"),
            True,
            "pointer activation must leave focus on the link",
        )

        # Keyboard navigation: reload /metadata/, Enter on the Files link, and
        # the heading must receive focus after a settled swap (focus rule D).
        await page.goto(self.metadata_url)
        await page.wait_for_function(f"{META} && {META}.textContent.trim() === 'Metadata'")
        target_link = page.locator('a[data-gwflow-section][href*="/files/"]')
        await target_link.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_function(
            f"({META} && {META}.textContent.trim() === 'Files') && ({ACTIVE} && {ACTIVE}.id === 'detail-heading')"
        )
        self.assertEqual(await page.title(), _title("Files"))
        self.assertEqual(await self._heading_text(), "Files")
        self.assertTrue(await self._skeleton_present())


class TestGWFlowDetailShellHistoryRestore(GWFlowDetailShellBase):
    """Browser back/forward/refresh restoration of the active section (issue
    #53 test plan: popstate Playwright flow; review finding T-2).

    Exercises the production ``popstate`` / ``htmx:historyRestore`` path: URL,
    active ``aria-current``, persistent heading and pane content must all
    restore together, and history restoration must never move focus (focus
    rule D).
    """

    async def _wait_heading(self, section: str) -> None:
        await self.page.wait_for_function(
            "document.getElementById('detail-heading') && "
            f"document.getElementById('detail-heading').textContent.trim() === '{section}'"
        )

    @async_e2e_test
    async def test_back_forward_refresh_restores_section(self):
        page = self.page
        meta_link = page.locator('a[data-gwflow-section][href*="/metadata/"]')
        files_link = page.locator('a[data-gwflow-section][href*="/files/"]')
        hist_link = page.locator('a[data-gwflow-section][href*="/history/"]')

        # Landing: server deep link on /metadata/.
        await self._wait_heading("Metadata")
        self.assertTrue(page.url.endswith("/metadata/"))
        self.assertEqual(await meta_link.get_attribute("aria-current"), "page")
        self.assertEqual(await page.title(), _title("Metadata"))

        # Metadata -> Files (push), then Files -> History (push).
        await files_link.click()
        await self._wait_heading("Files")
        self.assertTrue(page.url.endswith("/files/"))
        self.assertEqual(await files_link.get_attribute("aria-current"), "page")
        self.assertIsNone(await meta_link.get_attribute("aria-current"))
        await page.wait_for_selector(".gw-analysis-block")

        await hist_link.click()
        await self._wait_heading("History")
        self.assertTrue(page.url.endswith("/history/"))
        self.assertEqual(await hist_link.get_attribute("aria-current"), "page")
        self.assertEqual(await page.title(), _title("History"))

        # Back -> Files restored (URL, heading, aria-current, pane content).
        await page.go_back()
        await self._wait_heading("Files")
        self.assertTrue(page.url.endswith("/files/"))
        self.assertEqual(await files_link.get_attribute("aria-current"), "page")
        self.assertIsNone(await hist_link.get_attribute("aria-current"))
        await page.wait_for_selector(".gw-analysis-block")
        # No automatic focus move during history restoration (focus rule D).
        self.assertFalse(
            await page.evaluate("document.activeElement && document.activeElement.id === 'detail-heading'"),
            "history restoration must not move focus to the heading",
        )

        # Forward -> History restored.
        await page.go_forward()
        await self._wait_heading("History")
        self.assertTrue(page.url.endswith("/history/"))
        self.assertEqual(await hist_link.get_attribute("aria-current"), "page")
        self.assertFalse(
            await page.evaluate("document.activeElement && document.activeElement.id === 'detail-heading'"),
            "history restoration must not move focus to the heading",
        )

        # Refresh lands on the current section (server-side deep link).
        await page.reload()
        await self._wait_heading("History")
        self.assertTrue(page.url.endswith("/history/"))
        self.assertEqual(await hist_link.get_attribute("aria-current"), "page")


class TestGWFlowDetailShellAxe(GWFlowDetailShellBase):
    """axe scan of the changed detail-shell region (review finding AC-3).

    The scan is scoped to the shell (breadcrumb, context strip, section nav,
    pane) rather than the whole document: app-shell/theme contrast debt is
    tracked outside component suites.
    """

    AXE_SCOPE_SELECTOR = ".detail-shell"

    async def _wait_heading(self, section: str) -> None:
        await self.page.wait_for_function(
            "document.getElementById('detail-heading') && "
            f"document.getElementById('detail-heading').textContent.trim() === '{section}'"
        )

    @async_e2e_test
    async def test_detail_shell_zero_serious_critical_axe(self):
        page = self.page
        await self._wait_heading("Metadata")
        await load_axe(page)
        violations = await run_axe(page, self.AXE_SCOPE_SELECTOR)
        blocking = [v for v in violations if v.get("impact") in ("serious", "critical")]
        detail = "\n".join(
            f"- {v['id']} ({v.get('impact')}): "
            + "; ".join(" > ".join(str(part) for part in node["target"]) for node in v["nodes"])
            for v in blocking
        )
        self.assertEqual(
            [],
            blocking,
            f"Expected zero serious/critical axe violations within "
            f"'{self.AXE_SCOPE_SELECTOR}', found {len(blocking)}:\n{detail}",
        )
