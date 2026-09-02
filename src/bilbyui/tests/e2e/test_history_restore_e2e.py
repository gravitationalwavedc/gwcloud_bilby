"""History-restoration regression test (issue #51 round-2 finding).

After back/forward navigation restores a ``page>1`` URL, the hidden page form
control must keep its default of 1 so a subsequent filter change resets to
page 1 (GOV.UK filtering rule) instead of submitting the stale restored page.
"""

from __future__ import annotations

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.base import (
    LIBRARY_TOTALS,
    REVIEW_STATUS_TOTALS,
    GWFlowJobsPageBase,
    _build_gwflow_result,
)
from bilbyui.tests.e2e.utils import async_e2e_test


def _many_pages_side_effect(
    user, *, search="", library="", review_status="", time_range="all", page=1, page_size=20, **kwargs
):
    """Return a result with enough pages that pagination links render."""
    jobs = list(GWFlowJob.objects.order_by("id"))
    total = 100 + len(search) + LIBRARY_TOTALS.get(library, 0) + REVIEW_STATUS_TOTALS.get(review_status, 0)
    return _build_gwflow_result(jobs, total=total, has_next=page < 5)


class TestHistoryRestorePageReset(GWFlowJobsPageBase):
    """A filter change after history restoration must reset to page 1."""

    gwflow_jobs_side_effect = staticmethod(_many_pages_side_effect)

    @async_e2e_test
    async def test_filter_change_after_history_restore_resets_page(self):
        page = self.page
        await page.wait_for_selector(".pagination-wrap")

        # Navigate to page 3 via a pagination link (pushes ?page=3).
        await page.click("a[href*='page=3']")
        await page.wait_for_function(
            "() => location.search.includes('page=3')",
            timeout=10000,
        )

        # Back then forward restores the page=3 URL via popstate.
        await page.go_back()
        await page.go_forward()
        await page.wait_for_function(
            "() => location.search.includes('page=3')",
            timeout=10000,
        )

        # The hidden page control must stay at its form default of 1.
        page_value = await page.evaluate("document.querySelector(\"input[name='page']\").value")
        self.assertEqual(page_value, "1", "hidden page control must not be restored from the URL")

        # Change a filter -> the form submits page=1, not the restored page=3.
        await page.locator("#library").select_option("lib1")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('1100'); }",
            timeout=10000,
        )
        self.assertIn("page=1", page.url)
        self.assertNotIn("page=3", page.url)
