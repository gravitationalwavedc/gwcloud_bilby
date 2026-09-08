"""Race-condition e2e test for the coordinated GWFlow search form.

The form owns every control and coordinates requests with
``hx-sync="#jobs-search-region:replace"`` plus a 300 ms debounce on the search input. This
test fires a search-input change and a filter-select change in quick
succession (within the debounce window) and asserts the final rendered list
matches the LAST request's state — exactly one final DOM state, no
out-of-order resolution.
"""

from __future__ import annotations

import asyncio
import threading
import time
from urllib.parse import parse_qs, urlparse

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.base import (
    LIBRARY_TOTALS,
    REVIEW_STATUS_TOTALS,
    GWFlowJobsPageBase,
    _build_gwflow_result,
)
from bilbyui.tests.e2e.utils import async_e2e_test

#: Simulated ES latency so concurrent requests genuinely overlap and the
#: hx-sync coordination is exercised rather than trivially serialised.
SLOW_ES_DELAY_SECONDS = 0.4


class _SlowRequestGate:
    """Deterministic control of server-side request completion.

    The server-side side effect signals when a request for a given search
    value is in flight (``started``) and then blocks until the test releases
    it (``release``). This lets the test complete request A inside a debounce
    window deterministically, instead of relying on a fixed sleep, so it can
    prove whether an obsolete completion promotes stale history.
    """

    def __init__(self):
        self._started = {}
        self._release = {}
        self._lock = threading.Lock()

    def _events(self, key):
        with self._lock:
            if key not in self._started:
                self._started[key] = threading.Event()
                self._release[key] = threading.Event()
            return self._started[key], self._release[key]

    def started(self, key):
        self._events(key)[0].set()

    def wait_started(self, key, timeout=10):
        return self._events(key)[0].wait(timeout)

    def release(self, key):
        self._events(key)[1].set()

    def wait_release(self, key, timeout=10):
        return self._events(key)[1].wait(timeout)

    def reset(self):
        with self._lock:
            self._started.clear()
            self._release.clear()


GATE = _SlowRequestGate()


def _gated_race_side_effect(
    user, *, search="", library="", review_status="", time_range="all", page=1, page_size=20, **kwargs
):
    """Server-side side effect that blocks until the test releases the request.

    The ``total`` still encodes the request params so the DOM reveals which
    request state is rendered. The test gates completion via :data:`GATE`.
    """
    GATE.started(search)
    GATE.wait_release(search)
    jobs = list(GWFlowJob.objects.order_by("id"))
    total = len(search) + LIBRARY_TOTALS.get(library, 0) + REVIEW_STATUS_TOTALS.get(review_status, 0)
    return _build_gwflow_result(jobs, total=total)


def _slow_race_side_effect(
    user, *, search="", library="", review_status="", time_range="all", page=1, page_size=20, **kwargs
):
    """Slow ES-like response whose ``total`` encodes the request params.

    The deterministic total (``len(search)`` + per-library / per-review-status
    contribution) lets the test read which request state the DOM reflects from
    the rendered result count.
    """
    time.sleep(SLOW_ES_DELAY_SECONDS)
    jobs = list(GWFlowJob.objects.order_by("id"))
    total = len(search) + LIBRARY_TOTALS.get(library, 0) + REVIEW_STATUS_TOTALS.get(review_status, 0)
    return _build_gwflow_result(jobs, total=total)


