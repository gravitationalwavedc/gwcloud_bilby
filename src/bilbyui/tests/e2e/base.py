"""
Shared authenticated-page setup for the e2e tests.

Contains NO test methods (TESTING.md convention 2): concrete test classes
inherit a base class and each add exactly one test.

- :class:`TechValueDemoPageBase` — the technical-value demo route.
- :class:`GWFlowJobsPageBase` — the GWFlow jobs list. The list view talks to
  Elasticsearch through ``bilbyui.views.list_gwflow_jobs`` /
  ``bilbyui.views.list_gwflow_filter_options``; these are patched at the view
  layer so the live server renders real DB rows without an ES backend. The
  patch is visible to the live-server thread because
  ``StaticLiveServerTestCase`` runs it in a thread of the same process.
"""

from __future__ import annotations

from unittest import mock

from asgiref.sync import sync_to_async
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.utils import AsyncE2ETestCase
from bilbyui.tests.testcases import BilbyTestCase

DEMO_URL_NAME = "bilbyui:tech_value_demo"
GWFLOW_URL_NAME = "bilbyui:gwflow_jobs"

#: Deterministic per-param totals so the DOM result-count reveals which request
#: state won a race (see test_search_race_e2e.py).
LIBRARY_TOTALS = {"lib1": 1000, "lib2": 2000}
REVIEW_STATUS_TOTALS = {"approved": 3000}


def _build_gwflow_result(jobs, total=0, has_next=False, page=1, page_size=20):
    """Build the service result dict shape the view renders rows from."""
    records = [{"_id": str(job.id), "_source": {"analyses": []}} for job in jobs]
    return {
        "jobs": {job.id: job for job in jobs},
        "records": records,
        "has_next": has_next,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def default_gwflow_jobs_side_effect(
    user, *, search="", library="", review_status="", time_range="all", page=1, page_size=20, **kwargs
):
    """Return a result whose ``total`` encodes the request params.

    The total is deterministic so tests can assert which request state the DOM
    reflects: ``len(search)`` plus a per-library / per-review-status
    contribution. The rows are the DB fixtures, so the list renders real rows.
    """
    jobs = list(GWFlowJob.objects.order_by("id"))
    total = len(search) + LIBRARY_TOTALS.get(library, 0) + REVIEW_STATUS_TOTALS.get(review_status, 0)
    return _build_gwflow_result(jobs, total=total)


class TechValueDemoPageBase(AsyncE2ETestCase):
    """
    A logged-in browser page open on the tech-value demo route.

    ``asetUp`` creates a user through the Django ORM, logs them in via the
    cookie-based login helper and opens a fresh page on the demo URL.
    """

    user = None
    page = None

    async def asetUp(self):
        self.user = await sync_to_async(self._create_user)()
        await self.login(self.user)
        self.page = await self.browser_context.new_page()
        await self.page.goto(self.demo_url())

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    def _create_user(self):
        # Reuse the shared test-user factory for parity with unit tests; this
        # class cannot inherit BilbyTestCase (GraphQL client base conflicts
        # with StaticLiveServerTestCase), so its classmethod is called directly.
        return BilbyTestCase.create_user(
            name="e2e tech value",
            primary_email="e2e-tech-value@example.com",
        )

    def demo_url(self) -> str:
        return f"{self.live_server_url}{reverse(DEMO_URL_NAME)}"


class GWFlowJobsPageBase(AsyncE2ETestCase):
    """
    A logged-in browser page open on the GWFlow jobs list.

    ``asetUp`` creates a user + one GWFlowJob fixture through the Django ORM,
    patches the view-level service calls so the live server renders real rows
    without Elasticsearch, logs in via the cookie helper and opens the page.
    """

    user = None
    page = None
    _patchers = ()

    #: Subclasses override to change the mock response (e.g. a slow race mock).
    gwflow_jobs_side_effect = staticmethod(default_gwflow_jobs_side_effect)

    async def asetUp(self):
        self.user = await sync_to_async(self._create_user)()
        await self.login(self.user)
        self._patchers = (
            mock.patch("bilbyui.views.list_gwflow_jobs", side_effect=self.gwflow_jobs_side_effect),
            mock.patch(
                "bilbyui.views.list_gwflow_filter_options",
                return_value={"libraries": ["lib1", "lib2"], "review_statuses": ["approved", "reviewed"]},
            ),
        )
        for patcher in self._patchers:
            patcher.start()
        self.addCleanup(self._stop_patchers)
        await sync_to_async(self._create_fixtures)()
        self.page = await self.browser_context.new_page()
        await self.page.goto(self.gwflow_url())

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    def _stop_patchers(self):
        for patcher in self._patchers:
            patcher.stop()

    def _create_user(self):
        return BilbyTestCase.create_user(
            name="e2e gwflow",
            primary_email="e2e-gwflow@example.com",
        )

    def _create_fixtures(self):
        GWFlowJob.objects.create(sname="S230601ag", user=self.user, libraries=["lib1"])

    def gwflow_url(self) -> str:
        return f"{self.live_server_url}{reverse(GWFLOW_URL_NAME)}"
