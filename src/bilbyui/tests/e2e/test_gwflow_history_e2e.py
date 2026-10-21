"""Browser behaviour for the version-history master-detail view (issue #57).

Covers the acceptance-criteria browser paths that unit tests cannot reach:
URL-backed selection with back/forward restoration, deep-link landing, the
keyboard-only select -> compare -> read flow, axe accessibility scans of the
rewritten semantic-diff presentation (`.gwflow-changes`, issue #120), and
320px horizontal-overflow containment of that presentation.
``get_versions``/``get_version``/``get_diff`` are patched at the view layer
(visible to the live-server thread because ``StaticLiveServerTestCase`` runs
it in a thread of the same process) so the history pane renders deterministic
metadata rows and production-shaped per-version detail and semantic-diff
payloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from asgiref.sync import sync_to_async
from django.urls import reverse

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.utils import AsyncE2ETestCase, async_e2e_test, load_axe, run_axe
from bilbyui.tests.testcases import BilbyTestCase

SNAME = "S230601ag"
SHA_V1 = "1111111111111111111111111111111111111111"
SHA_V2 = "2222222222222222222222222222222222222222"
SHA_V3 = "3333333333333333333333333333333333333333"

#: `version_number`s backing SHA_V1/SHA_V2 in `_versions()`, reused by the
#: semantic-diff payloads below so `adapt_semantic_diff`'s request-match
#: checks (`baseline_version`/`selected_version`) succeed.
BASELINE_VERSION_NUMBER = 1023
SELECTED_VERSION_NUMBER = 1024

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gwflow_diff"
AXE_SCOPE_SELECTOR = ".gwflow-changes"


def _versions():
    return (
        [
            {
                "commit_sha": SHA_V1,
                "version_number": 1023,
                "record_timestamp": "2026-08-08 10:00:00 UTC",
                "is_current": False,
            },
            {
                "commit_sha": SHA_V2,
                "version_number": 1024,
                "record_timestamp": "2026-08-09 10:00:00 UTC",
                "is_current": False,
            },
            {
                "commit_sha": SHA_V3,
                "version_number": 1025,
                "record_timestamp": "2026-08-10 10:00:00 UTC",
                "is_current": True,
            },
        ],
        "live",
    )


def _single_version():
    """A one-entry versions list, forcing `diff_outcome.status == "no_baseline"`."""
    return [
        {
            "commit_sha": SHA_V1,
            "version_number": BASELINE_VERSION_NUMBER,
            "record_timestamp": "2026-08-08 10:00:00 UTC",
            "is_current": True,
        },
    ]


def _version_detail(sname, version_ref):
    versions = {
        1023: (SHA_V1, {"info": {"status": "draft"}}),
        1024: (SHA_V2, {"info": {"status": "ready"}, "extra": "v2-only"}),
        1025: (SHA_V3, {"info": {"status": "ready"}, "extra": "v3-only"}),
    }
    if isinstance(version_ref, str):
        version_ref = {sha: version_number for version_number, (sha, _) in versions.items()}[version_ref]

    sha, payload = versions[version_ref]
    return (
        {
            "sname": sname,
            "commit_sha": sha,
            "raw_payload": payload,
            "version_number": version_ref,
        },
        "live",
    )


def _load_semantic_fixture(name: str) -> dict:
    """Load a `gwflow_diff` fixture, retargeted to this module's sname/versions.

    Mirrors `TestGWFlowHistoryRenderedOutcomes.load_fixture` in
    `test_gwflow_views_history.py`: the fixture's `sname`/`baseline_version`/
    `selected_version` are overwritten to match what this module's `_versions()`
    resolves for `?version={SHA_V2}&compare=prev`, so `adapt_semantic_diff`'s
    request-match checks accept the payload.
    """
    with (FIXTURE_DIR / name).open(encoding="utf-8") as fixture:
        payload = json.load(fixture)
    payload["sname"] = SNAME
    payload["baseline_version"] = BASELINE_VERSION_NUMBER
    payload["selected_version"] = SELECTED_VERSION_NUMBER
    return payload


def _empty_semantic_payload() -> dict:
    return {
        "sname": SNAME,
        "baseline_version": BASELINE_VERSION_NUMBER,
        "selected_version": SELECTED_VERSION_NUMBER,
        "baseline_timestamp": "2026-08-08T10:00:00Z",
        "selected_timestamp": "2026-08-09T10:00:00Z",
        "changes": [],
    }


def _wide_semantic_payload() -> dict:
    """A diff payload with a long identity and a deeply nested field value.

    Drives the 320px containment check: the long `identity` exercises
    `_tech_value.html`'s containment, and the deeply nested `field_diffs`
    value exercises the new renderer's `<dl>`/`<ul>` containment rule
    (design 125 S8.3, `.gwflow-changes__record { dt, dd { overflow-wrap:
    anywhere; } }`).
    """
    long_identity = "pe-" + "x" * 300
    deep_value = {
        "level_one": {
            "level_two": {
                "level_three": {
                    "level_four": "deeply-nested-value-" + "y" * 200,
                },
            },
        },
    }
    return {
        "sname": SNAME,
        "baseline_version": BASELINE_VERSION_NUMBER,
        "selected_version": SELECTED_VERSION_NUMBER,
        "baseline_timestamp": "2026-08-08T10:00:00Z",
        "selected_timestamp": "2026-08-09T10:00:00Z",
        "changes": [
            {
                "entity_type": "analysis",
                "identity": long_identity,
                "kind": "modified",
                "before": {"value": "before"},
                "after": {"value": "after"},
                "field_diffs": {
                    "nested": {
                        "baseline": deep_value,
                        "selected": deep_value,
                    },
                },
            },
        ],
    }


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


class GWFlowHistoryDiffPageBase(AsyncE2ETestCase):
    """A logged-in browser page on the history pane, with a mocked semantic diff.

    Independent of `GWFlowHistoryPageBase` (rather than subclassing it) so that
    `get_versions`/`get_diff` are each patched exactly once per test, avoiding
    patch-stacking ordering hazards between a shared base and a subclass.
    """

    user = None
    page = None
    #: Versions list driving the rail; override for the `no_baseline` status.
    versions_list = None
    #: `(payload, state)` returned by the mocked `get_diff`.
    diff_payload = None
    diff_state = "live"
    initial_query = f"?version={SHA_V2}&compare=prev"

    async def asetUp(self):
        self.user = await sync_to_async(self._create_user)()
        await self.login(self.user)
        await sync_to_async(self._create_fixtures)()

        versions = self.versions_list if self.versions_list is not None else _versions()[0]
        self._get_versions_patcher = mock.patch(
            "bilbyui.views.get_versions",
            side_effect=lambda sname: (versions, "live"),
        )
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
        self._get_diff_patcher = mock.patch(
            "bilbyui.views.get_diff",
            return_value=(self.diff_payload, self.diff_state),
        )
        self._get_diff_patcher.start()
        self.addCleanup(self._get_diff_patcher.stop)

        self.page = await self.browser_context.new_page()
        await self.page.set_viewport_size({"width": 1280, "height": 800})
        await self.page.goto(self.history_url() + self.initial_query)

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    def _create_user(self):
        return BilbyTestCase.create_user(
            name="e2e gwflow history diff",
            primary_email="e2e-gwflow-history-diff@example.com",
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


class GWFlowHistoryDiffAxeStatusBase(GWFlowHistoryDiffPageBase):
    """Shared axe-violation assertion for one `diff_outcome.status` rendering.

    Mirrors `GWFlowMetadataPageBase`'s assertion helper in
    `test_gwflow_metadata_axe_e2e.py` exactly, scoped to `.gwflow-changes`.
    """

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


class TestGWFlowHistorySemanticAxeScan(GWFlowHistoryDiffAxeStatusBase):
    """`diff_outcome.status == "semantic"`, the golden fixture (all entity/kind combinations)."""

    diff_payload = _load_semantic_fixture("semantic_diff.json")
    diff_state = "live"

    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        await load_axe(self.page)
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_serious_or_critical_violations(violations)


class TestGWFlowHistorySemanticAxeScanWithDetailsOpened(GWFlowHistoryDiffAxeStatusBase):
    """Same golden fixture, scanned again with a field-diff `<details>` opened."""

    diff_payload = _load_semantic_fixture("semantic_diff.json")
    diff_state = "live"

    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations_with_details_opened(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        details = self.page.locator(f"{AXE_SCOPE_SELECTOR} details").first
        summary = details.locator("summary")
        await summary.focus()
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_selector(f"{AXE_SCOPE_SELECTOR} details[open]", state="attached", timeout=5000)
        await load_axe(self.page)
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_serious_or_critical_violations(violations)


class TestGWFlowHistorySemanticEmptyAxeScan(GWFlowHistoryDiffAxeStatusBase):
    """`diff_outcome.status == "semantic_empty"`."""

    diff_payload = _empty_semantic_payload()
    diff_state = "live"

    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        await load_axe(self.page)
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_serious_or_critical_violations(violations)


class TestGWFlowHistoryNoBaselineAxeScan(GWFlowHistoryDiffAxeStatusBase):
    """`diff_outcome.status == "no_baseline"` (a single version, no earlier one to compare)."""

    versions_list = _single_version()
    diff_payload = None
    diff_state = "live"
    initial_query = ""

    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        await load_axe(self.page)
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_serious_or_critical_violations(violations)


class TestGWFlowHistoryUnavailableAxeScan(GWFlowHistoryDiffAxeStatusBase):
    """`diff_outcome.status == "unavailable"` (the semantic-diff service is down)."""

    diff_payload = None
    diff_state = "down"

    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        await load_axe(self.page)
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_serious_or_critical_violations(violations)


class TestGWFlowHistoryUnavailableKeyboardRetry(GWFlowHistoryDiffPageBase):
    """Keyboard activation retries the unavailable semantic comparison."""

    diff_payload = None
    diff_state = "down"

    @async_e2e_test
    async def test_try_again_activates_by_keyboard(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        retry = self.page.get_by_role(
            "link",
            name="Try the semantic comparison again",
        )
        await retry.focus()
        self.assertTrue(
            await retry.evaluate("element => element === document.activeElement"),
            "the Try again link must receive keyboard focus",
        )
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        self.assertIn(
            "The semantic comparison service is unavailable.",
            " ".join((await self.page.content()).split()),
        )


class TestGWFlowHistoryFailedAxeScan(GWFlowHistoryDiffAxeStatusBase):
    """`diff_outcome.status == "failed"` (a malformed/unvalidatable payload)."""

    diff_payload = None
    diff_state = "malformed"

    @async_e2e_test
    async def test_no_serious_or_critical_axe_violations(self):
        await self.page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")
        await load_axe(self.page)
        violations = await run_axe(self.page, AXE_SCOPE_SELECTOR)
        self.assert_no_serious_or_critical_violations(violations)


class TestGWFlowHistoryOverflow320(GWFlowHistoryDiffPageBase):
    """320px horizontal-overflow containment with a long identity and a deeply nested value.

    Mirrors `test_gwflow_metadata_overflow_320_e2e.py`'s pattern:
    `document.documentElement.scrollWidth <= window.innerWidth`.
    """

    diff_payload = _wide_semantic_payload()
    diff_state = "live"

    @async_e2e_test
    async def test_wide_change_content_contained_at_320px(self):
        page = self.page
        await page.set_viewport_size({"width": 320, "height": 700})
        await page.reload()
        await page.wait_for_selector(AXE_SCOPE_SELECTOR, state="visible")

        # Open the field-diff disclosure so the deeply nested <dl>/<ul> is
        # actually laid out (a collapsed <details> cannot overflow).
        details = page.locator(f"{AXE_SCOPE_SELECTOR} details").first
        await details.locator("summary").click()
        await page.wait_for_selector(f"{AXE_SCOPE_SELECTOR} details[open]", state="attached", timeout=5000)

        metrics = await page.evaluate(
            "({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth })"
        )
        self.assertLessEqual(
            metrics["scrollWidth"],
            metrics["innerWidth"],
            "document scrolls horizontally at 320px: "
            f"scrollWidth={metrics['scrollWidth']} > innerWidth={metrics['innerWidth']}",
        )
