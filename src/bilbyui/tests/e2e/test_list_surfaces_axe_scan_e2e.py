"""Axe accessibility scan of the shared search form across all three job-list
surfaces (issue #51 AC1).

Scans ``.gwflow-search-form`` on GWFlow, My Jobs, and Public Jobs and asserts
zero serious/critical violations on each. The job-list rows are excluded: their
``btn-outline-primary`` "View" button carries pre-existing contrast debt owned
by the results-row redesign (#52).
"""

from unittest import mock

from django.urls import reverse

from bilbyui.tests.e2e.base import GWFlowJobsPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe

AXE_SCOPE_SELECTOR = ".gwflow-search-form"

SURFACES = ("bilbyui:gwflow_jobs", "bilbyui:my_jobs", "bilbyui:public_jobs")


def _public_jobs_side_effect(user, *, search="", time_range="all", page=1, page_size=20, **kwargs):
    return {
        "jobs": {},
        "records": [],
        "job_controller_jobs": {},
        "has_next": False,
        "total": 0,
        "page": page,
        "page_size": page_size,
        "state": "ok",
    }


class TestListSurfacesAxeScan(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations_on_all_surfaces(self):
        # Public jobs is ES-backed; mock it so the surface renders without ES.
        with mock.patch("bilbyui.views.list_public_jobs", side_effect=_public_jobs_side_effect):
            for url_name in SURFACES:
                url = f"{self.live_server_url}{reverse(url_name)}"
                await self.page.goto(url)
                await self.page.wait_for_selector(".gwflow-search-form")
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
                    f"{url_name}: expected zero serious/critical axe violations within "
                    f"'{AXE_SCOPE_SELECTOR}', found {len(blocking)}:\n{detail}",
                )