class TestGWFlowSearchRace(GWFlowJobsPageBase):
    """Simultaneous search-input + filter-select changes settle on the last request."""

    gwflow_jobs_side_effect = staticmethod(_slow_race_side_effect)

    @async_e2e_test
    async def test_simultaneous_search_and_filter_produce_one_final_state(self):
        page = self.page
        search = page.locator("#search")
        library = page.locator("#library")

        # Sanity: the initial list renders with no filters.
        await page.wait_for_selector(".result-count")
        self.assertIn("0 superevents match", await page.locator(".result-count").text_content())

        # Fire a search-input change (debounced 300 ms) ...
        await search.press_sequentially("abc")
        # ... and a filter-select change within the debounce window.
        await library.select_option("lib1")

        # The coordinated stream must settle on the LAST request's state:
        # search="abc" AND library="lib1" -> total = 3 + 1000 = 1003.
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('1003'); }",
            timeout=10000,
        )

        # Exactly one final state: the count must stay put (no out-of-order
        # resolution flipping it back to an earlier request's value).
        await page.wait_for_timeout(700)
        self.assertIn("1003 superevents match", await page.locator(".result-count").text_content())

        # Focus stays on the triggering control (WCAG 3.2.2): the search input
        # is outside the swapped list region and must not be replaced.
        self.assertEqual(
            await page.evaluate("document.activeElement ? document.activeElement.id : null"),
            "search",
            "focus must remain on the search input after the list swap",
        )

        # Exactly one live status region per settled fragment (announced once).
        status_count = await page.evaluate("document.querySelectorAll('[role=\"status\"]').length")
        self.assertEqual(status_count, 1, "exactly one role=status region per settled fragment")

        # The settled state is encoded in the URL and the active-filter chip.
        self.assertIn("search=abc", page.url)
        self.assertIn("library=lib1", page.url)
        self.assertGreaterEqual(
            await page.locator(".filter-chip", has_text="Library: lib1").count(),
            1,
            "Library: lib1 chip must be present",
        )

        # Last request wins: switching the filter must replace the previous
        # state entirely (no stale lib1 chip, no stale count).
        await library.select_option("lib2")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('2003'); }",
            timeout=10000,
        )
        self.assertIn("library=lib2", page.url)
        self.assertEqual(
            await page.locator(".filter-chip", has_text="Library: lib1").count(),
            0,
            "stale Library: lib1 chip must be gone",
        )
        self.assertGreaterEqual(
            await page.locator(".filter-chip", has_text="Library: lib2").count(),
            1,
            "Library: lib2 chip must be present",
        )
        await page.wait_for_timeout(700)
        self.assertIn("2003 superevents match", await page.locator(".result-count").text_content())


class TestGWFlowSiblingSourceRace(GWFlowJobsPageBase):
    """A chip-removal request overlapping a form request settles on the last request.

    Both sources target the same list region and share the
    ``#jobs-search-region`` synchronisation boundary, so the chip removal must
    replace the in-flight (or pending) form request rather than resolve
    out-of-order.
    """

    gwflow_jobs_side_effect = staticmethod(_slow_race_side_effect)

    @async_e2e_test
    async def test_chip_removal_overlapping_form_request_wins(self):
        page = self.page
        # Load with a library filter active so a removable chip is rendered.
        await page.goto(f"{self.gwflow_url()}?library=lib1")
        await page.wait_for_selector(".filter-chip")
        await page.wait_for_selector(".result-count")

        # Fire a search-input change (slow request A) ...
        search = page.locator("#search")
        await search.press_sequentially("abc")
        # Wait for the debounced form request to fire and be in-flight (the
        # slow mock sleeps SLOW_ES_DELAY_SECONDS) ...
        await page.wait_for_timeout(350)
        # ... then click the chip removal while request A is still in flight.
        await page.locator(".filter-chip-remove").click()

        # The shared sync boundary must settle on the LAST request: the chip
        # removal (library removed, search cleared) -> total = 0, no chips.
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('0 superevents match'); }",
            timeout=10000,
        )
        await page.wait_for_timeout(700)
        self.assertIn("0 superevents match", await page.locator(".result-count").text_content())
        self.assertEqual(await page.locator(".filter-chip").count(), 0, "no chips must remain after removal")
        self.assertNotIn("library=", page.url, "URL must reflect the chip removal")


class TestChipRemovalSyncsForm(GWFlowJobsPageBase):
    """Chip removal must sync the persistent form so a removed filter is not
    silently reintroduced by the next form submission (round-4 finding).

    Issue #75 (UX-17) moved this from the generic ``htmx:pushedIntoHistory``
    write-back to a targeted, action-specific reset: removing a chip resets
    ONLY the removed control (its ``param_name``), synchronously when the user
    action starts. It is no longer driven by any history event.
    """

    @async_e2e_test
    async def test_chip_removal_resets_form_control(self):
        page = self.page
        await page.goto(f"{self.gwflow_url()}?library=lib1")
        await page.wait_for_selector(".filter-chip")
        await page.wait_for_selector(".result-count")

        # The Library select reflects the active filter.
        self.assertEqual(await page.locator("#library").input_value(), "lib1")

        # Remove the library chip.
        await page.locator(".filter-chip-remove").click()
        await page.wait_for_function(
            "() => document.querySelector('.filter-chip') === null",
            timeout=10000,
        )

        # The persistent form control is reset by the targeted chip-removal
        # action sync (NOT by htmx:pushedIntoHistory, which is removed).
        self.assertEqual(await page.locator("#library").input_value(), "")
        self.assertNotIn("library=lib1", page.url)

        # A subsequent filter change must not reintroduce the removed library.
        await page.locator("#review").select_option("approved")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('3000'); }",
            timeout=10000,
        )
        self.assertNotIn("library=lib1", page.url)
        self.assertIn("review=approved", page.url)


