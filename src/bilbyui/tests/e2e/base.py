"""
Shared authenticated-page setup for the technical-value demo e2e tests.

Contains NO test methods (TESTING.md convention 2): concrete test classes
inherit :class:`TechValueDemoPageBase` and each add exactly one test.
"""

from __future__ import annotations

from asgiref.sync import sync_to_async
from django.urls import reverse

from bilbyui.tests.e2e.utils import AsyncE2ETestCase
from bilbyui.tests.testcases import BilbyTestCase

DEMO_URL_NAME = "bilbyui:tech_value_demo"


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
