"""Axe accessibility scan of the technical-value demo page.

The scan is deliberately scoped to the demo content cards rather than the
whole document: the app shell (navbar links) and the theme's default
``<code>`` colour both fail WCAG AA contrast on master — pre-existing debt
that this component neither introduces nor owns. Scoping the gate to the
component's own region enforces "the technical-value component adds zero
serious/critical violations" without blocking on shell-wide contrast fixes,
which are tracked separately.
"""

from bilbyui.tests.e2e.base import TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe

# Tightest wrapper containing every demo card (demo_tech_value.html renders
# all variants inside .card elements under .app-container). This excludes the
# navbar chrome from base.html and the intro prose's pre-existing <code>
# styling, both of which carry known contrast debt tracked outside this suite.
AXE_SCOPE_SELECTOR = ".app-container .card"


class TestDemoAxeScan(TechValueDemoPageBase):
    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
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