class TestGWFlowOriginalRaceRegression(GWFlowJobsPageBase):
    """The exact original race (issue #75 / UX-17) reproduced as a regression.

    Type ``S23``, let the debounced request A (search=S23) start and be in
    flight, keep typing to ``S2305`` while request A is still in flight, then
    assert the live input stays exactly ``S2305`` with focus and caret
    preserved, and that the final results and final URL both use ``S2305`` —
    the obsolete ``S23`` completion must not become the final rendered or
    navigable state.

    The request is gated deterministically (``_gated_race_side_effect``) so
    request A is released to complete *inside* request B's trailing debounce
    window, before B starts. This proves the acceptance contract that a
    superseded completion cannot create an authoritative history entry: the
    obsolete ``S23`` must neither swap nor push a URL, and exactly one
    history entry (the accepted ``S2305`` intent) may be added.

    Before the fix, request A's completion pushed ``search=S23`` to history
    and the ``htmx:pushedIntoHistory`` write-back reset the live input to
    ``S23``, dropping the continued typing. The fix removes that write-back
    and adds a stale-history guard (``search_stale_guard.js``) so an
    obsolete completion is neither swapped nor promoted to history.
    """

    gwflow_jobs_side_effect = staticmethod(_gated_race_side_effect)

    def setUp(self):
        super().setUp()
        GATE.reset()

    @async_e2e_test
    async def test_obsolete_completion_cannot_promote_stale_history(self):
        page = self.page
        search = page.locator("#search")
        await page.wait_for_selector(".result-count")

        # Type the prefix and wait until request A (search=S23) is confirmed
        # in flight (deterministic gate, not a fixed sleep).
        await search.press_sequentially("S23")
        self.assertTrue(
            await asyncio.to_thread(GATE.wait_started, "S23"),
            "request A (search=S23) must be in flight",
        )

        history_length = await page.evaluate("window.history.length")

        # Keep typing to the full query; request B (S2305) is scheduled but
        # still inside its 300 ms trailing debounce (not yet started).
        await search.press_sequentially("05")

        # Complete request A now — inside B's debounce window, before B fires.
        await asyncio.to_thread(GATE.release, "S23")

        # The live input stays S2305, and the obsolete S23 completion must
        # not promote stale history (no new entry, URL not reverted to S23).
        self.assertEqual(await search.input_value(), "S2305")
        self.assertEqual(
            await page.evaluate("document.activeElement ? document.activeElement.id : null"),
            "search",
            "focus must remain on the search input",
        )
        caret = await search.evaluate("(el) => [el.selectionStart, el.selectionEnd]")
        self.assertEqual(caret, [5, 5], "caret must be preserved at the end of S2305")
        await page.wait_for_timeout(100)
        self.assertEqual(
            await page.evaluate("window.history.length"),
            history_length,
            "the obsolete S23 completion must not add a history entry",
        )
        self.assertNotEqual(
            parse_qs(urlparse(page.url).query).get("search", [""])[0],
            "S23",
            "the obsolete S23 completion must not promote a stale URL",
        )

        # Request B settles on S2305: exactly one authoritative history entry.
        await asyncio.to_thread(GATE.release, "S2305")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('5 superevents match'); }",
            timeout=10000,
        )
        self.assertEqual(
            parse_qs(urlparse(page.url).query).get("search", [""])[0],
            "S2305",
            "final URL search must be S2305, not the obsolete S23",
        )
        self.assertEqual(
            await page.evaluate("window.history.length"),
            history_length + 1,
            "only the accepted S2305 intent may add a history entry",
        )
        self.assertEqual(await search.input_value(), "S2305")


class TestPushedIntoHistoryDoesNotWriteForm(GWFlowJobsPageBase):
    """``htmx:pushedIntoHistory`` must not write any URL value into a form
    control (issue #75 / UX-17 acceptance criterion).

    URL -> form sync now happens only on ``popstate`` / ``htmx:historyRestore``.
    Dispatching ``pushedIntoHistory`` with the URL carrying different values
    must leave every control untouched.
    """

    @async_e2e_test
    async def test_pushed_into_history_does_not_alter_any_control(self):
        page = self.page
        # Load with URL values that differ from what we set below.
        await page.goto(f"{self.gwflow_url()}?search=foo&library=lib1&review=approved&time_range=1w")
        await page.wait_for_selector(".result-count")

        # Set every control to a value that differs from the URL.
        await page.locator("#search").fill("S2305")
        await page.locator("#library").select_option("lib2")
        await page.locator("#review").select_option("reviewed")
        await page.locator("#time_range").select_option("1d")
        await page.locator("#advanced-search").fill("S2305")

        # Dispatch the event that must not write into any control.
        await page.evaluate("document.dispatchEvent(new Event('htmx:pushedIntoHistory'))")

        # No control may have been overwritten by the URL's values.
        self.assertEqual(await page.locator("#search").input_value(), "S2305")
        self.assertEqual(await page.locator("#advanced-search").input_value(), "S2305")
        self.assertEqual(await page.locator("#library").input_value(), "lib2")
        self.assertEqual(await page.locator("#review").input_value(), "reviewed")
        self.assertEqual(await page.locator("#time_range").input_value(), "1d")


