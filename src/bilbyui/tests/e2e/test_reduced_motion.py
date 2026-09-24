"""Reduced-motion preference gate for the GWFlow jobs page."""

from bilbyui.tests.e2e.accessibility_assertions import assert_no_active_animation
from bilbyui.tests.e2e.base import GWFlowJobsPageBase, TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test


class TestReducedMotion(GWFlowJobsPageBase):
    """Verify reduced-motion emulation and absence of active motion."""

    @async_e2e_test
    async def test_reduced_motion_preference_prevents_active_animation(self):
        await self.page.emulate_media(reduced_motion="reduce")
        await self.page.reload()
        await self.page.wait_for_load_state("networkidle")

        prefers_reduce = await self.page.evaluate("window.matchMedia('(prefers-reduced-motion: reduce)').matches")
        self.assertTrue(prefers_reduce, "browser must emulate prefers-reduced-motion: reduce")

        await assert_no_active_animation(self.page, "body")


class TestDemoReducedMotion(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_reduced_motion_prevents_active_animation(self):
        await self.page.emulate_media(reduced_motion="reduce")
        await self.page.reload()
        await self.page.wait_for_load_state("networkidle")
        self.assertTrue(await self.page.evaluate("window.matchMedia('(prefers-reduced-motion: reduce)').matches"))
        await assert_no_active_animation(self.page, "body")
