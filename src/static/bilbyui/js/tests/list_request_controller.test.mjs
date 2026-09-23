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
    data-list-heading="test-results-heading"
    data-list-status="test-status"
    aria-busy="false"
  >
    <h2 id="test-results-heading" tabindex="-1">Test results</h2>
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
    <button id="search-trigger" hx-target="#job-list" hx-sync="#jobs-search-region:replace">Search</button>
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
          (settings.settled.title === undefined
            ? ""
            : ' data-document-title="' +
              settings.settled.title +
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
      assert.equal(await retry.getAttribute("hx-sync"), "#jobs-search-region:replace");
      assert.equal((await snapshot(page)).busy, "false");
      assert.equal((await snapshot(page)).hidden, true);
      await page.close();
    });
  }


  await run("explicit pagination success sets title and focuses heading once", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => {
      const heading = document.getElementById("test-results-heading");
      window.__headingFocusCount = 0;
      const originalFocus = heading.focus.bind(heading);
      heading.focus = (options) => {
        window.__headingFocusCount += 1;
        window.__focusOptions = options;
        originalFocus(options);
      };
    });
    await dispatch(page, "htmx:beforeRequest", "page", {
      triggerId: "pagination-trigger"
    });
    await dispatch(page, "htmx:afterSwap", "page", {
      triggerId: "pagination-trigger",
      settled: {
        kind: "content",
        message: "Page 2 of 4, 20 jobs shown",
        title: "My Jobs, page 2"
      }
    });
    assert.equal(await page.title(), "My Jobs, page 2");
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "test-results-heading"
    );
    assert.equal(await page.evaluate(() => window.__headingFocusCount), 1);
    assert.deepEqual(
      await page.evaluate(() => window.__focusOptions),
      { preventScroll: true }
    );
    assert.equal(
      (await snapshot(page)).status,
      "Page 2 of 4, 20 jobs shown"
    );
    await page.close();
  });

  for (const triggerId of ["search-trigger", "other-trigger"]) {
    await run(`${triggerId} success does not focus results heading`, async () => {
      const page = await newFixture(browser);
      const targetId = triggerId === "other-trigger" ? "other-target" : "job-list";
      await dispatch(page, "htmx:beforeRequest", "normal", {
        triggerId,
        targetId
      });
      await dispatch(page, "htmx:afterSwap", "normal", {
        triggerId,
        targetId,
        settled: {
          kind: "content",
          message: "Settled",
          title: "Search title"
        }
      });
      assert.notEqual(
        await page.evaluate(() => document.activeElement.id),
        "test-results-heading"
      );
      await page.close();
    });
  }

  await run("replacement search clears pagination focus ownership", async () => {
    const page = await newFixture(browser);
    await dispatch(page, "htmx:beforeRequest", "page", {
      triggerId: "pagination-trigger"
    });
    await dispatch(page, "htmx:beforeRequest", "search");
    await dispatch(page, "htmx:afterSwap", "search", {
      settled: {
        kind: "content",
        message: "Search settled",
        title: "Search results"
      }
    });
    assert.notEqual(
      await page.evaluate(() => document.activeElement.id),
      "test-results-heading"
    );
    await page.close();
  });

  await run("stale success cannot focus or set document title", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => { document.title = "Original"; });
    await dispatch(page, "htmx:beforeRequest", "A", {
      triggerId: "pagination-trigger"
    });
    await dispatch(page, "htmx:beforeRequest", "B");
    await dispatch(page, "htmx:afterSwap", "A", {
      triggerId: "pagination-trigger",
      settled: {
        kind: "content",
        message: "Stale",
        title: "Stale title"
      }
    });
    assert.equal(await page.title(), "Original");
    assert.notEqual(
      await page.evaluate(() => document.activeElement.id),
      "test-results-heading"
    );
    await dispatch(page, "htmx:abort", "B");
    await page.close();
  });

  for (const terminal of [
    "htmx:responseError",
    "htmx:sendError",
    "htmx:timeout",
    "htmx:abort",
    "bilbyui:listRequestSuppressed"
  ]) {
    await run(`${terminal} clears pagination without focus`, async () => {
      const page = await newFixture(browser);
      await dispatch(page, "htmx:beforeRequest", "page", {
        triggerId: "pagination-trigger"
      });
      await dispatch(page, terminal, "page", {
        triggerId: "pagination-trigger"
      });
      assert.notEqual(
        await page.evaluate(() => document.activeElement.id),
        "test-results-heading"
      );
      await page.close();
    });
  }

  await run("popstate and history restore do not become pagination activation", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => {
      document.getElementById("search-trigger").focus();
      window.dispatchEvent(new PopStateEvent("popstate"));
      document.getElementById("job-list").innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Restored title" ' +
        'data-settled-message="Must not announce"></div>';
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
    });
    await advance(page, 0);
    assert.equal(await page.title(), "Restored title");
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "search-trigger"
    );
    assert.equal((await snapshot(page)).status, "");
    await page.close();
  });

  await run("history restore repairs detached list focus exactly once", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => {
      const target = document.getElementById("job-list");
      target.innerHTML = '<a id="old-page" href="#">Old page</a>';
      document.getElementById("old-page").focus();
      const heading = document.getElementById("test-results-heading");
      window.__historyFocusCount = 0;
      const originalFocus = heading.focus.bind(heading);
      heading.focus = (options) => {
        window.__historyFocusCount += 1;
        originalFocus(options);
      };
      window.dispatchEvent(new PopStateEvent("popstate"));
      target.innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Restored page"></div>';
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
    });
    await advance(page, 0);
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "test-results-heading"
    );
    assert.equal(await page.evaluate(() => window.__historyFocusCount), 1);
    assert.equal(await page.title(), "Restored page");
    await page.close();
  });

  await run("history restore leaves focus untouched when no list element was focused", async () => {
    const page = await newFixture(browser);
    const observed = await page.evaluate(async () => {
      const search = document.getElementById("search-trigger");
      search.focus();
      search.blur();
      window.dispatchEvent(new PopStateEvent("popstate"));
      document.getElementById("job-list").innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Approved first-page title"></div>';
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
      await new Promise((resolve) => setTimeout(resolve, 0));
      return {
        active: {
          id: document.activeElement.id,
          tagName: document.activeElement.tagName,
          connected: document.activeElement.isConnected,
          isBody: document.activeElement === document.body
        },
        title: document.title
      };
    });
    assert.deepEqual(observed.active, {
      id: "",
      tagName: "BODY",
      connected: true,
      isBody: true
    });
    assert.equal(observed.title, "Approved first-page title");
    await page.close();
  });

  await run("history restore repairs body fallback to surviving outside focus", async () => {
    const page = await newFixture(browser);
    const observed = await page.evaluate(async () => {
      const search = document.getElementById("search-trigger");
      search.focus();
      window.dispatchEvent(new PopStateEvent("popstate"));
      search.blur();
      document.getElementById("job-list").innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Page one title"></div>';
      const before = {
        id: document.activeElement.id,
        tagName: document.activeElement.tagName,
        connected: document.activeElement.isConnected
      };
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
      await new Promise((resolve) => setTimeout(resolve, 350));
      return {
        before,
        after: {
          id: document.activeElement.id,
          tagName: document.activeElement.tagName,
          connected: document.activeElement.isConnected
        },
        title: document.title
      };
    });
    assert.deepEqual(observed.before, {
      id: "",
      tagName: "BODY",
      connected: true
    });
    assert.deepEqual(observed.after, {
      id: "search-trigger",
      tagName: "BUTTON",
      connected: true
    });
    assert.equal(observed.title, "Page one title");
    await page.close();
  });

  await run("detached history restore focuses the heading exactly once", async () => {
    const page = await newFixture(browser);
    const observed = await page.evaluate(async () => {
      const target = document.getElementById("job-list");
      target.innerHTML = '<a id="detached-page" href="#">Page</a>';
      const detached = document.getElementById("detached-page");
      const heading = document.getElementById("test-results-heading");
      let headingFocusCalls = 0;
      const originalFocus = heading.focus.bind(heading);
      heading.focus = (options) => {
        headingFocusCalls += 1;
        originalFocus(options);
      };

      detached.focus();
      window.dispatchEvent(new PopStateEvent("popstate"));
      target.innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Restored detached title"></div>';
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );

      await new Promise((resolve) => setTimeout(resolve, 0));
      return {
        detachedConnected: detached.isConnected,
        headingFocusCalls,
        active: {
          id: document.activeElement.id,
          tagName: document.activeElement.tagName,
          connected: document.activeElement.isConnected,
          isBody: document.activeElement === document.body
        },
        title: document.title
      };
    });
    assert.equal(observed.detachedConnected, false);
    assert.deepEqual(observed.active, {
      id: "test-results-heading",
      tagName: "H2",
      connected: true,
      isBody: false
    });
    assert.equal(observed.headingFocusCalls, 1);
    assert.equal(observed.title, "Restored detached title");
    await page.close();
  });

  await run("whole-body history restore re-resolves surviving focus by id", async () => {
    const page = await newFixture(browser);
    const observed = await page.evaluate(async () => {
      const oldSearch = document.getElementById("search-trigger");
      oldSearch.focus();
      window.dispatchEvent(new PopStateEvent("popstate"));

      const replacement = oldSearch.cloneNode(true);
      oldSearch.replaceWith(replacement);
      document.getElementById("job-list").innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Restored body title"></div>';

      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
      await new Promise((resolve) => setTimeout(resolve, 0));

      return {
        oldConnected: oldSearch.isConnected,
        active: {
          id: document.activeElement.id,
          tagName: document.activeElement.tagName,
          connected: document.activeElement.isConnected,
          isBody: document.activeElement === document.body
        },
        title: document.title
      };
    });

    console.log(
      "RERESOLVED_HISTORY_FOCUS " + JSON.stringify(observed)
    );
    assert.equal(observed.oldConnected, false);
    assert.deepEqual(observed.active, {
      id: "search-trigger",
      tagName: "BUTTON",
      connected: true,
      isBody: false
    });
    assert.equal(observed.title, "Restored body title");
    await page.close();
  });

  await run("history restore does not double-focus a surviving element", async () => {
    const page = await newFixture(browser);
    const observed = await page.evaluate(async () => {
      const search = document.getElementById("search-trigger");
      search.focus();
      let focusCalls = 0;
      const originalFocus = search.focus.bind(search);
      search.focus = (options) => {
        focusCalls += 1;
        originalFocus(options);
      };

      window.dispatchEvent(new PopStateEvent("popstate"));
      document.getElementById("job-list").innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Approved first-page title"></div>';

      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );

      await new Promise((resolve) => setTimeout(resolve, 0));
      return {
        focusCalls,
        active: {
          id: document.activeElement.id,
          tagName: document.activeElement.tagName,
          connected: document.activeElement.isConnected,
          isBody: document.activeElement === document.body
        },
        title: document.title
      };
    });
    assert.deepEqual(observed.active, {
      id: "search-trigger",
      tagName: "BUTTON",
      connected: true,
      isBody: false
    });
    assert.equal(observed.focusCalls, 0);
    assert.equal(observed.title, "Approved first-page title");
    await page.close();
  });


  await run("history restore preserves surviving focus", async () => {
    const page = await newFixture(browser);
    await page.evaluate(() => {
      const search = document.getElementById("search-trigger");
      search.focus();
      window.dispatchEvent(new PopStateEvent("popstate"));
      document.getElementById("job-list").innerHTML =
        '<div data-settled-kind="content" ' +
        'data-document-title="Preserved focus"></div>';
      document.dispatchEvent(
        new CustomEvent("htmx:historyRestore", {detail: {}})
      );
    });
    await advance(page, 0);
    assert.equal(
      await page.evaluate(() => document.activeElement.id),
      "search-trigger"
    );
    await page.close();
  });

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
