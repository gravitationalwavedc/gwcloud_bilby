"""Horizontal-overflow containment of GWFlow metadata at a 320px viewport."""

from bilbyui.tests.e2e.test_gwflow_metadata_axe_e2e import GWFlowMetadataPageBase
from bilbyui.tests.e2e.utils import async_e2e_test

VIEWPORT = {"width": 320, "height": 700}


class TestGWFlowMetadataOverflow320(GWFlowMetadataPageBase):
    @async_e2e_test
    async def test_wide_metadata_tables_are_contained_at_320px(self):
        page = self.page
        await page.set_viewport_size(VIEWPORT)
        await page.reload()
        await page.wait_for_selector(".gwflow-metadata", state="visible")

        regions = page.locator(".table-scroll-region")
        self.assertGreaterEqual(
            await regions.count(),
            2,
            "complete_curated.json must render the wide GraceDB and PE tables",
        )

        metrics = await page.evaluate(
            "({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth })"
        )
        self.assertLessEqual(
            metrics["scrollWidth"],
            metrics["innerWidth"],
            "document scrolls horizontally at 320px: "
            f"scrollWidth={metrics['scrollWidth']} > innerWidth={metrics['innerWidth']}",
        )

        scrollable_regions = await regions.evaluate_all(
            "(elements) => elements.filter((element) => element.scrollWidth > element.clientWidth).length"
        )
        self.assertGreaterEqual(
            scrollable_regions,
            1,
            "expected at least one wide metadata table to scroll within its contained region",
        )
