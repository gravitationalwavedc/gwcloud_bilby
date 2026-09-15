"""Axe accessibility scan of the Bilby job section controls (issue #58)."""

from .test_job_section_shell_e2e import JobSectionShellBase
from .utils import async_e2e_test, load_axe, run_axe

AXE_SCOPE_SELECTOR = ".app-container"
ACCESSIBLE_NAME_AND_LABEL_RULES = {
    "aria-command-name",
    "aria-input-field-name",
    "aria-progressbar-name",
    "button-name",
    "label",
    "link-name",
    "select-name",
}


class TestJobSectionAxeScan(JobSectionShellBase):
    def assert_no_accessible_name_or_label_violations(self, violations):
        blocking = [
            violation
            for violation in violations
            if violation.get("id") in ACCESSIBLE_NAME_AND_LABEL_RULES
        ]
        detail = "\n".join(
            f"- {violation['id']} ({violation.get('impact')}): "
            + "; ".join(
                " > ".join(str(part) for part in node["target"])
                for node in violation["nodes"]
            )
            for violation in blocking
        )
        self.assertEqual(
            [],
            blocking,
            f"Expected zero accessible-name or label axe violations within "
            f"'{AXE_SCOPE_SELECTOR}', found {len(blocking)}:\n{detail}",
        )

    @async_e2e_test
    async def test_no_accessible_name_or_label_axe_violations(self):
        await self.page.goto(self.parameters_url)
        await self.page.wait_for_selector(
            f"{AXE_SCOPE_SELECTOR} #job-section-heading"
        )
        await load_axe(self.page)

        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_accessible_name_or_label_violations(violations)

        await self.page.locator('button[aria-label="Edit name"]').click()
        await self.page.locator(
            'input[name="name"], button[aria-label="Save name"]'
        ).first.wait_for(state="visible")
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_accessible_name_or_label_violations(violations)

        await self.page.locator(
            'button[aria-label="Edit description"]'
        ).click()
        await self.page.locator(
            'textarea[name="description"], '
            'button[aria-label="Save description"]'
        ).first.wait_for(state="visible")
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_accessible_name_or_label_violations(violations)
