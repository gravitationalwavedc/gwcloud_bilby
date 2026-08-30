# Testing

This document covers the Playwright end-to-end (e2e) stack. For general unit
test conventions see [AGENTS.md](AGENTS.md) and run:

```bash
cd src && bash run_coverage.sh --parallel
```

## E2E stack

E2e tests are plain Django tests (`django.test` discovery, `manage.py test`)
that drive a real browser via [Playwright](https://playwright.dev/python/):

- **One shared headless Chromium per process.** `pw_server.py` installs the
  Node side of Playwright into `<repo-root>/.playwright/` on first use and
  starts a single `chromium.launchServer()`. Tests connect to it over
  WebSocket; every test gets its own fresh `BrowserContext`.
- **`PW_WS_ENDPOINT` wiring.** If the environment variable is set, tests use
  that endpoint instead of starting a server — this is how CI or a custom
  runner shares one browser server across parallel workers. Otherwise
  `utils.ensure_pw_endpoint()` lazily starts one server for the current
  process and stops it via `atexit`.
- **Lazy start means unit-only runs never need Node.** The server is only
  started from within the `async_e2e_test` decorator. Running any other test
  module never imports a browser, spawns Node, or touches `.playwright/`.
- **Exact-pinned, lifecycle-script-free install.** `pw_server.py` installs
  `playwright@{python version}` and `axe-core@4.10.3` (exact pins) with
  `--ignore-scripts --no-audit --no-fund --save-exact`, so no npm lifecycle
  scripts run in the privileged CI environment. The install is skipped only
  when `.playwright/node_modules/playwright/package.json` matches the Python
  `playwright` version **and** the installed `axe-core` version equals the
  pinned `4.10.3`.
- **Serial install in CI.** The `django-tests` job initializes
  `.playwright/` once, serially, before `run_coverage.sh --parallel` spawns
  workers, so parallel workers never race to mutate the shared npm tree.
- **Inter-process lock for local parallel runs.** The Python bootstrap wraps
  the npm mutation in an advisory `fcntl.flock` on
  `.playwright/.install.lock` (blocking with a timeout) and double-checks the
  pinned versions after acquiring the lock, so local `--parallel N` runs
  serialize the install too.

Infrastructure lives in `src/bilbyui/tests/e2e/`:

| File | Purpose |
| --- | --- |
| `pw_server.py` | Shared Chromium launchServer lifecycle + Node dependency install |
| `utils.py` | `AsyncE2ETestCase`, `async_e2e_test` decorator, cookie login, axe helpers |

## Conventions (normative)

1. **Exactly ONE test method per Playwright test class.** Browser contexts,
   login state, and page fixtures are shared at class level; one test method
   keeps that sharing predictable.
2. **Shared setup lives in a base class containing NO test cases.** Concrete
   test classes inherit from the base and each add their single test.

```python
class TechValuePageBase(AsyncE2ETestCase):
    async def asetUp(self):
        user = ...  # create fixtures once here

class TestTechValueAxe(TechValuePageBase):
    @async_e2e_test
    async def test_zero_serious_violations(self):
        ...
```

Authentication is cookie-based: `login(user)` force-logs in via the Django
test client, copies the session cookies into the browser context, and caches
the resulting storage state per class so later tests skip the login flow.

## Running e2e locally

```bash
cd src && DJANGO_SETTINGS_MODULE=gw_bilby.test \
  poetry run python manage.py test bilbyui.tests.e2e --parallel 1
```

The first run downloads npm packages into `<repo-root>/.playwright/`; the
Python-side Chromium binaries come from `poetry run playwright install
chromium` (already covered by `poetry install --with dev` plus that command).
Subsequent runs reuse both and start in milliseconds.

Without `PW_WS_ENDPOINT` set, `--parallel N` gives each worker its own browser
server. To share one across workers, export `PW_WS_ENDPOINT` from a parent
process that called `start_pw_server()` first.

## Accessibility (axe)

axe-core is npm-installed into `.playwright/node_modules/axe-core/` alongside
Playwright. `load_axe(page)` injects the bundled `axe.min.js` via
`page.evaluate(source)` — this works under strict Content-Security-Policy
where script-tag injection would be blocked. `run_axe(page, scope_selector)`
runs axe scoped to the given selector and returns the violations array.
Policy: **zero serious or critical violations** on scanned pages, scanned
region by region.

- Axe scope: scans run against the page content region, not app chrome;
  shell-wide contrast fixes are tracked outside this suite.

## Technical-value component

The `_tech_value.html` primitive (issue #49) is covered by render, keyboard,
overflow, and clipboard e2e tests:

- **Disclosure.** The toggle is a `<button>` with `aria-expanded` and an
  optional `disclosure_id` parameter; when supplied, `aria-controls` points at
  the full-value span's matching unique ID.
- **Clipboard.** The copy handler is async: it reports "Copied" only when
  `navigator.clipboard.writeText` resolves and "Copy failed" when it rejects,
  so a denied or unavailable clipboard never announces a false success.
