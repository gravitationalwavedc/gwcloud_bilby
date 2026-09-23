"""Shared browser primitives and gate detectors for accessibility e2e tests.

Each accessibility gate has exactly one detector here. The route gates and the
seeded causal meta-tests call the same function per gate, so a defect that
fails a route gate also fails its seed (and vice versa).
"""

from __future__ import annotations

BLOCKING_AXE_IMPACTS = {"serious", "critical"}
MINIMUM_TARGET_SIZE = 24
TARGET_SELECTOR = (
    "a[href], button, input, select, textarea, summary, [role='button'], [role='link'], [tabindex]:not([tabindex='-1'])"
)


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


async def assert_no_serious_axe_violations(page, scope_selector: str = "body", *, context: str = "") -> None:
    """Assert that axe finds no serious or critical violations in a scope."""
    from .utils import run_axe

    violations = await run_axe(page, scope_selector)
    blocking = [violation for violation in violations if violation.get("impact") in BLOCKING_AXE_IMPACTS]
    if not blocking:
        return
    lines = []
    for violation in blocking:
        for node in violation.get("nodes", []):
            target = " > ".join(str(part) for part in node.get("target", []))
            html = " ".join(node.get("html", "").split())[:240]
            lines.append(
                f"rule={violation.get('id')} impact={violation.get('impact')} selector={target!r} html={html!r}"
            )
    prefix = f"{context}: " if context else ""
    raise AssertionError(f"{prefix}serious axe violation detected:\n" + "\n".join(lines))


async def assert_no_horizontal_overflow(page, *, context: str = "") -> None:
    """Assert that the document does not overflow the viewport horizontally."""
    metrics = await page.evaluate(
        """() => {
            const root = document.scrollingElement || document.documentElement;
            return {
                scrollWidth: root.scrollWidth,
                innerWidth: window.innerWidth,
                overflowing: root.scrollWidth > window.innerWidth,
            };
        }"""
    )
    prefix = f"{context}: " if context else ""
    assert not metrics["overflowing"], f"{prefix}horizontal overflow detected: {metrics}"


async def assert_table_scroll_regions(page, *, context: str = "") -> None:
    """Assert overflowing table regions are labelled, focusable and scroll internally."""
    regions = page.locator(".table-scroll-region")
    prefix = f"{context}: " if context else ""
    for index in range(await regions.count()):
        region = regions.nth(index)
        facts = await region.evaluate(
            """element => {
                const style = getComputedStyle(element);
                const label = (
                    element.getAttribute('aria-label')
                    || element.getAttribute('aria-labelledby')
                    || ''
                );
                return {
                    label,
                    overflowX: style.overflowX,
                    tabIndex: element.getAttribute('tabindex'),
                    clientWidth: element.clientWidth,
                    scrollWidth: element.scrollWidth,
                };
            }"""
        )
        if facts["scrollWidth"] <= facts["clientWidth"]:
            continue
        assert facts["label"], f"{prefix}region {index} has no accessible label"
        assert facts["overflowX"] in ("auto", "scroll"), f"{prefix}region {index} does not scroll internally: {facts}"
        assert facts["tabIndex"] == "0", f"{prefix}overflowing region {index} is not keyboard focusable"


