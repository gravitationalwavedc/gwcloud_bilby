"""Responsive file-block transform and axe scan of the GWFlow files region.

At a mobile viewport (<768px) the file table rows transform to stacked
per-file blocks (see _gwflow_files.scss): the table header is hidden and each
row renders as a self-contained block with name + actions primary and
size/status secondary. This test asserts that transform, that the page does
not scroll horizontally at 375px, and that the files region carries zero
serious/critical axe violations.

The axe scan is scoped to the files region (the joined analysis blocks)
rather than the whole document: the app shell (navbar links) and theme
defaults carry pre-existing contrast debt tracked outside this suite.
"""

from bilbyui.tests.e2e.base import GWFlowFilesPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe

MOBILE_VIEWPORT = {"width": 375, "height": 700}

# The joined analysis blocks are the files region; excludes app shell chrome.
AXE_SCOPE_SELECTOR = ".gw-analysis-block"


class TestGWFlowFilesMobileTransform(GWFlowFilesPageBase):
    @async_e2e_test
    async def test_mobile_stacked_transform_no_overflow_axe(self):
        page = self.page
        await page.set_viewport_size(MOBILE_VIEWPORT)
        await page.reload()
        await self._open_files_region()

        # Stacked transform: the table header is hidden and each row is a
        # self-contained block.
        self.assertFalse(
            await page.locator(".gw-files-table thead").first.is_visible(),
            "table header must be hidden at 375px (stacked per-file blocks)",
        )
        row_display = await page.locator(".gw-file-row").first.evaluate("el => getComputedStyle(el).display")
        self.assertEqual(
            "block",
            row_display,
            f"file rows must render as stacked blocks at 375px, got display={row_display}",
        )

        # No horizontal overflow at 375px.
        metrics = await page.evaluate(
            "({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth })"
        )
        self.assertLessEqual(
            metrics["scrollWidth"],
            metrics["innerWidth"],
            "document scrolls horizontally at 375px: "
            f"scrollWidth={metrics['scrollWidth']} > innerWidth={metrics['innerWidth']}",
        )

        # Zero serious/critical axe violations within the files region.
        await load_axe(page)
        violations = await run_axe(page, AXE_SCOPE_SELECTOR)
        blocking = [v for v in violations if v.get("impact") in ("serious", "critical")]
        detail = "\n".join(
            f"- {v['id']} ({v.get('impact')}): "
            + "; ".join(" > ".join(str(part) for part in node["target"]) for node in v["nodes"])
            for v in blocking
        )
        self.assertEqual(
            [],
            blocking,
            f"Expected zero serious/critical axe violations within '{AXE_SCOPE_SELECTOR}', "
            f"found {len(blocking)}:\n{detail}",
        )
