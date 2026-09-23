"""Keyboard-only journeys for token revoke, job rename, and GWFlow."""

from unittest import mock

from asgiref.sync import sync_to_async
from django.urls import reverse
from playwright.async_api import expect

from bilbyui.models import BilbyJob
from bilbyui.services.api_tokens import create_token
from bilbyui.tests.e2e.base import GWFlowDetailShellBase
from bilbyui.tests.e2e.utils import AsyncE2ETestCase, async_e2e_test
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestKeyboardTokenRevoke(AsyncE2ETestCase):
    @async_e2e_test
    async def test_keyboard_token_revoke(self):
        user = await sync_to_async(BilbyTestCase.create_user)(
            name="keyboard token",
            primary_email="keyboard-token@example.com",
        )
        await self.login(user)
        page = await self.browser_context.new_page()

        await sync_to_async(create_token)(user, "e2e-token")

        await page.goto(f"{self.live_server_url}{reverse('bilbyui:api_tokens')}")
        row = page.locator("[data-token-id]").first
        await expect(row).to_be_visible()

        start = row.locator(".token-revoke-start")
        await start.focus()
        await expect(start).to_be_focused()
        await start.press("Enter")

        cancel = row.locator(".token-revoke-cancel")
        await expect(cancel).to_be_visible()
        await expect(cancel).to_be_focused()
        await cancel.press("Shift+Tab")

        confirm = page.get_by_role("button", name="Yes, revoke")
        await expect(confirm).to_be_focused()
        await confirm.press("Enter")
        await expect(row).to_have_count(0)

        status = page.locator("#token-revoke-status")
        await expect(status).to_have_attribute("role", "status")
        await expect(status).to_contain_text("Token revoked")

        await page.keyboard.press("Tab")
        self.assertFalse(await page.evaluate("document.activeElement === document.body"))
        await page.close()


class _KeyboardEditNameBase(AsyncE2ETestCase):
    user = None
    job = None
    page = None

    async def asetUp(self):
        self.user = await sync_to_async(BilbyTestCase.create_user)(
            name="keyboard edit",
            primary_email="keyboard-edit@example.com",
        )
        self.job = await sync_to_async(self._create_job)()
        self._patchers = (
            mock.patch("bilbyui.views.generate_parameter_output", return_value=None),
            mock.patch("bilbyui.views.request_job_filter", return_value=("OK", [])),
            mock.patch("bilbyui.models.BilbyJob.elastic_search_update"),
        )
        for _p in self._patchers:
            _p.start()
        self.addCleanup(self._stop_patchers)
        await self.login(self.user)
        self.page = await self.browser_context.new_page()
        await self.page.goto(f"{self.live_server_url}{reverse('bilbyui:view_job', args=[self.job.id])}")

    def _create_job(self):
        with mock.patch("bilbyui.models.BilbyJob.elastic_search_update"):
            return BilbyJob.objects.create(
                user_id=self.user.id,
                name="Viewable job",
                description="d",
                job_controller_id=10001,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Viewable job"}),
            )

    def _stop_patchers(self):
        for _p in getattr(self, "_patchers", ()):
            _p.stop()

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None


class TestKeyboardEditName(_KeyboardEditNameBase):
    @async_e2e_test
    async def test_keyboard_edit_name(self):
        container = self.page.locator(f"#field-name-{self.job.id}")
        edit = container.locator('.edit-button[aria-label="Edit name"]')
        await edit.focus()
        await expect(edit).to_be_focused()
        await edit.press("Enter")

        field = self.page.locator("#job-name-input")
        await expect(field).to_be_focused()
        await field.fill("")
        await field.type("jobname")
        await field.press("Tab")
        save_button = self.page.locator('.save-button[aria-label="Save name"]')
        await expect(save_button).to_be_focused()
        await save_button.press("Enter")
        await expect(self.page.locator("#job-name-input")).to_have_count(0)
        heading = self.page.locator(f"#field-name-{self.job.id} h1.job-inline-field__value")
        await expect(heading).to_have_text("jobname")

        edit = self.page.locator(f'#field-name-{self.job.id} .edit-button[aria-label="Edit name"]')
        await edit.focus()
        await edit.press("Enter")
        field = self.page.locator("#job-name-input")
        await expect(field).to_be_focused()
        await field.fill("ab")
        await field.press("Enter")

        await expect(field).to_be_visible()
        await expect(self.page.locator("#job-name-error")).to_have_count(0)


class TestKeyboardGwflowJourney(GWFlowDetailShellBase):
    def _versions(self):
        return (
            [
                {
                    "commit_sha": "1111222233334444555566667777888899990000",
                    "commit_timestamp": "2026-08-10 12:00:00 UTC",
                    "schema_version": "3",
                    "is_current": True,
                },
                {
                    "commit_sha": "aaaabbbbccccddddeeeeffff0000111122223333",
                    "commit_timestamp": "2026-08-09 12:00:00 UTC",
                    "schema_version": "3",
                    "is_current": False,
                },
            ],
            "live",
        )

    @async_e2e_test
    async def test_keyboard_gwflow_detail_journey(self):
        history = self.page.locator('a[data-gwflow-section][href*="/history/"]')
        await history.focus()
        await expect(history).to_be_focused()
        await history.press("Enter")

        region = self.page.locator("#gwflow-history-region")
        await expect(region).to_be_visible()

        version_reached = False
        for _ in range(80):
            await self.page.keyboard.press("Tab")
            version_reached = await self.page.evaluate("() => !!document.activeElement.closest('[data-version-link]')")
            if version_reached:
                break
        self.assertTrue(version_reached, "History loaded but version link was not keyboard-reachable")
        version = region.locator("a[data-version-link]:focus")
        await expect(version).to_be_focused()
        await version.press("Enter")
        await expect(region.locator("#gwflow-history-version")).to_be_visible()

        region = self.page.locator("#gwflow-history-region")
        await expect(region).to_be_visible()
        await expect(region.locator("#gwflow-history-version")).to_be_visible()

        compare = region.locator('input[name="compare"][value="prev"]')
        await expect(compare).to_be_attached()
        await expect(compare).to_be_enabled()

        await self.page.wait_for_load_state("networkidle", timeout=5000)

        # Re-anchor on a known focusable element inside the history region, then
        # reach the compare control with Tab so keyboard reachability is proven.
        anchor = region.locator(".gwflow-history__desktop-list a[data-version-link]").first
        await anchor.focus()
        await expect(anchor).to_be_focused()

        compare_reached = False
        for _ in range(80):
            await self.page.keyboard.press("Tab")
            compare_reached = await self.page.evaluate(
                """() => document.activeElement
                && document.activeElement.matches(
                    'input[name="compare"][value="prev"]'
                )"""
            )
            if compare_reached:
                break

        self.assertTrue(compare_reached, "Compare control was not keyboard-reachable")
        await expect(compare).to_be_focused()
        await compare.press("Space")
        await expect(compare).to_be_checked()
        self.assertNotEqual(
            await compare.evaluate("(element) => getComputedStyle(element).outlineStyle"),
            "none",
        )

        files = self.page.locator('a[data-gwflow-section][href*="/files/"]')
        await files.focus()
        await expect(files).to_be_focused()
        await files.press("Enter")
        await expect(self.page.locator("#detail-pane")).to_be_visible()

        download = self.page.locator('a[href*="/download/"]').first
        if await download.count():
            await download.focus()
            await expect(download).to_be_focused()
            await expect(download).to_have_attribute("target", "_blank")
            self.assertIn("/download/", await download.get_attribute("href"))
