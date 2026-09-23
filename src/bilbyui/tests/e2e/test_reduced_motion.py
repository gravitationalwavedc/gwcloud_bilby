"""Reduced-motion preference gate for the GWFlow jobs page."""

from bilbyui.tests.e2e.base import GWFlowJobsPageBase, TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test


class TestReducedMotion(GWFlowJobsPageBase):
    """Verify reduced-motion emulation and absence of infinite motion."""

    @async_e2e_test
    async def test_reduced_motion_preference_prevents_infinite_animation(self):
        await self.page.emulate_media(reduced_motion="reduce")
        await self.page.reload()
        await self.page.wait_for_load_state("networkidle")

        prefers_reduce = await self.page.evaluate("window.matchMedia('(prefers-reduced-motion: reduce)').matches")
        self.assertTrue(prefers_reduce, "browser must emulate prefers-reduced-motion: reduce")

        motion = await self.page.locator("body").evaluate(
            """body => Array.from(body.querySelectorAll('*')).flatMap(element => {
                const style = getComputedStyle(element);
                const durations = style.animationDuration.split(',').map(value => {
                    if (value.trim().endsWith('ms')) return parseFloat(value);
                    if (value.trim().endsWith('s')) return parseFloat(value) * 1000;
                    return 0;
                });
                const iterations = style.animationIterationCount.split(',');
                const infinite = durations.some(
                    (duration, index) =>
                        duration > 0
                        && (iterations[index] || iterations[0] || '').trim() === 'infinite'
                );
                if (!infinite) return [];
                return [{
                    tag: element.tagName.toLowerCase(),
                    id: element.id,
                    classes: String(element.className),
                    animationDuration: style.animationDuration,
                    animationIterationCount: style.animationIterationCount,
                }];
            })"""
        )
        self.assertEqual([], motion, f"infinite animations remain in reduced-motion mode: {motion}")


class TestDemoReducedMotion(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_reduced_motion_prevents_infinite_animation(self):
        await self.page.emulate_media(reduced_motion="reduce")
        await self.page.reload()
        await self.page.wait_for_load_state("networkidle")
        self.assertTrue(await self.page.evaluate("window.matchMedia('(prefers-reduced-motion: reduce)').matches"))
        motion = await self.page.locator("body").evaluate(
            """body => Array.from(body.querySelectorAll('*')).filter(element => {
                const style = getComputedStyle(element);
                return style.animationDuration !== '0s'
                    && style.animationIterationCount.split(',').some(value => value.trim() === 'infinite');
            }).map(element => ({tag: element.tagName.toLowerCase(), id: element.id}))"""
        )
        self.assertEqual([], motion, f"infinite animations remain in reduced-motion mode: {motion}")
