"""Axe accessibility scan of the GWFlow metadata presentation (issue #55 AC5)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from asgiref.sync import sync_to_async
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.utils import AsyncE2ETestCase, async_e2e_test, load_axe, run_axe
from bilbyui.tests.testcases import BilbyTestCase

AXE_SCOPE_SELECTOR = ".gwflow-metadata"
METADATA_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "metadata_corpus" / "complete_curated.json"


class GWFlowMetadataPageBase(AsyncE2ETestCase):
    """A logged-in browser page showing deterministic rich GWFlow metadata."""

    user = None
    page = None
    sname = "S230601ag"
    _get_superevent_patcher = None

    async def asetUp(self):
        self.user = await sync_to_async(self._create_user)()
        await self.login(self.user)
        await sync_to_async(self._create_fixtures)()

        payload = json.loads(METADATA_FIXTURE.read_text(encoding="utf-8"))
        self._get_superevent_patcher = mock.patch(
            "bilbyui.views.get_superevent",
            return_value=(payload, "live"),
        )
        self._get_superevent_patcher.start()
        self.addCleanup(self._get_superevent_patcher.stop)

        self.page = await self.browser_context.new_page()
        await self.page.goto(self.metadata_url())

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    def _create_user(self):
        return BilbyTestCase.create_user(
            name="e2e gwflow metadata",
            primary_email="e2e-gwflow-metadata@example.com",
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )

    def _create_fixtures(self):
        GWFlowJob.objects.create(
            sname=self.sname,
            user=self.user,
            libraries=["cbc-workflow-o4a"],
            schema_version="v2",
        )

    def metadata_url(self) -> str:
        return f"{self.live_server_url}{reverse('bilbyui:gwflow_job_metadata', args=[self.sname])}"


class TestGWFlowMetadataAxeScan(GWFlowMetadataPageBase):
    def assert_no_serious_or_critical_violations(self, violations):
        blocking = [violation for violation in violations if violation.get("impact") in ("serious", "critical")]
        detail = "\n".join(
            f"- {violation['id']} ({violation.get('impact')}): "
            + "; ".join(" > ".join(str(part) for part in node["target"]) for node in violation["nodes"])
            for violation in blocking
        )
        self.assertEqual(
            [],
            blocking,
            f"Expected zero serious/critical axe violations within "
            f"'{AXE_SCOPE_SELECTOR}', found {len(blocking)}:\n{detail}",
        )

    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        await load_axe(self.page)

        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_serious_or_critical_violations(violations)

        disclosure = self.page.get_by_text(
            re.compile(r"^Show all \d+ fields$"),
            exact=True,
        )
        if await disclosure.count():
            await disclosure.first.click()
            await self.page.locator(f"{AXE_SCOPE_SELECTOR} [x-show]").first.wait_for(state="visible")
            violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
            self.assert_no_serious_or_critical_violations(violations)
