"""Axe accessibility scan of the GWFlow search form (issue #51 AC1).

Scans the ``.gwflow-search-form`` (search input, advanced-syntax input, filter
selects and help toggle) and asserts zero serious/critical violations. The
scope deliberately excludes the job-list rows: their ``btn-outline-primary``
"View" button carries pre-existing contrast debt owned by the results-row
redesign (#52), not by this search/filter work. Chip/pagination accessibility
is asserted separately via template tests (named remove buttons,
``aria-current``, ``rel``).
"""

from bilbyui.tests.e2e.base import GWFlowJobsPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe

AXE_SCOPE_SELECTOR = ".gwflow-search-form"


class TestGWFlowSearchAxeScan(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
        await self.page.wait_for_selector(".result-count")
        await load_axe(self.page)
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)

        blocking = [v for v in violations if v.get("impact") in ("serious", "critical")]
        detail = "\n".join(
            f"- {v['id']} ({v.get('impact')}): "
            + "; ".join(" > ".join(str(part) for part in node["target"]) for node in v["nodes"])
            for v in blocking
        )
        self.assertEqual(
            [],
            blocking,
            f"Expected zero serious/critical axe violations within '{AXE_SCOPE_SELECTOR}', "
            f"found {len(blocking)}:\n{detail}",
        )
