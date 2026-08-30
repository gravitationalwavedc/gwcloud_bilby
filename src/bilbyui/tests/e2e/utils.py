"""
Async Playwright test utilities for e2e tests.

Provides:

- :class:`AsyncE2ETestCase` — ``StaticLiveServerTestCase`` base with a
  cookie-based login helper that caches authentication per class.
- :func:`async_e2e_test` — decorator for async test methods. It lazily
  bootstraps the shared browser server (see :func:`ensure_pw_endpoint`),
  connects Chromium, creates a fresh browser context per test, and runs
  optional ``asetUp`` / ``aTearDown`` hooks.
- :func:`load_axe` / :func:`run_axe` — CSP-safe axe-core accessibility scans.
"""

from __future__ import annotations

import atexit
import functools
import os

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.async_api import BrowserContext, async_playwright

from bilbyui.tests.e2e.pw_server import get_playwright_dir, start_pw_server, stop_pw_server

PW_WS_ENDPOINT_ENV_VAR = "PW_WS_ENDPOINT"

_endpoint: str | None = None
_server_proc = None


def ensure_pw_endpoint() -> str:
    """
    Return the WebSocket endpoint of a shared Playwright Chromium server.

    Uses ``PW_WS_ENDPOINT`` from the environment when set (e.g. exported by CI
    or a custom runner to share one server across parallel workers). Otherwise
    starts one server per process on first use and stops it via ``atexit``.
    Plain unit-test runs never call this, so they never need Node.js.
    """
    global _endpoint, _server_proc
    if _endpoint:
        return _endpoint

    env_endpoint = os.environ.get(PW_WS_ENDPOINT_ENV_VAR)
    if env_endpoint:
        _endpoint = env_endpoint
        return _endpoint

    _server_proc = start_pw_server()
    atexit.register(stop_pw_server, _server_proc)
    _endpoint = _server_proc.ws_endpoint
    return _endpoint


BLOCKED_EXTERNAL_DOMAINS = (
    # Trackers/analytics that pages might reference must never be fetched.
    "googletagmanager.com",
    "google-analytics.com",
    # External font CDNs are blocked so tests exercise only locally served assets.
    "fonts.googleapis.com",
    "fonts.gstatic.com",
)


class AsyncE2ETestCase(StaticLiveServerTestCase):
    """
    Base class for Playwright e2e tests against the Django live server.

    Conventions (see TESTING.md): put shared setup in a test-free subclass of
    this class, and write exactly ONE test method per concrete test class.

    Authentication is performed by injecting session cookies into the browser
    context (:meth:`login`) and cached as a Playwright storage state per test
    class, so each test starts on an authenticated page without a login UI.
    """

    _storage_state: str | None = None
    _authenticated_user_id = None

    playwright = None
    browser = None
    browser_context: BrowserContext | None = None

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._storage_state = None
        cls._authenticated_user_id = None

    async def login(self, user) -> None:
        """Log ``user`` in by copying Django client cookies into the context."""
        cls = self.__class__
        if cls._storage_state and cls._authenticated_user_id == user.id:
            return

        await self.client.aforce_login(user)
        origin = self.live_server_url.rstrip("/")
        cookies = [
            {
                "name": name,
                "value": cookie.value,
                "url": origin,
                "secure": settings.SESSION_COOKIE_SECURE or False,
                "httpOnly": settings.SESSION_COOKIE_HTTPONLY or False,
                "sameSite": settings.SESSION_COOKIE_SAMESITE or "Lax",
            }
            for name, cookie in self.client.cookies.items()
        ]

        await self.browser_context.clear_cookies()
        await self.browser_context.add_cookies(cookies)

        cls._storage_state = await self.browser_context.storage_state()
        cls._authenticated_user_id = user.id

    async def _block_external_requests(self, route):
        """Abort requests to external tracker/font domains; allow everything else."""
        url = route.request.url
        for domain in BLOCKED_EXTERNAL_DOMAINS:
            if domain in url:
                await route.abort()
                return
        await route.continue_()


def async_e2e_test(coroutine):
    """
    Decorator for async e2e test methods.

    Connects to the shared Chromium server, creates a fresh browser context
    (reusing the class storage state once :meth:`AsyncE2ETestCase.login` has
    run), installs external-request blocking, then awaits ``asetUp``, the
    test coroutine and ``aTearDown``, closing all resources afterwards.
    """

    @functools.wraps(coroutine)
    async def wrapper(*args, **kwargs):
        self = args[0]
        cls = self.__class__

        ws_endpoint = ensure_pw_endpoint()

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect(ws_endpoint)
        try:
            if cls._storage_state:
                self.browser_context = await self.browser.new_context(storage_state=cls._storage_state)
            else:
                self.browser_context = await self.browser.new_context()
            await self.browser_context.route("**/*", self._block_external_requests)

            if hasattr(self, "asetUp"):
                await self.asetUp()

            return await coroutine(*args, **kwargs)
        finally:
            try:
                if hasattr(self, "aTearDown"):
                    await self.aTearDown()
            finally:
                if self.browser_context is not None:
                    await self.browser_context.close()
                    self.browser_context = None
                if self.browser is not None:
                    await self.browser.close()
                    self.browser = None
                if self.playwright is not None:
                    await self.playwright.stop()
                    self.playwright = None

    return wrapper


def _axe_source() -> str:
    axe_path = get_playwright_dir() / "node_modules" / "axe-core" / "axe.min.js"
    try:
        return axe_path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(
            f"axe-core source not found at {axe_path}. Run any e2e test once "
            "(the first run installs axe-core), or install it manually with npm."
        ) from e


async def load_axe(page) -> None:
    """Inject axe-core into the page via evaluate, which works under strict CSP."""
    await page.evaluate(_axe_source())


async def run_axe(page, scope_selector: str):
    """Run axe scoped to ``scope_selector`` and return its violations array.

    The helper encodes this suite's axe policy (see TESTING.md): scans always
    state their page region, because app-shell/theme contrast debt is tracked
    outside component suites. Note ``axe.run(document, { include })`` silently
    ignores ``include`` — the selector must be passed as the context argument.
    """
    return await page.evaluate(
        """(selector) => axe.run(
                { include: [[selector]] },
                { resultTypes: ['violations'] },
            ).then((r) => r.violations)""",
        scope_selector,
    )
