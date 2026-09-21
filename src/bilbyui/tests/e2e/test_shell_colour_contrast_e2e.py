"""Rendered shell colour-contrast checks and true full-document axe gates."""

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from bilbyui.tests.e2e.base import GWFlowJobsPageBase, TechValueDemoPageBase
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe_document

VIEWPORT_WIDTHS = (375, 1024)
NAV_LINK = ".app-navbar .navbar-nav .nav-link"
NAV_USER = ".app-navbar .app-navbar-user"
ACTIVE_NAV_LINK = '.app-navbar .navbar-nav .nav-link.active[aria-current="page"]'

CONTRAST_EVALUATE_JS = r"""
(selector) => {
    const el = document.querySelector(selector);
    if (!el) {
        return null;
    }

    const parseChannel = (value) => {
        const token = value.trim();
        return token.endsWith("%")
            ? 255 * Number.parseFloat(token) / 100
            : Number.parseFloat(token);
    };

    const parseAlpha = (value) => {
        if (value === undefined) {
            return 1;
        }
        const token = value.trim();
        return token.endsWith("%")
            ? Number.parseFloat(token) / 100
            : Number.parseFloat(token);
    };

    const parseColour = (value) => {
        const match = value.trim().match(/^rgba?\((.*)\)$/i);
        if (!match) {
            throw new Error(`Unsupported computed colour: ${value}`);
        }

        const body = match[1].trim();
        let channels;
        let alpha;
        if (body.includes(",")) {
            const parts = body.split(",").map((part) => part.trim());
            channels = parts.slice(0, 3);
            alpha = parts[3];
        } else {
            const slashParts = body.split("/").map((part) => part.trim());
            channels = slashParts[0].split(/\s+/);
            alpha = slashParts[1];
        }
        if (channels.length !== 3) {
            throw new Error(`Unexpected computed colour: ${value}`);
        }
        return [
            parseChannel(channels[0]),
            parseChannel(channels[1]),
            parseChannel(channels[2]),
            parseAlpha(alpha),
        ];
    };

    const composite = (foreground, background) => {
        const alpha = foreground[3] + background[3] * (1 - foreground[3]);
        if (alpha === 0) {
            return [0, 0, 0, 0];
        }
        return [
            (foreground[0] * foreground[3]
                + background[0] * background[3] * (1 - foreground[3])) / alpha,
            (foreground[1] * foreground[3]
                + background[1] * background[3] * (1 - foreground[3])) / alpha,
            (foreground[2] * foreground[3]
                + background[2] * background[3] * (1 - foreground[3])) / alpha,
            alpha,
        ];
    };

    const layers = [];
    let ancestor = el;
    while (ancestor) {
        const layer = parseColour(getComputedStyle(ancestor).backgroundColor);
        if (layer[3] > 0) {
            layers.push(layer);
            if (layer[3] >= 1) {
                break;
            }
        }
        ancestor = ancestor.parentElement;
    }

    let background = [255, 255, 255, 1];
    for (let index = layers.length - 1; index >= 0; index -= 1) {
        background = composite(layers[index], background);
    }

    let foreground = parseColour(getComputedStyle(el).color);
    if (foreground[3] < 1) {
        foreground = composite(foreground, background);
    }

    const linearise = (channel) => {
        const srgb = channel / 255;
        return srgb <= 0.04045
            ? srgb / 12.92
            : ((srgb + 0.055) / 1.055) ** 2.4;
    };
    const luminance = (colour) =>
        0.2126 * linearise(colour[0])
        + 0.7152 * linearise(colour[1])
        + 0.0722 * linearise(colour[2]);

    const foregroundLuminance = luminance(foreground);
    const backgroundLuminance = luminance(background);
    const lighter = Math.max(foregroundLuminance, backgroundLuminance);
    const darker = Math.min(foregroundLuminance, backgroundLuminance);

    return {
        fg: foreground,
        bg: background,
        ratio: (lighter + 0.05) / (darker + 0.05),
    };
}
"""


async def _contrast(page, selector):
    """Return rendered foreground/background contrast data for ``selector``."""
    return await page.evaluate(CONTRAST_EVALUATE_JS, selector)


def _assert_contrast(testcase, result, selector, viewport):
    testcase.assertIsNotNone(
        result,
        f"Expected rendered element '{selector}' at {viewport}px",
    )
    testcase.assertGreaterEqual(
        result["ratio"],
        4.5,
        f"{selector} contrast at {viewport}px was {result['ratio']:.3f}:1 "
        f"(fg={result['fg']}, bg={result['bg']})",
    )


def _blocking_axe_detail(violations):
    blocking = [
        violation
        for violation in violations
        if violation.get("impact") in ("serious", "critical")
    ]
    detail = "\n".join(
        f"- {violation['id']} ({violation.get('impact')}): "
        + "; ".join(
            " > ".join(str(part) for part in node["target"])
            for node in violation["nodes"]
        )
        for violation in blocking
    )
    return blocking, detail


