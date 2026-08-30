"""Horizontal-overflow containment of the demo page at a 320px viewport."""

from bilbyui.tests.e2e.base import TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test

VIEWPORT = {"width": 320, "height": 700}


class TestOverflow320(TechValueDemoPageBase):
    @async_e2e_test
    async def test_no_horizontal_overflow_at_320px(self):
        page = self.page
        await page.set_viewport_size(VIEWPORT)
        await page.reload()

        metrics = await page.evaluate(
            "({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth })"
        )
        self.assertLessEqual(
            metrics["scrollWidth"],
            metrics["innerWidth"],
            "document scrolls horizontally at 320px: "
            f"scrollWidth={metrics['scrollWidth']} > innerWidth={metrics['innerWidth']}",
        )

        boxes = await page.evaluate(
            """
() => Array.from(document.querySelectorAll('.tech-value')).map((el) => {
    const full = el.querySelector('.tech-value-full');
    const label = el.querySelector('.tech-value-label');
    return {
        width: el.getBoundingClientRect().width,
        parentWidth: el.parentElement.getBoundingClientRect().width,
        fullLength: full ? full.textContent.length : 0,
        label: label ? label.textContent.slice(0, 40) : '',
    };
})
"""
        )
        self.assertGreaterEqual(len(boxes), 9, f"demo fixture sanity: expected all variants, found {len(boxes)}")
        stress = [b for b in boxes if b["fullLength"] >= 500]
        self.assertGreaterEqual(len(stress), 4, "demo fixture sanity: expected 4 stress paths (>=500 chars)")

        for i, box in enumerate(boxes):
            self.assertLessEqual(
                box["width"],
                box["parentWidth"] + 1,
                f".tech-value #{i} ({box['label']}...) overflows its container: "
                f"{box['width']}px > {box['parentWidth']}px",
            )

        index = await page.evaluate(
            """
() => Array.from(document.querySelectorAll('.tech-value')).findIndex(
    (el) => el.querySelector('.tech-value-full').textContent.length >= 1000
)
"""
        )
        self.assertGreaterEqual(index, 0, "fixture sanity: a 1000-character path must exist on the page")

        stress_root = page.locator(".tech-value").nth(index)
        await stress_root.locator(".tech-value-toggle").click()

        document_width = await page.evaluate("document.documentElement.clientWidth")
        revealed_width = await stress_root.locator(".tech-value-full").evaluate(
            "el => el.getBoundingClientRect().width"
        )
        self.assertLessEqual(
            revealed_width,
            document_width,
            f"revealed 1000-char path renders wider than the document: {revealed_width}px > {document_width}px",
        )
