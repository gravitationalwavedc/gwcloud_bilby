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

from bilbyui.tests.e2e.base import GWFlowFilesPageBase
from bilbyui.tests.e2e.utils import async_e2e_test

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
