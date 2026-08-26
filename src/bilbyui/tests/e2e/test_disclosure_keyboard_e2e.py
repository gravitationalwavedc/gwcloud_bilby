"""Keyboard operability of the full-value disclosure (APG disclosure pattern)."""

from bilbyui.tests.e2e.base import TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test


class TestDisclosureKeyboard(TechValueDemoPageBase):
    @async_e2e_test
    async def test_disclosure_toggles_with_enter_and_space(self):
        root = self.page.locator(".tech-value").first
        toggle = root.locator(".tech-value-toggle")
        full = root.locator(".tech-value-full")

        await toggle.focus()
        self.assertEqual(await toggle.get_attribute("aria-expanded"), "false")
        self.assertTrue(await full.evaluate("el => el.hidden"), "full block must start [hidden]")
        self.assertFalse(await full.is_visible(), "full block must not be visible before disclosure")

        await toggle.press("Enter")
        self.assertEqual(await toggle.get_attribute("aria-expanded"), "true", "Enter must expand the disclosure")
        self.assertTrue(await full.is_visible(), "Enter must reveal the full-value block")

        await toggle.press(" ")
        self.assertEqual(await toggle.get_attribute("aria-expanded"), "false", "Space must collapse the disclosure")
        self.assertTrue(await full.evaluate("el => el.hidden"), "Space must re-hide via the hidden property")
        self.assertFalse(await full.is_visible(), "full block must be hidden after Space")
