"""Mobile filter-disclosure flow for the GWFlow search form.

At a mobile viewport (<768px) the common filters collapse behind a "Filters"
disclosure button; the always-visible advanced-syntax input sits directly
under it. This test asserts the disclosure reveals the stacked labelled
selects and that interacting with a filter select updates the list.
"""

from __future__ import annotations

from bilbyui.tests.e2e.base import GWFlowJobsPageBase
from bilbyui.tests.e2e.utils import async_e2e_test

MOBILE_VIEWPORT = {"width": 375, "height": 700}

FILTER_SELECT_IDS = ("library", "review_status", "time_range")


class TestGWFlowMobileFilters(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_mobile_filters_disclosure_flow(self):
        page = self.page
        await page.set_viewport_size(MOBILE_VIEWPORT)
        await page.reload()
        await page.wait_for_selector(".result-count")

        # The "Filters" disclosure button is the only filter entry point at
        # mobile width.
        filters_button = page.locator("button[data-target='#search-filters']")
        self.assertTrue(await filters_button.is_visible(), "Filters disclosure button must be visible at mobile width")

        # The advanced-syntax input is always visible and sits directly under
        # the Filters button (not hidden behind the disclosure).
        search_input = page.locator("#search")
        self.assertTrue(await search_input.is_visible(), "advanced-syntax input must be visible at mobile width")
        button_box = await filters_button.bounding_box()
        input_box = await search_input.bounding_box()
        self.assertIsNotNone(button_box, "Filters button must have a bounding box")
        self.assertIsNotNone(input_box, "advanced-syntax input must have a bounding box")
        self.assertGreaterEqual(
            input_box["y"],
            button_box["y"] + button_box["height"] - 1,
            "advanced-syntax input must be directly under the Filters button",
        )

        # The labelled selects start collapsed behind the disclosure.
        for select_id in FILTER_SELECT_IDS:
            self.assertFalse(
                await page.locator(f"#{select_id}").is_visible(),
                f"#{select_id} must be hidden before disclosure",
            )

        # Reveal the stacked labelled selects.
        await filters_button.click()
        self.assertEqual(
            await filters_button.get_attribute("aria-expanded"),
            "true",
            "Filters button must report expanded after disclosure",
        )

        # Each select has a programmatic label and is now visible.
        boxes = []
        for select_id in FILTER_SELECT_IDS:
            select = page.locator(f"#{select_id}")
            self.assertTrue(await select.is_visible(), f"#{select_id} must be visible after disclosure")
            self.assertEqual(
                await page.locator(f"label[for='{select_id}']").count(),
                1,
                f"#{select_id} must have a programmatic <label for>",
            )
            box = await select.bounding_box()
            self.assertIsNotNone(box, f"#{select_id} must have a bounding box")
            boxes.append((select_id, box))

        # The selects stack vertically (each below the previous).
        for (prev_id, prev_box), (cur_id, cur_box) in zip(boxes, boxes[1:]):
            self.assertGreaterEqual(
                cur_box["y"],
                prev_box["y"] + prev_box["height"] - 1,
                f"#{cur_id} must stack below #{prev_id}",
            )

        # Interacting with a filter select updates the list (result count +
        # active-filter chip).
        await page.locator("#library").select_option("lib1")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('1000'); }",
            timeout=10000,
        )
        self.assertIn("library=lib1", page.url)
        self.assertGreaterEqual(
            await page.locator(".filter-chip", has_text="Library: lib1").count(),
            1,
            "Library: lib1 chip must be present after selecting the filter",
        )