CONTRAST_SWEEP_JS = r"""
(scopeSelector) => {
    const root = document.querySelector(scopeSelector);
    if (!root) throw new Error(`Missing contrast scope: ${scopeSelector}`);
    const visible = el => {
        const s = getComputedStyle(el), r = el.getBoundingClientRect();
        return s.display !== "none" && s.visibility !== "hidden"
            && Number(s.opacity) > 0 && r.width > 0 && r.height > 0;
    };
    const rgba = value => {
        const m = value.trim().match(/^rgba?\((.*)\)$/i);
        if (!m) return null;
        let bits, alpha = "1";
        if (m[1].includes(",")) {
            bits = m[1].split(",").map(v => v.trim());
            alpha = bits[3] || alpha;
        } else {
            const halves = m[1].split("/").map(v => v.trim());
            bits = halves[0].split(/\s+/);
            alpha = halves[1] || alpha;
        }
        const channel = v => v.endsWith("%") ? 2.55 * parseFloat(v) : parseFloat(v);
        const a = v => v.endsWith("%") ? parseFloat(v) / 100 : parseFloat(v);
        return [channel(bits[0]), channel(bits[1]), channel(bits[2]), a(alpha)];
    };
    const over = (fg, bg) => {
        const a = fg[3] + bg[3] * (1 - fg[3]);
        if (!a) return [0, 0, 0, 0];
        return [0, 1, 2].map(i =>
            (fg[i] * fg[3] + bg[i] * bg[3] * (1 - fg[3])) / a
        ).concat(a);
    };
    const backdrop = el => {
        const layers = []; let node = el;
        let disposition = null;
        while (node) {
            const s = getComputedStyle(node);
            if (s.backgroundImage && s.backgroundImage !== "none") {
                disposition = s.backgroundImage.includes("gradient")
                    ? "gradient-background: manual review"
                    : "image-background: manual review";
                break;
            }
            const layer = rgba(s.backgroundColor);
            if (layer && layer[3]) {
                layers.push(layer);
                if (layer[3] === 1) break;
            }
            node = node.parentElement;
        }
        let result = [255, 255, 255, 1];
        for (let i = layers.length - 1; i >= 0; i--) result = over(layers[i], result);
        return {colour: result, disposition};
    };
    const linear = n => {
        const s = n / 255;
        return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    const luminance = c => .2126 * linear(c[0]) + .7152 * linear(c[1]) + .0722 * linear(c[2]);
    const ratio = (a, b) => {
        const x = luminance(a), y = luminance(b);
        return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
    };
    const selector = el => {
        if (el.id) return `#${CSS.escape(el.id)}`;
        const cls = [...el.classList].slice(0, 2).map(CSS.escape).join(".");
        return `${el.tagName.toLowerCase()}${cls ? "." + cls : ""}`;
    };
    const records = [], dispositions = [];
    const add = (el, kind, rawForeground, threshold, detail) => {
        const bg = backdrop(el);
        if (bg.disposition) {
            dispositions.push({selector: selector(el), kind, disposition: bg.disposition});
            return;
        }
        let fg = rgba(rawForeground);
        if (!fg || fg[3] === 0) return;
        if (fg[3] < 1) fg = over(fg, bg.colour);
        records.push({
            selector: selector(el), kind, foreground: fg, background: bg.colour,
            ratio: ratio(fg, bg.colour), threshold, detail,
        });
    };
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let text;
    while ((text = walker.nextNode())) {
        if (!text.nodeValue.trim()) continue;
        const el = text.parentElement;
        if (!el || !visible(el)) continue;
        const s = getComputedStyle(el), px = parseFloat(s.fontSize);
        const weight = Number(s.fontWeight) || (s.fontWeight === "bold" ? 700 : 400);
        const large = px >= 24 || (px >= 18.66 && weight >= 700);
        add(el, "text", s.color, large ? 3 : 4.5, large ? "large text" : "normal text");
    }
    const uiSelector = [
        "button", "input", "select", "textarea", "[role=button]",
        "[aria-current]", "svg", ".badge", ".alert"
    ].join(",");
    for (const el of root.querySelectorAll(uiSelector)) {
        if (!visible(el) || el.disabled) continue;
        const s = getComputedStyle(el);
        if (el.matches("svg, svg *")) {
            if (s.fill !== "none") add(el, "icon-fill", s.fill, 3, "meaningful SVG fill");
            if (s.stroke !== "none") add(el, "icon-stroke", s.stroke, 3, "meaningful SVG stroke");
        } else {
            const widths = [s.borderTopWidth, s.borderRightWidth, s.borderBottomWidth, s.borderLeftWidth];
            if (widths.some(width => parseFloat(width) > 0)) {
                add(el, "control-boundary", s.borderColor, 3, "control boundary");
            }
        }
    }
    for (const el of root.querySelectorAll("*")) {
        if (!visible(el)) continue;
        for (const pseudo of ["::before", "::after"]) {
            const s = getComputedStyle(el, pseudo);
            if (s.content !== "none" && s.content !== "normal" && s.content !== '""') {
                add(el, "pseudo-element", s.color, 3, `meaningful ${pseudo}`);
            }
        }
    }
    const byPair = new Map();
    for (const item of records) {
        const rounded = colour => colour.map(value => Math.round(value * 10) / 10).join(",");
        const key = `${item.kind}|${rounded(item.foreground)}|${rounded(item.background)}|${item.threshold}`;
        if (!byPair.has(key)) byPair.set(key, item);
    }
    return {records: [...byPair.values()], dispositions};
}
"""