class TestNavLinkContrastDemoPage(TechValueDemoPageBase):
    @async_e2e_test
    async def test_nav_link_states_and_user_contrast_at_responsive_viewports(self):
        for width in VIEWPORT_WIDTHS:
            await self.page.set_viewport_size({"width": width, "height": 900})
            await self.page.goto(self.demo_url())

            if not await self.page.is_visible(NAV_LINK):
                await self.page.click(".navbar-toggler")
                await self.page.wait_for_selector(NAV_LINK, state="visible")

            default = await _contrast(self.page, NAV_LINK)
            _assert_contrast(self, default, NAV_LINK, width)

            await self.page.hover(NAV_LINK)
            hover = await _contrast(self.page, NAV_LINK)
            _assert_contrast(self, hover, f"{NAV_LINK} (hover)", width)

            await self.page.focus(NAV_LINK)
            focus = await _contrast(self.page, NAV_LINK)
            _assert_contrast(self, focus, f"{NAV_LINK} (focus)", width)

            user = await _contrast(self.page, NAV_USER)
            _assert_contrast(self, user, NAV_USER, width)

        # Disabled navigation is an inactive component and is exempt from
        # WCAG SC 1.4.3 and SC 1.4.11; no disabled fixture is fabricated.


class TestInlineCodeContrastDemoPage(TechValueDemoPageBase):
    @async_e2e_test
    async def test_inline_code_contrast_at_responsive_viewports(self):
        selector = ".app-container code"
        for width in VIEWPORT_WIDTHS:
            await self.page.set_viewport_size({"width": width, "height": 900})
            await self.page.goto(self.demo_url())
            result = await _contrast(self.page, selector)
            _assert_contrast(self, result, selector, width)


class TestNavLinkActiveContrastGWFlowPage(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_active_nav_link_and_user_contrast_at_responsive_viewports(self):
        for width in VIEWPORT_WIDTHS:
            await self.page.set_viewport_size({"width": width, "height": 900})
            await self.page.goto(self.gwflow_url())

            if not await self.page.is_visible(ACTIVE_NAV_LINK):
                await self.page.click(".navbar-toggler")
                await self.page.wait_for_selector(ACTIVE_NAV_LINK, state="visible")

            active = await _contrast(self.page, ACTIVE_NAV_LINK)
            _assert_contrast(self, active, ACTIVE_NAV_LINK, width)

            user = await _contrast(self.page, NAV_USER)
            _assert_contrast(self, user, NAV_USER, width)


class TestLinkContrastGWFlowPage(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_filter_reset_and_pagination_link_contrast(self):
        selectors = (
            ".filter-reset",
            ".page-link",
            '.page-item.active .page-link[aria-current="page"]',
        )
        for width in VIEWPORT_WIDTHS:
            await self.page.set_viewport_size({"width": width, "height": 900})
            await self.page.goto(f"{self.gwflow_url()}?library=lib1")
            for selector in selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=5000)
                except PlaywrightTimeoutError:
                    region_html = await self.page.locator("main").inner_html()
                    self.fail(
                        f"Expected '{selector}' after applying library=lib1 at "
                        f"{width}px. Main-region HTML:\n{region_html}"
                    )
                result = await _contrast(self.page, selector)
                _assert_contrast(self, result, selector, width)


class TestFullPageAxeScanDemoPage(TechValueDemoPageBase):
    @async_e2e_test
    async def test_zero_serious_or_critical_full_document_violations(self):
        for width in VIEWPORT_WIDTHS:
            await self.page.set_viewport_size({"width": width, "height": 900})
            await self.page.goto(self.demo_url())
            await load_axe(self.page)
            violations = await run_axe_document(self.page)
            blocking, detail = _blocking_axe_detail(violations)
            self.assertEqual(
                [],
                blocking,
                f"Expected zero serious/critical full-document axe violations "
                f"on demo page at {width}px, found {len(blocking)}:\n{detail}",
            )


class TestFullPageAxeScanGWFlowPage(GWFlowJobsPageBase):
    @async_e2e_test
    async def test_zero_serious_or_critical_full_document_violations(self):
        for width in VIEWPORT_WIDTHS:
            await self.page.set_viewport_size({"width": width, "height": 900})
            await self.page.goto(f"{self.gwflow_url()}?library=lib1")
            await load_axe(self.page)
            violations = await run_axe_document(self.page)
            blocking, detail = _blocking_axe_detail(violations)
            self.assertEqual(
                [],
                blocking,
                f"Expected zero serious/critical full-document axe violations "
                f"on GWFlow jobs page at {width}px, found {len(blocking)}:\n{detail}",
            )
