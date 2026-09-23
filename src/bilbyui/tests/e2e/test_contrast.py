"""Computed contrast sweep for rendered GWFlow content."""

from __future__ import annotations

import json

from bilbyui.tests.e2e.base import (
    GWFlowDetailShellBase,
    GWFlowFilesPageBase,
    GWFlowJobsPageBase,
    TechValueDemoPageBase,
)
from bilbyui.tests.e2e.utils import async_e2e_test

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


def _format_failures(failures):
    """Return actionable contrast diagnostics."""
    return "\n".join(
        f"- {item['selector']} ({item['kind']}, {item['detail']}): "
        f"{item['ratio']:.3f}:1 < {item['threshold']}:1; "
        f"fg={item['foreground']}, bg={item['background']}"
        for item in failures
    )


def _aaa_advisory(records):
    """Build a non-blocking report for enhanced AAA text contrast."""
    text = [item for item in records if item["kind"] == "text"]
    misses = [item for item in text if item["ratio"] < (4.5 if item["threshold"] == 3 else 7)]
    return {"checked_pairs": len(text), "advisory_failures": misses}


class TestContentContrast(GWFlowJobsPageBase):
    """Sweep one deterministic reachable content state."""

    @async_e2e_test
    async def test_computed_content_contrast(self):
        await self.page.wait_for_selector("#gwflow-job-list")
        result = await self.page.evaluate(CONTRAST_SWEEP_JS, "#gwflow-job-list")
        records = result["records"]
        failures = [item for item in records if item["ratio"] + 0.001 < item["threshold"]]
        advisory = _aaa_advisory(records)
        print("CONTRAST_AAA_ADVISORY=" + json.dumps(advisory, sort_keys=True))
        print(
            "CONTRAST_SWEEP="
            + json.dumps(
                {
                    "pairs": len(records),
                    "failures": len(failures),
                    "dispositions": result["dispositions"],
                },
                sort_keys=True,
            )
        )
        self.assertGreater(len(records), 0, "Expected rendered text or UI colour pairs")
        self.assertEqual([], failures, "Computed contrast failures:\n" + _format_failures(failures))


async def _assert_contrast(case, scope):
    await case.page.wait_for_selector(scope)
    result = await case.page.evaluate(CONTRAST_SWEEP_JS, scope)
    records = result["records"]
    failures = [item for item in records if item["ratio"] + 0.001 < item["threshold"]]
    case.assertGreater(len(records), 0, "Expected rendered text or UI colour pairs")
    case.assertEqual([], failures, "Computed contrast failures:\n" + _format_failures(failures))


class TestDetailContentContrast(GWFlowDetailShellBase):
    @async_e2e_test
    async def test_metadata_computed_content_contrast(self):
        await _assert_contrast(self, ".detail-shell")


class TestFilesContentContrast(GWFlowFilesPageBase):
    @async_e2e_test
    async def test_files_computed_content_contrast(self):
        await _assert_contrast(self, "#detail-pane")


class TestDemoContentContrast(TechValueDemoPageBase):
    @async_e2e_test
    async def test_demo_computed_content_contrast(self):
        await _assert_contrast(self, ".app-container")
