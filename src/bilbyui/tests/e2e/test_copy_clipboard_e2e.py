"""Clipboard exactness and single status announcement on the demo page.

The copy handler is async (see _tech_value.html): it announces "Copied" only
when ``navigator.clipboard.writeText`` resolves and "Copy failed" when it
rejects. Both paths are covered here, each with its own concrete class and a
single test method (TESTING.md convention 1).
"""

from bilbyui.tests.e2e.base import TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test

# CSP-safe fake installed BEFORE any interaction: headless clipboard
# permissions are flaky and real writes are unobservable. The handler awaits
# ``.then(...)`` on the return value, so the fake must resolve. The trailing
# ``; true`` keeps the assignment from returning the function itself, which
# Playwright's ``evaluate`` would otherwise invoke immediately.
RESOLVED_FAKE = "navigator.clipboard.writeText = (t) => { window.__copied = t; return Promise.resolve(); }; true"
REJECTED_FAKE = "navigator.clipboard.writeText = () => Promise.reject(new Error('denied')); true"


class TestCopyClipboard(TechValueDemoPageBase):
    @async_e2e_test
    async def test_copy_writes_exact_full_value_and_announces_once(self):
        page = self.page
        await page.evaluate(RESOLVED_FAKE)

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


class TestCopyClipboardRejected(TechValueDemoPageBase):
    @async_e2e_test
    async def test_copy_rejection_announces_failure_not_success(self):
        page = self.page
        await page.evaluate(REJECTED_FAKE)

        root = page.locator(".tech-value").first
        await page.locator(".tech-value-copy").first.click()

        # The handler routes the rejection to the second .then callback, so the
        # status must report failure; the page must also survive the rejection
        # (no unhandled rejection breaking the test/page).
        status = root.locator(".tech-value-status")
        await page.wait_for_function("() => document.querySelector('.tech-value-status').textContent === 'Copy failed'")
        self.assertEqual(await status.text_content(), "Copy failed")
        self.assertNotEqual(await status.text_content(), "Copied")
        # The page must remain interactive after the rejected write: a later
        # disclosure toggle proves the rejection did not break the page.
        toggle = root.locator(".tech-value-toggle")
        await toggle.click()
        self.assertEqual(await toggle.get_attribute("aria-expanded"), "true")
