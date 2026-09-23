"""WCAG 2.2 target-size gate for the GWFlow jobs page."""

from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test

TARGET_SELECTOR = (
    "a[href], button, input, select, textarea, summary, [role='button'], [role='link'], [tabindex]:not([tabindex='-1'])"
)
MINIMUM_TARGET_SIZE = 24
MAXIMUM_EXCEPTIONS = 3


class TestTargetSize(GWFlowJobsPageBase):
    """Verify visible, enabled targets in main meet the WCAG minimum."""

    @async_e2e_test
    async def test_visible_interactive_targets_are_at_least_24_css_pixels(self):
        targets = self.page.locator("main").locator(TARGET_SELECTOR)
        failures = []
        exceptions = []

        for index in range(await targets.count()):
            target = targets.nth(index)
            if not await target.is_visible() or not await target.is_enabled():
                continue

            box = await target.bounding_box()
            if box is None:
                continue

            details = await target.evaluate(
                """element => ({
                    selector: element.id
                        ? `#${CSS.escape(element.id)}`
                        : element.tagName.toLowerCase(),
                    text: (element.innerText || element.value || element.title || '')
                        .trim().replace(/\\s+/g, ' ').slice(0, 80),
                    inlineLink: element.matches('a[href]')
                        && getComputedStyle(element).display === 'inline',
                })"""
            )
            attribution = f"{details['selector']} {details['text']!r}: {box['width']:.2f}x{box['height']:.2f}px"

            with self.subTest(target=attribution):
                if box["width"] >= MINIMUM_TARGET_SIZE and box["height"] >= MINIMUM_TARGET_SIZE:
                    continue
                if details["inlineLink"]:
                    exceptions.append(
                        {
                            "selector": details["selector"],
                            "reason": "inline text link exception under WCAG 2.5.8",
                            "target": attribution,
                        }
                    )
                    continue
                failures.append(attribution)

        self.assertLessEqual(
            len(exceptions),
            MAXIMUM_EXCEPTIONS,
            f"more than {MAXIMUM_EXCEPTIONS} inline-link exceptions: {exceptions}",
        )
        self.assertFalse(failures, "undersized interactive targets: " + "; ".join(failures))


async def _assert_target_sizes(case):
    targets = case.page.locator("main").locator(TARGET_SELECTOR)
    failures = []
    for index in range(await targets.count()):
        target = targets.nth(index)
        if not await target.is_visible() or not await target.is_enabled():
            continue
        box = await target.bounding_box()
        if box is None:
            continue
        inline = await target.evaluate(
            "element => element.matches('a[href]') && getComputedStyle(element).display === 'inline'"
        )
        if box["width"] < MINIMUM_TARGET_SIZE or box["height"] < MINIMUM_TARGET_SIZE:
            if not inline:
                failures.append(f"{await target.evaluate('e => e.id || e.tagName')}: {box}")
    case.assertFalse(failures, "undersized interactive targets: " + "; ".join(failures))


class TestDetailTargetSize(GWFlowDetailShellBase):
    @async_e2e_test
    async def test_metadata_targets_are_at_least_24_css_pixels(self):
        await _assert_target_sizes(self)


class TestFilesTargetSize(GWFlowFilesPageBase):
    @async_e2e_test
    async def test_files_targets_are_at_least_24_css_pixels(self):
        await _assert_target_sizes(self)


class TestDemoTargetSize(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_targets_are_at_least_24_css_pixels(self):
        await _assert_target_sizes(self)