class TestSearchIMEComposition(GWFlowJobsPageBase):
    """IME composition must not fire requests for incomplete text; only the
    final composed value is searched, exactly once, after settling."""

    @async_e2e_test
    async def test_composing_inputs_do_not_trigger_and_compositionend_triggers_once(self):
        page = self.page
        await page.wait_for_selector(".result-count")

        list_requests = []
        page.on(
            "request",
            lambda r: list_requests.append(r.url) if r.url.startswith(self.gwflow_url()) else None,
        )

        # Phase 1: composing input events only -> no request may fire. The
        # in-progress composition is not yet committed to the input value, so
        # nothing is submitted (the htmx:beforeRequest guard also cancels any
        # request that would fire mid-composition).
        await page.evaluate(
            """() => {
              const input = document.querySelector('#search');
              input.focus();
              input.dispatchEvent(new CompositionEvent('compositionstart', { data: '' }));
              input.dispatchEvent(new InputEvent('input', { bubbles: true, data: '\u3042', isComposing: true }));
              input.dispatchEvent(new InputEvent('input', { bubbles: true, data: '\u3044', isComposing: true }));
            }"""
        )
        # Longer than the 300 ms debounce: no request may have been scheduled.
        await page.wait_for_timeout(400)
        self.assertEqual(len(list_requests), 0, "composing inputs must not trigger a request")

        # Phase 2: compositionend commits the final composed value; after
        # settling, exactly one request for the final composed value.
        await page.evaluate(
            """() => {
              const input = document.querySelector('#search');
              input.value = '\u3042\u3044';
              input.dispatchEvent(new CompositionEvent('compositionend', { data: '\u3042\u3044' }));
            }"""
        )
        # total = len('\u3042\u3044') = 2.
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('2 superevents match'); }",
            timeout=10000,
        )
        self.assertEqual(len(list_requests), 1, "compositionend must trigger exactly one request")
        self.assertIn("search=", list_requests[0])


class TestSearchNativeClear(GWFlowJobsPageBase):
    """The native search-clear control must search for the empty value."""

    @async_e2e_test
    async def test_native_clear_searches_for_empty_value(self):
        page = self.page
        await page.wait_for_selector(".result-count")

        # Type a search and wait for it to take effect. Without this, the
        # later wait for "0 superevents match" would match the unchanged
        # initial page state (also 0) before any request fires, making the
        # request-count assertion racy.
        await page.locator("#search").fill("S2305")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('5 superevents match'); }",
            timeout=10000,
        )

        # Simulate the native search-clear control firing the search event, and
        # deterministically wait for the resulting list request.
        async with page.expect_request(
            lambda r: r.url.startswith(self.gwflow_url()) and "search=" in r.url
        ) as req_info:
            await page.evaluate(
                """() => {
                  const input = document.querySelector('#search');
                  input.value = '';
                  input.dispatchEvent(new Event('search', { bubbles: true }));
                }"""
            )
        req = await req_info.value

        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('0 superevents match'); }",
            timeout=10000,
        )
        self.assertIn("search=", req.url, "clear request must carry the search param")
        self.assertEqual(await page.locator("#search").input_value(), "")


