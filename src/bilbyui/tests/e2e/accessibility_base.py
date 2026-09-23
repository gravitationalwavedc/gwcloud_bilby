"""Test-free shared base for accessibility and responsive browser gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bilbyui.tests.e2e.accessibility_assertions import (
    settle_page,
)
from bilbyui.tests.e2e.accessibility_assertions import (
    wait_for_ready as wait_for_page_ready,
)
from bilbyui.tests.e2e.utils import AsyncE2ETestCase


class AccessibilityE2EBase(AsyncE2ETestCase):
    """Small shared browser setup surface; deliberately contains no tests."""

    page = None

    async def open_authenticated(self, user, url: str):
        """Log in and open an authenticated page at ``url``."""
        await self.login(user)
        self.page = await self.browser_context.new_page()
        await self.page.goto(url)
        return self.page

    async def wait_for_ready(self, selector: str) -> None:
        """Wait for the page's relevant content scope to become visible."""
        await wait_for_page_ready(self.page, selector)

    async def settle(self) -> None:
        """Wait for network and HTMX activity to settle."""
        await settle_page(self.page)

    async def capture_diagnostics(
        self,
        name: str,
        content_scope: str,
        directory: str | Path,
    ) -> dict[str, Any]:
        """Capture a screenshot, scoped HTML, URL, and viewport details."""
        output_dir = Path(directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        screenshot = output_dir / f"{name}.png"
        html = output_dir / f"{name}.html"
        scope = self.page.locator(content_scope)
        await self.page.screenshot(path=str(screenshot), full_page=True)
        html.write_text(await scope.evaluate("element => element.outerHTML"), encoding="utf-8")
        return {
            "name": name,
            "url": self.page.url,
            "viewport": self.page.viewport_size,
            "content_scope": content_scope,
            "screenshot": str(screenshot),
            "html": str(html),
        }
