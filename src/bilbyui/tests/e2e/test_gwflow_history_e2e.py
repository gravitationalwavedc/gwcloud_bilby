"""Browser behaviour for the version-history master-detail view (issue #57).

Covers the acceptance-criteria browser paths that unit tests cannot reach:
URL-backed selection with back/forward restoration, deep-link landing, and the
keyboard-only select -> compare -> read flow. ``get_versions`` is patched at
the view layer (visible to the live-server thread because
``StaticLiveServerTestCase`` runs it in a thread of the same process) so the
history pane renders deterministic metadata rows and production-shaped\nper-version detail payloads.
"""

from __future__ import annotations

from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from asgiref.sync import sync_to_async
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.utils import AsyncE2ETestCase, async_e2e_test
from bilbyui.tests.testcases import BilbyTestCase

SNAME = "S230601ag"
SHA_V1 = "1111111111111111111111111111111111111111"
SHA_V2 = "2222222222222222222222222222222222222222"
SHA_V3 = "3333333333333333333333333333333333333333"


def _versions():
    return (
        [
            {
                "commit_sha": SHA_V1,
                "commit_timestamp": "2026-08-08 10:00:00 UTC",
                "schema_version": "v1",
                "is_current": False,
            },
            {
                "commit_sha": SHA_V2,
                "commit_timestamp": "2026-08-09 10:00:00 UTC",
                "schema_version": "v1",
                "is_current": False,
            },
            {
                "commit_sha": SHA_V3,
                "commit_timestamp": "2026-08-10 10:00:00 UTC",
                "schema_version": "v1",
                "is_current": True,
            },
        ],
        "live",
    )


def _version_detail(sname, sha):
    payloads = {
        SHA_V1: {"info": {"status": "draft"}},
        SHA_V2: {"info": {"status": "ready"}, "extra": "v2-only"},
        SHA_V3: {"info": {"status": "ready"}, "extra": "v3-only"},
    }
    return (
        {"sname": sname, "commit_sha": sha, "raw_payload": payloads[sha]},
        "live",
    )


class GWFlowHistoryPageBase(AsyncE2ETestCase):
    """A logged-in browser page open on the GWFlow history section."""

    user = None
    page = None
    _get_versions_patcher = None
    _get_version_patcher = None
    _get_superevent_patcher = None
    #: Optional query string appended to the initial history URL (e.g. a deep
    #: link). Subclasses set this so the deep link is the FIRST navigation,
    #: avoiding a second `goto` that is flaky in the shared browser server.
    initial_query = ""

    async def asetUp(self):
        self.user = await sync_to_async(self._create_user)()
        await self.login(self.user)
        await sync_to_async(self._create_fixtures)()
        self._get_versions_patcher = mock.patch("bilbyui.views.get_versions", side_effect=lambda sname: _versions())
        self._get_versions_patcher.start()
        self.addCleanup(self._get_versions_patcher.stop)
        self._get_version_patcher = mock.patch(
            "bilbyui.views.get_version",
            side_effect=_version_detail,
        )
        self._get_version_patcher.start()
        self.addCleanup(self._get_version_patcher.stop)
        self._get_superevent_patcher = mock.patch(
            "bilbyui.views.get_superevent",
            return_value=({"sname": SNAME}, "live"),
        )
        self._get_superevent_patcher.start()
        self.addCleanup(self._get_superevent_patcher.stop)
        self.page = await self.browser_context.new_page()
        await self.page.set_viewport_size({"width": 1280, "height": 800})
        await self.page.goto(self.history_url() + self.initial_query)

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    def _create_user(self):
        return BilbyTestCase.create_user(
            name="e2e gwflow history",
            primary_email="e2e-gwflow-history@example.com",
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )

    def _create_fixtures(self):
        GWFlowJob.objects.create(
            sname=SNAME,
            user=self.user,
            libraries=["cbc-workflow-o4a"],
            schema_version="v2",
        )

    def history_url(self) -> str:
        return f"{self.live_server_url}{reverse('bilbyui:gwflow_job_history', args=[SNAME])}"

    def _rail(self):
        return self.page.locator(".gwflow-history__desktop-list")

    def _version_link(self, sha: str):
        return self.page.locator(f'.gwflow-history__desktop-list a[data-version-sha="{sha}"]')

    async def _wait_for_rail(self):
        await self.page.wait_for_selector(".gwflow-history__desktop-list", state="attached", timeout=20000)


class TestHistorySelectionRestore(GWFlowHistoryPageBase):
    """Back/forward URL restoration."""

    @async_e2e_test
    async def test_back_forward_restores_selection(self):
        await self._wait_for_rail()
        # Select v2 via the rail link (HTMX pushes ?version=... to the URL).
        await self._version_link(SHA_V2).click()
        await self.page.wait_for_function(
            "() => location.search.includes('version=2222222222222222222222222222222222222222')",
            timeout=10000,
        )
        # Back returns to the default (current) selection, forward restores v2.
        await self.page.go_back()
        await self.page.go_forward()
        await self.page.wait_for_function(
            "() => location.search.includes('version=2222222222222222222222222222222222222222')",
            timeout=10000,
        )
        selected = self.page.locator(".gwflow-history__desktop-list [aria-current='true']")
        self.assertEqual(await selected.get_attribute("data-version-sha"), SHA_V2)


class TestHistoryDeepLink(GWFlowHistoryPageBase):
    """Deep-link landing (initial navigation to a version+compare URL)."""

    initial_query = f"?version={SHA_V2}&compare=prev"

    @async_e2e_test
    async def test_deep_link_renders_selected_version(self):
        await self._wait_for_rail()
        selected = self.page.locator(".gwflow-history__desktop-list [aria-current='true']")
        self.assertEqual(await selected.get_attribute("data-version-sha"), SHA_V2)
        self.assertIn("v2-only", await self.page.content())


class TestHistoryKeyboardWalkthrough(GWFlowHistoryPageBase):
    """Keyboard-only select -> compare -> read flow."""

    @async_e2e_test
    async def test_keyboard_select_compare_read(self):
        await self._wait_for_rail()
        rail = self._rail()
        links = rail.locator("[data-version-link]")
        count = await links.count()
        self.assertGreaterEqual(count, 2)

        # The rail renders newest-first; select a NON-current version so the
        # "vs current" comparison is meaningful (not a self-comparison).
        target_sha = await links.nth(1).get_attribute("data-version-sha")

        # Keyboard-only select: focus a version link and activate it with Enter
        # (native link behaviour), which must update the URL to that version.
        await links.nth(1).focus()
        self.assertEqual(
            await self.page.evaluate("document.activeElement.getAttribute('data-version-sha')"),
            target_sha,
            "a version link must be keyboard-focusable",
        )
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_function(
            f"() => location.search.includes('version={target_sha}')",
            timeout=10000,
        )

        # Compare: operate the native compare controls using only the keyboard.
        compare = self.page.locator(".gwflow-history__compare")
        await compare.wait_for(state="attached", timeout=10000)
        current_radio = compare.locator('input[name="compare"][value="current"]')
        await current_radio.focus()
        await self.page.keyboard.press("Space")
        await compare.locator('button[type="submit"]').press("Enter")
        await self.page.wait_for_function(
            "() => location.search.includes('compare=current')",
            timeout=10000,
        )

        # Read: the changes result must render with a labelled baseline.
        await self.page.wait_for_selector(".gwflow-changes", state="attached", timeout=10000)
        normalized = " ".join((await self.page.content()).split())
        self.assertIn("Changes from current version", normalized)
