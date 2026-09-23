"""Five-width responsive overflow crawl for the GWFlow jobs list."""

from bilbyui.tests.e2e.accessibility_cases import VIEWPORT_WIDTHS
from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test


class TestResponsiveCrawl(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_gwflow_list_has_no_horizontal_page_overflow(self):
        for width in VIEWPORT_WIDTHS:
            label = f"gwflow-list width={width}"
            with self.subTest(case=label):
                await self.page.set_viewport_size({"width": width, "height": 900})
                await self.page.reload()
                await self.page.wait_for_load_state("networkidle")

                metrics = await self.page.evaluate(
                    """() => ({
                        scrollWidth: document.scrollingElement.scrollWidth,
                        innerWidth: window.innerWidth,
                    })"""
                )
                self.assertLessEqual(
                    metrics["scrollWidth"],
                    metrics["innerWidth"],
                    f"{label}: page overflow: {metrics}",
                )

                regions = self.page.locator(".table-scroll-region")
                for index in range(await regions.count()):
                    region = regions.nth(index)
                    facts = await region.evaluate(
                        """element => {
                            const style = getComputedStyle(element);
                            const label = (
                                element.getAttribute('aria-label')
                                || element.getAttribute('aria-labelledby')
                                || ''
                            );
                            return {
                                label,
                                overflowX: style.overflowX,
                                tabIndex: element.getAttribute('tabindex'),
                                clientWidth: element.clientWidth,
                                scrollWidth: element.scrollWidth,
                            };
                        }"""
                    )
                    if facts["scrollWidth"] <= facts["clientWidth"]:
                        continue
                    self.assertTrue(facts["label"], f"{label}: region {index} has no accessible label")
                    self.assertIn(
                        facts["overflowX"],
                        ("auto", "scroll"),
                        f"{label}: region {index} does not scroll internally: {facts}",
                    )
                    self.assertEqual(
                        facts["tabIndex"],
                        "0",
                        f"{label}: overflowing region {index} is not keyboard focusable",
                    )


async def _assert_responsive(case, route):
    for width in VIEWPORT_WIDTHS:
        with case.subTest(case=f"{route} width={width}"):
            await case.page.set_viewport_size({"width": width, "height": 900})
            await case.page.reload()
            await case.page.wait_for_load_state("networkidle")
            metrics = await case.page.evaluate(
                "() => ({scrollWidth: document.scrollingElement.scrollWidth, innerWidth: window.innerWidth})"
            )
            case.assertLessEqual(metrics["scrollWidth"], metrics["innerWidth"], f"{route} width={width}: {metrics}")


class TestDetailResponsiveCrawl(GWFlowDetailShellBase):
    @async_e2e_test
    async def test_metadata_has_no_horizontal_page_overflow(self):
        await _assert_responsive(self, "gwflow-detail-metadata")


class TestFilesResponsiveCrawl(GWFlowFilesPageBase):
    @async_e2e_test
    async def test_files_has_no_horizontal_page_overflow(self):
        await _assert_responsive(self, "gwflow-detail-files")


class TestDemoResponsiveCrawl(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_has_no_horizontal_page_overflow(self):
        await _assert_responsive(self, "tech-value-demo")
