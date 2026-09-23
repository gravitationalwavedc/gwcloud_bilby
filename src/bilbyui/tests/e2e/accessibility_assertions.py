"""Shared browser primitives for accessibility and responsive e2e gates."""

from __future__ import annotations

import json
from typing import Any


async def wait_for_ready(page, selector: str) -> None:
    """Wait until the scoped page content is attached and visible."""
    await page.locator(selector).wait_for(state="visible")


async def settle_page(page) -> None:
    """Wait for network quiescence and for active HTMX requests to finish."""
    await page.wait_for_load_state("networkidle")
    await page.wait_for_function(
        """() => (
            !document.documentElement.classList.contains('htmx-request')
            && !document.querySelector('.htmx-request')
        )"""
    )


async def page_overflow(page) -> dict[str, int | bool]:
    """Return document-width measurements and whether horizontal overflow exists."""
    return await page.evaluate(
        """() => {
            const root = document.documentElement;
            return {
                clientWidth: root.clientWidth,
                scrollWidth: root.scrollWidth,
                overflowing: root.scrollWidth > root.clientWidth,
            };
        }"""
    )


async def scroll_region(page, selector: str) -> dict[str, int | bool]:
    """Return width measurements for a deliberately scrollable region."""
    return await page.locator(selector).evaluate(
        """element => ({
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
            scrollable: element.scrollWidth > element.clientWidth,
        })"""
    )


def format_diagnostics(diagnostics: dict[str, Any]) -> str:
    """Format captured diagnostics deterministically for assertion messages."""
    return json.dumps(diagnostics, indent=2, sort_keys=True, default=str)


async def assert_no_serious_axe_violations(page, scope_selector: str = "body") -> None:
    """Assert that axe finds no serious or critical violations in a scope."""
    from .utils import run_axe

    violations = await run_axe(page, scope_selector)
    serious = [violation for violation in violations if violation.get("impact") in {"serious", "critical"}]
    assert not serious, f"serious axe violation detected: {serious}"


async def assert_no_horizontal_overflow(page) -> None:
    """Assert that document width does not exceed viewport width."""
    metrics = await page_overflow(page)
    assert not metrics["overflowing"], f"horizontal overflow detected: {metrics}"


def contrast_ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    """Return the WCAG contrast ratio for two sRGB colour triples."""

    def linearise(value: int) -> float:
        channel = value / 255
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    def luminance(rgb: tuple[int, int, int]) -> float:
        red, green, blue = (linearise(value) for value in rgb)
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    first = luminance(foreground)
    second = luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


async def assert_text_contrast(page, selector: str, minimum_ratio: float = 4.5) -> None:
    """Assert that selected text meets the requested contrast ratio."""
    colours = await page.locator(selector).evaluate(
        """element => {
            const rgb = value => value.match(/\\d+(?:\\.\\d+)?/g)
                .slice(0, 3).map(Number);
            const style = getComputedStyle(element);
            return {
                foreground: rgb(style.color),
                background: rgb(style.backgroundColor),
            };
        }"""
    )
    ratio = contrast_ratio(
        tuple(colours["foreground"]),
        tuple(colours["background"]),
    )
    assert ratio >= minimum_ratio, (
        f"low-contrast text pair detected for {selector}: {ratio:.2f} below {minimum_ratio:.2f}"
    )


async def assert_minimum_target_size(page, selector: str, minimum_size: int = 24) -> None:
    """Assert that an interactive target meets the minimum dimensions."""
    box = await page.locator(selector).bounding_box()
    assert box is not None, f"target has no bounding box: {selector}"
    assert box["width"] >= minimum_size and box["height"] >= minimum_size, (
        f"target below {minimum_size}px detected for {selector}: {box['width']:.1f}x{box['height']:.1f}px"
    )


async def assert_active_element(page, expected_id: str) -> None:
    """Assert that focus is restored to the expected element."""
    actual_id = await page.evaluate("() => document.activeElement ? document.activeElement.id : ''")
    assert actual_id == expected_id, (
        f"post-swap focus restoration failed: expected {expected_id!r}, found {actual_id!r}"
    )


async def assert_no_infinite_animation(page, selector: str) -> None:
    """Assert that reduced-motion rendering contains no infinite animation."""
    facts = await page.locator(selector).evaluate(
        """element => {
            const style = getComputedStyle(element);
            return {
                duration: style.animationDuration,
                iterations: style.animationIterationCount,
            };
        }"""
    )
    durations = [float(value.removesuffix("s") or 0) for value in facts["duration"].split(",")]
    iterations = [value.strip() for value in facts["iterations"].split(",")]
    active_infinite = any(
        iteration == "infinite" and durations[index % len(durations)] > 0 for index, iteration in enumerate(iterations)
    )
    assert not active_infinite, f"infinite animation under reduced motion detected for {selector}: {facts}"
