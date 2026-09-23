"""Computed contrast sweep for rendered GWFlow content."""

from __future__ import annotations

import json

from bilbyui.tests.e2e.accessibility_assertions import assert_no_contrast_failures
from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test


def _aaa_advisory(records):
    """Build a non-blocking report for enhanced AAA text contrast."""
    text = [item for item in records if item["kind"] == "text"]
    misses = [item for item in text if item["ratio"] < (4.5 if item["threshold"] == 3 else 7)]
    return {"checked_pairs": len(text), "advisory_failures": misses}


class TestContentContrast(GWFlowJobsPageBase):
    """Sweep one deterministic reachable content state."""

    @async_e2e_test
    async def test_computed_content_contrast(self):
        await self.page.wait_for_selector("#gwflow-job-list")
        result = await assert_no_contrast_failures(
            self.page,
            "#gwflow-job-list",
            context="gwflow_list_search_filter_pagination",
        )
        records = result["records"]
        failures = [item for item in records if item["ratio"] + 0.001 < item["threshold"]]
        advisory = _aaa_advisory(records)
        print("CONTRAST_AAA_ADVISORY=" + json.dumps(advisory, sort_keys=True))
        print(
            "CONTRAST_SWEEP="
            + json.dumps(
                {
                    "pairs": len(records),
                    "failures": len(failures),
                    "dispositions": result["dispositions"],
                },
                sort_keys=True,
            )
        )


class TestDetailContentContrast(GWFlowDetailShellBase):
    @async_e2e_test
    async def test_metadata_computed_content_contrast(self):
        await self.page.wait_for_selector(".detail-shell")
        await assert_no_contrast_failures(self.page, ".detail-shell", context="gwflow_detail_metadata")


class TestFilesContentContrast(GWFlowFilesPageBase):
    @async_e2e_test
    async def test_files_computed_content_contrast(self):
        await self.page.wait_for_selector("#detail-pane")
        await assert_no_contrast_failures(self.page, "#detail-pane", context="gwflow_detail_files")


class TestDemoContentContrast(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_computed_content_contrast(self):
        await self.page.wait_for_selector(".app-container")
        await assert_no_contrast_failures(self.page, ".app-container", context="tech_value_demo")
