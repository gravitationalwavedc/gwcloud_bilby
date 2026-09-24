"""Five-width responsive overflow crawl for the GWFlow jobs list."""

from bilbyui.tests.e2e.accessibility_assertions import (
    assert_no_horizontal_overflow,
    assert_table_scroll_regions,
)
from bilbyui.tests.e2e.accessibility_cases import VIEWPORT_WIDTHS
from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test


async def _assert_width(case, route, width):
    await case.page.set_viewport_size({"width": width, "height": 900})
    await case.page.reload()
    await case.page.wait_for_load_state("networkidle")
    context = f"{route} width={width}"
    await assert_no_horizontal_overflow(case.page, context=context)
    await assert_table_scroll_regions(case.page, context=context)


class TestResponsiveCrawl(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_gwflow_list_has_no_horizontal_page_overflow(self):
        for width in VIEWPORT_WIDTHS:
            with self.subTest(case=f"gwflow-list width={width}"):
                await _assert_width(self, "gwflow-list", width)


async def _assert_responsive(case, route):
    for width in VIEWPORT_WIDTHS:
        with case.subTest(case=f"{route} width={width}"):
            await _assert_width(case, route, width)


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