class TestBackForwardCoherence(GWFlowJobsPageBase):
    """Back/forward restore a coherent state (URL, controls, results) with no
    duplicate request, no extra history entry and no forced focus."""

    @async_e2e_test
    async def test_back_forward_restores_coherent_state(self):
        page = self.page
        await page.wait_for_selector(".result-count")

        # Apply a filter -> one history entry.
        await page.locator("#library").select_option("lib1")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('1000 superevents match'); }",
            timeout=10000,
        )
        self.assertIn("library=lib1", page.url)

        list_requests = []
        page.on(
            "request",
            lambda r: list_requests.append(r.url) if r.url.startswith(self.gwflow_url()) else None,
        )
        hist_len = await page.evaluate("window.history.length")

        # Back -> initial state restored from the htmx history cache.
        await page.go_back()
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('0 superevents match'); }",
            timeout=10000,
        )
        self.assertEqual(await page.locator("#library").input_value(), "")
        self.assertNotIn("library=", page.url)

        # Forward -> filtered state restored again.
        await page.go_forward()
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('1000 superevents match'); }",
            timeout=10000,
        )
        self.assertEqual(await page.locator("#library").input_value(), "lib1")
        self.assertIn("library=lib1", page.url)

        # No duplicate request fired during back/forward (htmx history cache).
        self.assertEqual(len(list_requests), 0, "back/forward must not fire a new list request")
        # No extra history entry created by back/forward.
        self.assertEqual(await page.evaluate("window.history.length"), hist_len)
        # No forced focus onto the search input.
        self.assertNotEqual(
            await page.evaluate("document.activeElement ? document.activeElement.id : null"),
            "search",
            "back/forward must not force focus onto the search input",
        )


class TestRefreshCoherence(GWFlowJobsPageBase):
    """A genuine browser refresh restores a coherent state: URL, search/filter
    controls, active-filter chips, results and count all agree, with no
    duplicate request and no extra history entry (issue #75 / UX-17 AC5)."""

    @async_e2e_test
    async def test_refresh_restores_coherent_state(self):
        page = self.page
        await page.wait_for_selector(".result-count")

        # Apply a filter -> one history entry.
        await page.locator("#library").select_option("lib1")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('1000 superevents match'); }",
            timeout=10000,
        )
        self.assertIn("library=lib1", page.url)
        hist_before = await page.evaluate("window.history.length")

        # Genuine browser refresh (server re-renders from request params).
        await page.reload()
        await page.wait_for_selector(".result-count")

        # URL, controls, chips, results and count all agree after refresh.
        self.assertIn("library=lib1", page.url)
        self.assertEqual(await page.locator("#library").input_value(), "lib1")
        self.assertGreaterEqual(
            await page.locator(".filter-chip", has_text="Library: lib1").count(),
            1,
            "Library: lib1 chip must be present after refresh",
        )
        self.assertIn("1000 superevents match", await page.locator(".result-count").text_content())

        # No extra history entry from the refresh.
        self.assertEqual(
            await page.evaluate("window.history.length"),
            hist_before,
            "a refresh must not add a history entry",
        )


class TestNoUnexpectedScroll(GWFlowJobsPageBase):
    """An input-triggered update must not cause unexpected page scroll
    (issue #75 / UX-17 AC6)."""

    gwflow_jobs_side_effect = staticmethod(_slow_race_side_effect)

    @async_e2e_test
    async def test_input_triggered_update_does_not_scroll(self):
        page = self.page
        search = page.locator("#search")
        await page.wait_for_selector(".result-count")

        # Type a query and let the debounced request settle.
        await search.press_sequentially("abc")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('3 superevents match'); }",
            timeout=10000,
        )

        # The list swap below the input must not scroll the page.
        self.assertEqual(
            await page.evaluate("window.scrollY"),
            0,
            "input-triggered update must not scroll the page",
        )


class TestResetAllFollowedByFilterChange(GWFlowJobsPageBase):
    """Reset all must clear every represented control so a subsequent filter
    change does not reintroduce removed values (issue #75 / UX-17)."""

    @async_e2e_test
    async def test_reset_all_then_filter_change_does_not_reintroduce_removed_values(self):
        page = self.page
        await page.goto(f"{self.gwflow_url()}?library=lib1&review=approved")
        await page.wait_for_selector(".filter-chip")
        await page.wait_for_selector(".result-count")

        self.assertEqual(await page.locator("#library").input_value(), "lib1")
        self.assertEqual(await page.locator("#review").input_value(), "approved")

        # Reset all -> every represented control returns to its default.
        await page.locator(".filter-reset").click()
        await page.wait_for_function(
            "() => document.querySelector('.filter-chip') === null",
            timeout=10000,
        )
        self.assertEqual(await page.locator("#library").input_value(), "")
        self.assertEqual(await page.locator("#review").input_value(), "")
        self.assertEqual(await page.locator("#time_range").input_value(), "all")

        # A subsequent filter change must not reintroduce the removed values.
        await page.locator("#library").select_option("lib2")
        await page.wait_for_function(
            "() => { const el = document.querySelector('.result-count'); return el && el.textContent.includes('2000 superevents match'); }",
            timeout=10000,
        )
        self.assertIn("library=lib2", page.url)
        self.assertNotIn("review=approved", page.url, "removed review value must not be reintroduced")
        self.assertEqual(await page.locator("#review").input_value(), "")
