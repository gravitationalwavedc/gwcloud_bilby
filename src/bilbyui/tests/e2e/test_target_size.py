"""WCAG 2.2 target-size gate for the GWFlow jobs page."""

from bilbyui.tests.e2e.accessibility_assertions import assert_target_sizes
from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test

MAXIMUM_EXCEPTIONS = 3


class TestTargetSize(GWFlowJobsPageBase):
    """Verify visible, enabled targets in main meet the WCAG minimum."""

    @async_e2e_test
    async def test_visible_interactive_targets_are_at_least_24_css_pixels(self):
        await assert_target_sizes(self.page, max_inline_link_exceptions=MAXIMUM_EXCEPTIONS)


class TestDetailTargetSize(GWFlowDetailShellBase):
    @async_e2e_test
    async def test_metadata_targets_are_at_least_24_css_pixels(self):
        await assert_target_sizes(self.page)


class TestFilesTargetSize(GWFlowFilesPageBase):
    @async_e2e_test
    async def test_files_targets_are_at_least_24_css_pixels(self):
        await assert_target_sizes(self.page)


class TestDemoTargetSize(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_targets_are_at_least_24_css_pixels(self):
        await assert_target_sizes(self.page)
