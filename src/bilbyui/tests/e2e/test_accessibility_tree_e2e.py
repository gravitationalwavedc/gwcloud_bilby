"""Direct accessibility-tree assertions for the technical-value demo page.

Unlike the axe scan (which checks computed rules) these tests assert the
component's exposed semantics directly through Playwright's role/name queries
and ARIA attributes, so the accessibility contract is verified against the
rendered page rather than inferred from markup.
"""

from bilbyui.tests.e2e.base import TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test

# The copy handler awaits ``.then(...)`` on the write result, so the fake must
# resolve for the success announcement to fire (see _tech_value.html). The
# trailing ``; true`` keeps the assignment from returning the function itself,
# which Playwright's ``evaluate`` would otherwise invoke immediately.
RESOLVED_FAKE = "navigator.clipboard.writeText = (t) => { window.__copied = t; return Promise.resolve(); }; true"


class TestAccessibilityTreeButtons(TechValueDemoPageBase):
    @async_e2e_test
    async def test_copy_and_disclosure_buttons_expose_accessible_names(self):
        page = self.page

        # Path-kind copy button (default copy_label) must be exposed by name.
        copy_path = page.get_by_role("button", name="Copy path")
        self.assertTrue(await copy_path.first.is_visible(), "Copy path button must be visible")

        # Disclosure toggle's sr-only label must be its accessible name.
        show_full = page.get_by_role("button", name="Show full path")
        self.assertTrue(await show_full.first.is_visible(), "Show full path toggle must be visible")

        # Identifier card's explicit copy_label must be the accessible name.
        identifier_card = page.locator(".card", has_text="Identifier mode")
        copy_superevent = identifier_card.get_by_role("button", name="Copy superevent ID")
        self.assertTrue(await copy_superevent.is_visible(), "Copy superevent ID button must be visible")


class TestAccessibilityTreeLiveRegion(TechValueDemoPageBase):
    @async_e2e_test
    async def test_status_live_region_announces_copied(self):
        page = self.page
        await page.evaluate(RESOLVED_FAKE)

        status = page.locator(".tech-value-status").first
        self.assertEqual(await status.get_attribute("role"), "status", "status element must be a live region")

        await page.locator(".tech-value-copy").first.click()
        await page.wait_for_function("() => document.querySelector('.tech-value-status').textContent === 'Copied'")
        self.assertEqual(await status.text_content(), "Copied")


class TestAccessibilityTreeDisclosureContract(TechValueDemoPageBase):
    @async_e2e_test
    async def test_toggle_without_disclosure_id_omits_aria_controls(self):
        # The demo page passes no disclosure_id anywhere, so the optional
        # contract must hold: collapsed by default and no dangling aria-controls.
        toggle = self.page.locator(".tech-value-toggle").first
        self.assertEqual(await toggle.get_attribute("aria-expanded"), "false")
        self.assertIsNone(await toggle.get_attribute("aria-controls"))
