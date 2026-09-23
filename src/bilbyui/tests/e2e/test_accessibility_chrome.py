"""Isolated axe accessibility scan for shared application chrome."""

from bilbyui.tests.e2e.base import GWFlowJobsPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe

CHROME_SCOPE = ".app-navbar"
BLOCKING_IMPACTS = {"serious", "critical"}


def _format_findings(violations):
    """Return blocking shell findings and actionable diagnostics."""
    blocking = [violation for violation in violations if violation.get("impact") in BLOCKING_IMPACTS]
    lines = []
    for violation in blocking:
        for node in violation.get("nodes", []):
            target = " > ".join(str(part) for part in node.get("target", []))
            html = " ".join(node.get("html", "").split())[:240]
            lines.append(
                f"rule={violation.get('id')} impact={violation.get('impact')} "
                f"selector={target!r} html={html!r} scope={CHROME_SCOPE!r}"
            )
    return blocking, "\n".join(lines)


class TestAccessibilityChrome(GWFlowJobsPageBase):
    """Scan shared app shell separately from route content."""

    @async_e2e_test
    async def test_shared_chrome_has_no_blocking_axe_findings(self):
        await self.page.wait_for_selector(CHROME_SCOPE, state="visible")
        await load_axe(self.page)
        violations = await run_axe(self.page, CHROME_SCOPE)
        blocking, diagnostics = _format_findings(violations)
        self.assertEqual(
            [],
            blocking,
            "Serious/critical app-chrome axe findings:\n" + diagnostics,
        )
