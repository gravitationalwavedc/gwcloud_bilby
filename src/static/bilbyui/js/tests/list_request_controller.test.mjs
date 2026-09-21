/**
 * Isolated tests for list_request_controller.js.
 *
 * Run:
 * node src/static/bilbyui/js/tests/list_request_controller.test.mjs
 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const testFile = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(testFile), "../../../../..");
const { chromium } = require(
  path.join(repoRoot, ".playwright/node_modules/playwright")
);
const controllerPath = path.resolve(
  path.dirname(testFile),
  "../list_request_controller.js"
);

const fixture = `<!doctype html>
<html>
<body>
  <button id="other-trigger" hx-target="#other-target">Other</button>
  <div id="other-target"></div>

  <div id="outside-decoy">
    <span class="list-loading-indicator__text">Wrong indicator</span>
  </div>

  <div
    id="test-region"
    data-list-region
    data-list-target="job-list"
    data-list-indicator="test-indicator"
    data-list-status="test-status"
    aria-busy="false"
  >
    <span
      id="test-indicator"
      class="list-loading-indicator"
      hidden
      aria-hidden="true"
    ><span class="list-loading-indicator__text">Updating results…</span></span>
    <p
      id="test-status"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    ></p>
    <button id="search-trigger" hx-target="#job-list">Search</button>
    <a
      id="pagination-trigger"
      href="?page=2"
      hx-target="#job-list"
      data-pagination-focus="true"
      data-page="2"
    >Page 2</a>
    <div id="job-list"></div>
  </div>
</body>
</html>`;

let passed = 0;
let failed = 0;

async function run(name, callback) {
  try {
    await callback();
    passed += 1;
    console.log(`PASS ${name}`);
  } catch (error) {
    failed += 1;
    console.error(`FAIL ${name}`);
    console.error(error && error.stack ? error.stack : error);
  }
}

async function newFixture(browser) {
  const page = await browser.newPage();
  await page.clock.install();
  await page.setContent(fixture);
  await page.addScriptTag({ path: controllerPath });
  return page;
}

async function snapshot(page) {
  return page.evaluate(() => {
    const region = document.getElementById("test-region");
    const indicator = document.getElementById("test-indicator");
    const status = document.getElementById("test-status");
    return {
      busy: region.getAttribute("aria-busy"),
      hidden: indicator.hidden,
      ariaHidden: indicator.getAttribute("aria-hidden"),
      indicatorText: indicator.querySelector(
        ".list-loading-indicator__text"
      ).textContent,
      status: status.textContent,
      statusCount: region.querySelectorAll("[role='status']").length
    };
  });
}

async function dispatch(page, name, requestName, options = {}) {
  await page.evaluate(
    ({ eventName, identityName, settings }) => {
      window.__requests = window.__requests || {};
      window.__requests[identityName] =
        window.__requests[identityName] || {};
      const elt = document.getElementById(
        settings.triggerId || "search-trigger"
      );
      const target = document.getElementById(
        settings.targetId || "job-list"
      );
      if (settings.settled) {
        target.innerHTML =
          '<div data-settled-kind="' +
          settings.settled.kind +
          '"' +
          (settings.settled.message === undefined
            ? ""
            : ' data-settled-message="' +
              settings.settled.message +
              '"') +
          "></div>";
      }
      document.dispatchEvent(
        new CustomEvent(eventName, {
          bubbles: true,
          detail: {
            elt,
            xhr: window.__requests[identityName],
            target,
            requestConfig: settings.requestConfig || {
              verb: "get",
              path: "/jobs/",
              parameters: {search: "binary", empty: ""}
            }
          }
        })
      );
    },
    { eventName: name, identityName: requestName, settings: options }
  );
}

async function advance(page, milliseconds) {
  await page.clock.fastForward(milliseconds);
}

const browser = await chromium.launch({ headless: true });

try {
  await run("1 start activates busy state and clears status", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => {
      document.getElementById("test-status").textContent = "Old status";
    });
    await dispatch(page, "htmx:beforeRequest", "A");
    assert.deepEqual(await snapshot(page), {
      busy: "true",
      hidden: false,
      ariaHidden: "false",
      indicatorText: "Updating results…",
      status: "",
      statusCount: 1
    });
    await page.close();
  });

  await run("2 fast success publishes only settled message", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await advance(page, 999);
    assert.equal((await snapshot(page)).status, "");
    await dispatch(page, "htmx:afterSwap", "A", {
      settled: { kind: "content", message: "3 jobs match" }
    });
    assert.equal((await snapshot(page)).status, "3 jobs match");
    await advance(page, 5000);
    assert.equal((await snapshot(page)).status, "3 jobs match");
    await page.close();
  });

  await run("3 uninterrupted request announces progress exactly once", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await advance(page, 1000);
    assert.equal((await snapshot(page)).status, "Updating results…");
    await advance(page, 5000);
    assert.equal((await snapshot(page)).status, "Updating results…");
    assert.equal(
      await page.locator("#test-status").getByText(
        "Updating results…",
        { exact: true }
      ).count(),
      1
    );
    await page.close();
  });

  for (const terminal of [
    "htmx:responseError",
    "htmx:sendError",
    "htmx:timeout",
    "htmx:abort"
  ]) {
    await run(`4 ${terminal} clears UI and cancels timer`, async () => {
      const page = await newFixture(browser);
      await dispatch(page, "htmx:beforeRequest", "A");
      await advance(page, 500);
      await dispatch(page, terminal, "A");
      assert.deepEqual(await snapshot(page), {
        busy: "false",
        hidden: true,
        ariaHidden: "true",
        indicatorText: "Updating results…",
        status: "",
        statusCount: 1
      });
      await advance(page, 5000);
      assert.equal((await snapshot(page)).status, "");
      await page.close();
    });
  }

  await run("5 duplicate terminal events are idempotent", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await dispatch(page, "htmx:responseError", "A");
    await dispatch(page, "htmx:abort", "A");
    await dispatch(page, "htmx:afterSwap", "A", {
      settled: { kind: "content", message: "Must not publish" }
    });
    assert.deepEqual(await snapshot(page), {
      busy: "false",
      hidden: true,
      ariaHidden: "true",
      indicatorText: "Updating results…",
      status: "",
      statusCount: 1
    });
    await page.close();
  });

  await run("6 aborting replaced A cannot clear active B", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await advance(page, 500);
    await dispatch(page, "htmx:beforeRequest", "B");
    await dispatch(page, "htmx:abort", "A");
    assert.equal((await snapshot(page)).busy, "true");
    assert.equal((await snapshot(page)).hidden, false);
    await advance(page, 500);
    assert.equal((await snapshot(page)).status, "");
    await advance(page, 500);
    assert.equal((await snapshot(page)).status, "Updating results…");
    await page.close();
  });

  await run("7 late A changes nothing after B settles", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await dispatch(page, "htmx:beforeRequest", "B");
    await dispatch(page, "htmx:afterSwap", "B", {
      settled: { kind: "content", message: "B settled" }
    });
    await dispatch(page, "htmx:afterSwap", "A", {
      settled: { kind: "content", message: "A stale" }
    });
    assert.equal((await snapshot(page)).status, "B settled");
    assert.equal((await snapshot(page)).busy, "false");
    await page.close();
  });

  await run("8 stale-guard suppression clears current request silently", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await advance(page, 1000);
    await dispatch(page, "bilbyui:listRequestSuppressed", "A", {
      settled: { kind: "content", message: "Must not publish" }
    });
    assert.equal((await snapshot(page)).busy, "false");
    assert.equal((await snapshot(page)).hidden, true);
    assert.equal((await snapshot(page)).status, "");
    await page.close();
  });

  await run("9 non-list events leave list state unchanged", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => {
      document.getElementById("test-status").textContent = "Preserve";
    });
    await dispatch(page, "htmx:beforeRequest", "X", {
      triggerId: "other-trigger",
      targetId: "other-target"
    });
    await advance(page, 5000);
    assert.deepEqual(await snapshot(page), {
      busy: "false",
      hidden: true,
      ariaHidden: "true",
      indicatorText: "Updating results…",
      status: "Preserve",
      statusCount: 1
    });
    await page.close();
  });

  await run("10 replacement cancels A timer and B owns progress", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await advance(page, 900);
    await dispatch(page, "htmx:beforeRequest", "B");
    await advance(page, 100);
    assert.equal((await snapshot(page)).status, "");
    await advance(page, 899);
    assert.equal((await snapshot(page)).status, "");
    await advance(page, 1);
    assert.equal((await snapshot(page)).status, "Updating results…");
    await page.close();
  });

  await run("11 pagination copy and history events clear pending ownership", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A", {
      triggerId: "pagination-trigger"
    });
    assert.equal((await snapshot(page)).indicatorText, "Loading page 2…");
    await page.evaluate(() => window.dispatchEvent(new PopStateEvent("popstate")));
    await dispatch(page, "htmx:abort", "A");
    await dispatch(page, "htmx:beforeRequest", "B", {
      triggerId: "pagination-trigger"
    });
    await page.evaluate(() => {
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", { detail: {} })
      );
    });
    await dispatch(page, "htmx:responseError", "B");
    assert.equal((await snapshot(page)).busy, "false");
    assert.equal((await snapshot(page)).status, "");
    await advance(page, 5000);
    assert.equal((await snapshot(page)).status, "");
    await page.close();
  });

  await run("12 indicator and status are resolved by configured IDs", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => {
      const region = document.getElementById("test-region");
      const indicator = document.getElementById("test-indicator");
      const status = document.getElementById("test-status");
      document.body.append(indicator, status);
      status.textContent = "Old";
      region.insertAdjacentHTML(
        "afterbegin",
        '<span class="list-loading-indicator" hidden aria-hidden="true">' +
        '<span class="list-loading-indicator__text">Decoy</span></span>' +
        '<p role="status">Decoy status</p>'
      );
    });
    await dispatch(page, "htmx:beforeRequest", "A");
    assert.equal(
      await page.locator("#test-indicator").getAttribute("aria-hidden"),
      "false"
    );
    assert.equal(await page.locator("#test-status").textContent(), "");
    assert.equal(
      await page.locator("#test-region p[role='status']").textContent(),
      "Decoy status"
    );
    await dispatch(page, "htmx:afterSwap", "A", {
      settled: { kind: "content", message: "ID nodes updated" }
    });
    assert.equal(
      await page.locator("#test-status").textContent(),
      "ID nodes updated"
    );
    await page.close();
  });

  for (const failureEvent of [
    "htmx:responseError",
    "htmx:sendError",
    "htmx:timeout"
  ]) {
    await run(`${failureEvent} renders current-token recovery UI`, async () => {
      const page = await newFixture(browser);
      await dispatch(page, "htmx:beforeRequest", "failure");
      await dispatch(page, failureEvent, "failure");
      const error = page.locator(
        '#job-list [data-settled-kind="error"] [role="alert"]'
      );
      const retry = error.getByRole("button", { name: "Retry" });
      assert.equal(await error.count(), 1);
      assert.equal(await retry.count(), 1);
      assert.equal(await retry.getAttribute("hx-get"), "/jobs/?search=binary");
      assert.equal(await retry.getAttribute("hx-target"), "#job-list");
      assert.equal(
        await retry.getAttribute("hx-indicator"),
        "#test-indicator"
      );
      assert.equal((await snapshot(page)).busy, "false");
      assert.equal((await snapshot(page)).hidden, true);
      await page.close();
    });
  }

  await run("superseded-token failure renders no recovery UI", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "A");
    await dispatch(page, "htmx:beforeRequest", "B");
    await dispatch(page, "htmx:responseError", "A");
    assert.equal(
      await page.locator(
        '#job-list [data-settled-kind="error"]'
      ).count(),
      0
    );
    assert.equal((await snapshot(page)).busy, "true");
    assert.equal((await snapshot(page)).hidden, false);
    await dispatch(page, "htmx:abort", "B");
    await page.close();
  });
} finally {
  await browser.close();
}

console.log(`RESULT ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exitCode = 1;
}
