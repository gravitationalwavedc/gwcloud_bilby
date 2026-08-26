"""Clipboard exactness and single status announcement on the demo page."""

from bilbyui.tests.e2e.base import TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test


class TestCopyClipboard(TechValueDemoPageBase):
    @async_e2e_test
    async def test_copy_writes_exact_full_value_and_announces_once(self):
        page = self.page
        # CSP-safe fake installed BEFORE any interaction: headless clipboard
        # permissions are flaky and real writes are unobservable.
        await page.evaluate("navigator.clipboard.writeText = (t) => { window.__copied = t; }")

        root = page.locator(".tech-value").first
        await page.locator(".tech-value-copy").first.click()

        expected = await root.locator(".tech-value-full").text_content()
        copied = await page.evaluate("window.__copied")
        self.assertIsNotNone(copied, "copy handler never invoked navigator.clipboard.writeText")
        # Exact equality against raw textContent: no whitespace normalization.
        self.assertEqual(copied, expected)

        status = root.locator(".tech-value-status")
        self.assertEqual(await status.inner_text(), "Copied")

        statuses = page.locator(".tech-value-status")
        announced = 0
        for i in range(await statuses.count()):
            if (await statuses.nth(i).text_content() or "").strip():
                announced += 1
        self.assertLessEqual(announced, 1, f"expected at most one status message, got {announced}")
