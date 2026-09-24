"""Shape checks and a browser gate for the deterministic GWFlow pathological fixtures."""

from unittest import mock

from asgiref.sync import sync_to_async
from django.urls import reverse

from bilbyui.services.gwflow_metadata import build_metadata_presentation
from bilbyui.tests.e2e.accessibility_assertions import (
    assert_no_horizontal_overflow,
    assert_table_scroll_regions,
)
from bilbyui.tests.e2e.accessibility_cases import VIEWPORT_WIDTHS
from bilbyui.tests.e2e.pathological_fixtures import (
    METADATA_COLUMN_COUNT,
    PATH_LENGTH,
    SNAME,
    SUPEREVENT_EVENT_COUNT,
    VERSION_COUNT,
    build_pathological_fixtures,
)
from bilbyui.tests.e2e.utils import AsyncE2ETestCase, async_e2e_test
from bilbyui.tests.testcases import BilbyTestCase


class PathologicalFixturesTests(BilbyTestCase):
    def test_factories_build_required_pathological_shapes(self):
        fixtures = build_pathological_fixtures(type(self))

        self.assertEqual(len(fixtures["file"].path), PATH_LENGTH)
        self.assertEqual(fixtures["file"].path, "p" * PATH_LENGTH)

        events = fixtures["superevent"]["gracedb"]["events"]
        self.assertEqual(len(events), SUPEREVENT_EVENT_COUNT)

        metadata = fixtures["metadata"]
        event = metadata["gracedb"]["events"][0]
        self.assertEqual(len(event), METADATA_COLUMN_COUNT)
        presentation = build_metadata_presentation(metadata)
        gracedb = next(section for section in presentation.sections if section.id == "gracedb")
        self.assertEqual(len(gracedb.comparative_sets[0].columns), METADATA_COLUMN_COUNT)

        versions = fixtures["versions"]
        self.assertEqual(len(versions), VERSION_COUNT)
        self.assertEqual(sum(version["is_current"] for version in versions), 1)
        self.assertTrue(
            all(
                {"commit_sha", "commit_timestamp", "schema_version", "is_current", "payload"} <= version.keys()
                for version in versions
            )
        )


class _PathologicalDetailPageBase(AsyncE2ETestCase):
    """Test-free base: a GWFlow files region built from the pathological fixtures.

    The combined fixture (job, 1,000-character file path, 100-event superevent,
    12-column metadata, long version list) is created once, and the detail
    services are patched so the live server renders it deterministically.
    """

    user = None
    page = None
    sname = SNAME
    #: Subclasses override to choose which superevent payload the metadata
    #: section renders (e.g. the 100-event payload instead of the 12-column one).
    superevent_fixture = "metadata"
    _patchers = ()

    async def asetUp(self):
        self.fixtures = await sync_to_async(build_pathological_fixtures)(BilbyTestCase)
        self.user = self.fixtures["user"]
        await self.login(self.user)
        self._patchers = (
            mock.patch(
                "bilbyui.views.get_superevent",
                side_effect=lambda sname: (self.fixtures[self.superevent_fixture], "live"),
            ),
            mock.patch(
                "bilbyui.views.get_versions",
                side_effect=lambda sname: (self.fixtures["versions"], "live"),
            ),
        )
        for patcher in self._patchers:
            patcher.start()
        self.addCleanup(self._stop_patchers)
        self.page = await self.browser_context.new_page()
        await self.page.goto(self.detail_url())

    async def open_files_region(self):
        await self.page.click('a[data-gwflow-section][href*="/files/"]')
        await self.page.wait_for_selector(".gw-analysis-block")

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    def _stop_patchers(self):
        for patcher in self._patchers:
            patcher.stop()

    def detail_url(self) -> str:
        return f"{self.live_server_url}{reverse('bilbyui:gwflow_job_detail', args=[self.sname])}"


class TestPathologicalResponsiveCrawl(_PathologicalDetailPageBase):
    """Five-width overflow crawl over the pathological metadata and files regions."""

    @async_e2e_test
    async def test_pathological_detail_has_no_horizontal_page_overflow(self):
        for route in ("metadata", "files"):
            if route == "files":
                await self.open_files_region()
            for width in VIEWPORT_WIDTHS:
                with self.subTest(case=f"pathological-{route} width={width}"):
                    await self.page.set_viewport_size({"width": width, "height": 900})
                    await self.page.reload()
                    await self.page.wait_for_load_state("networkidle")
                    context = f"pathological-{route} width={width}"
                    await assert_no_horizontal_overflow(self.page, context=context)
                    await assert_table_scroll_regions(self.page, context=context)


class TestPathologicalSupereventEvents(_PathologicalDetailPageBase):
    """The 100-event superevent renders every event without five-width overflow."""

    superevent_fixture = "superevent"

    @async_e2e_test
    async def test_superevent_renders_100_events_without_overflow(self):
        await self.page.wait_for_selector("#gracedb-comparison-table")
        rows = self.page.locator("#gracedb-comparison-table tbody tr")
        self.assertEqual(await rows.count(), SUPEREVENT_EVENT_COUNT)
        for width in VIEWPORT_WIDTHS:
            with self.subTest(case=f"pathological-superevent width={width}"):
                await self.page.set_viewport_size({"width": width, "height": 900})
                await self.page.reload()
                await self.page.wait_for_load_state("networkidle")
                context = f"pathological-superevent width={width}"
                await assert_no_horizontal_overflow(self.page, context=context)
                await assert_table_scroll_regions(self.page, context=context)


class TestPathologicalVersionList(_PathologicalDetailPageBase):
    """The long version history renders every version without five-width overflow."""

    @async_e2e_test
    async def test_version_list_renders_all_versions_without_overflow(self):
        await self.page.click('a[data-gwflow-section][href*="/history/"]')
        await self.page.wait_for_selector(".gwflow-history__desktop-list")
        links = self.page.locator(".gwflow-history__desktop-list a[data-version-link]")
        self.assertEqual(await links.count(), VERSION_COUNT)
        for width in VIEWPORT_WIDTHS:
            with self.subTest(case=f"pathological-versions width={width}"):
                await self.page.set_viewport_size({"width": width, "height": 900})
                await self.page.reload()
                await self.page.wait_for_load_state("networkidle")
                context = f"pathological-versions width={width}"
                await assert_no_horizontal_overflow(self.page, context=context)
                await assert_table_scroll_regions(self.page, context=context)
