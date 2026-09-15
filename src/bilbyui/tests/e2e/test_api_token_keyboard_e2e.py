from asgiref.sync import sync_to_async
from django.urls import reverse

from bilbyui.services.api_tokens import create_token
from bilbyui.tests.testcases import BilbyTestCase

from .utils import AsyncE2ETestCase, async_e2e_test

RESOLVED_FAKE = """
Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: {
    writeText: () => Promise.resolve()
  }
});
"""

REJECTED_FAKE = """
Object.defineProperty(navigator, "clipboard", {
  configurable: true,
  value: {
    writeText: () => Promise.reject(new Error("Clipboard unavailable"))
  }
});
"""


class APITokenKeyboardBase(AsyncE2ETestCase):
    async def asetUp(self):
        self.user = await sync_to_async(BilbyTestCase.create_user)(
            name="e2e api token",
            primary_email="api-token-keyboard@example.com",
        )
        await sync_to_async(create_token)(self.user, "e2e-token")
        await self.login(self.user)
        self.url = self.live_server_url + reverse("bilbyui:api_tokens")


class APITokenRevokeKeyboardE2ETest(APITokenKeyboardBase):
    @async_e2e_test
    async def test_revoke_confirm_escape_and_submit_by_keyboard(self):
        page = await self.browser_context.new_page()
        await page.goto(self.url)

        row = page.locator("[data-token-id]").first
        revoke = row.locator(".token-revoke-start")
        cancel = row.locator(".token-revoke-cancel")

        await revoke.focus()
        await page.keyboard.press("Enter")
        await row.locator(".token-revoke").wait_for(state="attached")
        self.assertEqual(
            await row.locator(".token-revoke").get_attribute("data-confirming"),
            "true",
        )
        self.assertTrue(await cancel.evaluate("el => el === document.activeElement"))

        await page.keyboard.press("Escape")
        self.assertEqual(
            await row.locator(".token-revoke").get_attribute("data-confirming"),
            "false",
        )
        self.assertTrue(await revoke.evaluate("el => el === document.activeElement"))

        await page.keyboard.press("Enter")
        self.assertTrue(await cancel.evaluate("el => el === document.activeElement"))
        await page.keyboard.press("Shift+Tab")
        confirm = row.get_by_role("button", name="Yes, revoke")
        self.assertTrue(await confirm.evaluate("el => el === document.activeElement"))
        await page.keyboard.press("Enter")

        await row.wait_for(state="detached")
        status = page.locator("#token-revoke-status")
        await page.wait_for_function(
            """() => document.querySelector("#token-revoke-status").textContent
                .trim() === "Token revoked" """
        )
        self.assertEqual(await status.get_attribute("role"), "status")
        self.assertEqual((await status.text_content()).strip(), "Token revoked")


class APITokenCopySuccessKeyboardE2ETest(APITokenKeyboardBase):
    @async_e2e_test
    async def test_copy_success_is_announced_by_keyboard(self):
        page = await self.browser_context.new_page()
        await page.add_init_script(RESOLVED_FAKE)
        await page.goto(self.url)

        await page.get_by_role("button", name="Create Token").click()
        await page.locator("#token-name").fill("copy-token")
        await page.locator("#token-create-form button[type=submit]").click()
        await page.locator(".token-copy").wait_for(state="attached")

        copy = page.locator(".token-copy")
        status = page.locator(".token-copy-status")
        await copy.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_function(
            """() => document.querySelector(".token-copy-status").textContent
                .trim() === "Copied!" """
        )
        self.assertEqual((await status.text_content()).strip(), "Copied!")


class APITokenCopyFailureKeyboardE2ETest(APITokenKeyboardBase):
    @async_e2e_test
    async def test_copy_failure_is_announced_by_keyboard(self):
        page = await self.browser_context.new_page()
        await page.add_init_script(REJECTED_FAKE)
        await page.goto(self.url)

        await page.get_by_role("button", name="Create Token").click()
        await page.locator("#token-name").fill("copy-token")
        await page.locator("#token-create-form button[type=submit]").click()
        await page.locator(".token-copy").wait_for(state="attached")

        copy = page.locator(".token-copy")
        status = page.locator(".token-copy-status")
        await copy.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_function(
            """() => document.querySelector(".token-copy-status").textContent
                .trim() === "Copy failed" """
        )
        self.assertEqual((await status.text_content()).strip(), "Copy failed")
