"""Race-condition e2e test for the coordinated GWFlow search form.

The form owns every control and coordinates requests with
``hx-sync="this:replace"`` plus a 300 ms debounce on the search input. This
test fires a search-input change and a filter-select change in quick
succession (within the debounce window) and asserts the final rendered list
matches the LAST request's state — exactly one final DOM state, no
out-of-order resolution.
"""

from __future__ import annotations

import time

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.base import (
    LIBRARY_TOTALS,
    REVIEW_STATUS_TOTALS,
    GWFlowJobsPageBase,
    _build_gwflow_result,
)
from bilbyui.tests.e2e.utils import async_e2e_test

#: Simulated ES latency so concurrent requests genuinely overlap and the
#: hx-sync coordination is exercised rather than trivially serialised.
SLOW_ES_DELAY_SECONDS = 0.4


def _slow_race_side_effect(
    user, *, search="", library="", review_status="", time_range="all", page=1, page_size=20, **kwargs
):
    """Slow ES-like response whose ``total`` encodes the request params.

    The deterministic total (``len(search)`` + per-library / per-review-status
    contribution) lets the test read which request state the DOM reflects from
    the rendered result count.
    """
    time.sleep(SLOW_ES_DELAY_SECONDS)
    jobs = list(GWFlowJob.objects.order_by("id"))
    total = len(search) + LIBRARY_TOTALS.get(library, 0) + REVIEW_STATUS_TOTALS.get(review_status, 0)
    return _build_gwflow_result(jobs, total=total)


class TestGWFlowSearchRace(GWFlowJobsPageBase):
    """Simultaneous search-input + filter-select changes settle on the last request."""

    gwflow_jobs_side_effect = staticmethod(_slow_race_side_effect)

    @async_e2e_test
    async def test_simultaneous_search_and_filter_produce_one_final_state(self):
        page = self.page
        search = page.locator("#search")
        library = page.locator("#library")

        # Sanity: the initial list renders with no filters.
        await page.wait_for_selector(".result-count")
        self.assertIn("0 superevents match", await page.locator(".result-count").text_content())

        # Fire a search-input change (debounced 300 ms) ...
        await search.press_sequentially("abc")
        # ... and a filter-select change within the debounce window.
        await library.select_option("lib1")

        # The coordinated stream must settle on the LAST request's state:
        # search="abc" AND library="lib1" -> total = 3 + 1000 = 1003.
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('1003'); }",
            timeout=10000,
        )

        # Exactly one final state: the count must stay put (no out-of-order
        # resolution flipping it back to an earlier request's value).
        await page.wait_for_timeout(700)
        self.assertIn("1003 superevents match", await page.locator(".result-count").text_content())

        # The settled state is encoded in the URL and the active-filter chip.
        self.assertIn("search=abc", page.url)
        self.assertIn("library=lib1", page.url)
        self.assertGreaterEqual(
            await page.locator(".filter-chip", has_text="Library: lib1").count(),
            1,
            "Library: lib1 chip must be present",
        )

        # Last request wins: switching the filter must replace the previous
        # state entirely (no stale lib1 chip, no stale count).
        await library.select_option("lib2")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('2003'); }",
            timeout=10000,
        )
        self.assertIn("library=lib2", page.url)
        self.assertEqual(
            await page.locator(".filter-chip", has_text="Library: lib1").count(),
            0,
            "stale Library: lib1 chip must be gone",
        )
        self.assertGreaterEqual(
            await page.locator(".filter-chip", has_text="Library: lib2").count(),
            1,
            "Library: lib2 chip must be present",
        )
        await page.wait_for_timeout(700)
        self.assertIn("2003 superevents match", await page.locator(".result-count").text_content())