def format_contrast_failures(failures) -> str:
    """Return actionable contrast diagnostics."""
    return "\n".join(
        f"- {item['selector']} ({item['kind']}, {item['detail']}): "
        f"{item['ratio']:.3f}:1 < {item['threshold']}:1; "
        f"fg={item['foreground']}, bg={item['background']}"
        for item in failures
    )


async def assert_no_contrast_failures(page, scope_selector: str, *, context: str = "") -> dict:
    """Run the computed contrast sweep and assert no pair falls below threshold."""
    result = await page.evaluate(CONTRAST_SWEEP_JS, scope_selector)
    records = result["records"]
    failures = [item for item in records if item["ratio"] + 0.001 < item["threshold"]]
    prefix = f"{context}: " if context else ""
    assert records, f"{prefix}expected rendered text or UI colour pairs"
    assert not failures, f"{prefix}computed contrast failures:\n" + format_contrast_failures(failures)
    return result


async def assert_target_sizes(
    page,
    *,
    scope_selector: str = "main",
    selector: str = TARGET_SELECTOR,
    minimum_size: int = MINIMUM_TARGET_SIZE,
    max_inline_link_exceptions: int | None = None,
    context: str = "",
) -> None:
    """Assert visible enabled targets meet the minimum size, except inline text links."""
    targets = page.locator(scope_selector).locator(selector)
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
        if box["width"] >= minimum_size and box["height"] >= minimum_size:
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
    prefix = f"{context}: " if context else ""
    if max_inline_link_exceptions is not None:
        assert len(exceptions) <= max_inline_link_exceptions, (
            f"{prefix}more than {max_inline_link_exceptions} inline-link exceptions: {exceptions}"
        )
    assert not failures, f"{prefix}undersized interactive targets: " + "; ".join(failures)


INFINITE_ANIMATION_JS = r"""
scope => {
    const elements = [scope, ...scope.querySelectorAll('*')];
    return elements.flatMap(element => {
        const style = getComputedStyle(element);
        const durations = style.animationDuration.split(',').map(value => {
            if (value.trim().endsWith('ms')) return parseFloat(value);
            if (value.trim().endsWith('s')) return parseFloat(value) * 1000;
            return 0;
        });
        const iterations = style.animationIterationCount.split(',');
        const infinite = durations.some(
            (duration, index) =>
                duration > 0
                && (iterations[index] || iterations[0] || '').trim() === 'infinite'
        );
        if (!infinite) return [];
        return [{
            tag: element.tagName.toLowerCase(),
            id: element.id,
            classes: String(element.className),
            animationDuration: style.animationDuration,
            animationIterationCount: style.animationIterationCount,
        }];
    });
}
"""


async def assert_no_infinite_animation(page, scope_selector: str = "body", *, context: str = "") -> None:
    """Assert the reduced-motion tree contains no active infinite animation."""
    motion = await page.locator(scope_selector).evaluate(INFINITE_ANIMATION_JS)
    prefix = f"{context}: " if context else ""
    assert not motion, f"{prefix}infinite animations remain in reduced-motion mode: {motion}"


async def assert_active_element(page, expected_id: str) -> None:
    """Assert that focus is restored to the expected element."""
    actual_id = await page.evaluate("() => document.activeElement ? document.activeElement.id : ''")
    assert actual_id == expected_id, (
        f"post-swap focus restoration failed: expected {expected_id!r}, found {actual_id!r}"
    )
