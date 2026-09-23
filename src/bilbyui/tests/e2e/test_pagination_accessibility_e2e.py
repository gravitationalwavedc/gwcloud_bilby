"""Browser coverage for issue #77 pagination accessibility and history."""

from __future__ import annotations

from bilbyui.models import GWFlowJob
from bilbyui.tests.e2e.base import GWFlowJobsPageBase, _build_gwflow_result
from bilbyui.tests.e2e.utils import async_e2e_test, load_axe, run_axe


def _paginated_result(
    user,
    *,
    search="",
    library="",
    review_status="",
    time_range="all",
    page=1,
    page_size=20,
    **kwargs,
):
    jobs = list(GWFlowJob.objects.order_by("id"))
    return _build_gwflow_result(
        jobs,
        total=100 + len(search),
        has_next=page < 5,
        page=page,
        page_size=page_size,
    )


class PaginationAccessibilityBase(GWFlowJobsPageBase):
    """Shared paginated fixture; contains no tests."""

    gwflow_jobs_side_effect = staticmethod(_paginated_result)

    def _create_fixtures(self):
        for index in range(3):
            GWFlowJob.objects.create(
                sname=f"S23060{index + 1}a",
                user=self.user,
                libraries=["lib1"],
            )

    async def wait_settled(self):
        await self.page.wait_for_function(
            """() => {
                const region = document.getElementById('gwflow-results-region');
                const indicator = document.getElementById('gwflow-loading-indicator');
                return region?.getAttribute('aria-busy') === 'false'
                    && indicator?.hidden === true;
            }"""
        )

    async def assert_connected_non_body_focus(self):
        state = await self.page.evaluate(
            """() => ({
                connected: document.activeElement.isConnected,
                body: document.activeElement === document.body,
            })"""
        )
        self.assertTrue(state["connected"])
        self.assertFalse(state["body"])


class TestPaginationFocusAnnouncementTitle(PaginationAccessibilityBase):
    @async_e2e_test
    async def test_explicit_focus_single_message_title_and_search_preservation(self):
        page = self.page
        await page.wait_for_selector(".pagination-wrap")
        initial_title = await page.title()
        self.assertNotIn("page 1", initial_title.lower())

        writes = await page.evaluate(
            """() => {
                window.__statusWrites = [];
                const status = document.getElementById('gwflow-results-status');
                new MutationObserver(() => {
                    const value = status.textContent.trim();
                    if (value) window.__statusWrites.push(value);
                }).observe(status, {childList: true, characterData: true, subtree: true});
                return window.__statusWrites;
            }"""
        )
        self.assertEqual(writes, [])

        async def delayed_page(route):
            await page.wait_for_timeout(350)
            await route.continue_()

        await page.route("**/gwflow/?*page=2*", delayed_page, times=1)
        page_two = page.locator("a[data-pagination-focus='true'][data-page='2']").first
        await page_two.focus()
        await page_two.press("Enter")
        await page.wait_for_function("() => !document.getElementById('gwflow-loading-indicator').hidden")
        loading = (await page.locator("#gwflow-loading-indicator").inner_text()).strip()
        self.assertIn("Loading page 2", loading)
        await self.wait_settled()

        self.assertEqual(
            await page.evaluate("document.activeElement.id"),
            "gwflow-results-heading",
        )
        await self.assert_connected_non_body_focus()
        self.assertEqual(
            await page.locator("#gwflow-results-status").count(),
            1,
        )
        self.assertEqual(
            await page.locator("#gwflow-job-list [role='status'], #gwflow-job-list [aria-live]").count(),
            0,
        )
        message = (await page.locator("#gwflow-results-status").inner_text()).strip()
        self.assertTrue(message)
        self.assertIn("Page 2 of 5", message)
        final_writes = await page.evaluate("window.__statusWrites")
        self.assertEqual(final_writes, [message])
        self.assertIn("page=2", page.url)
        self.assertIn("page 2", (await page.title()).lower())
        self.assertNotEqual(initial_title, await page.title())

        search = page.locator("#search")
        await search.focus()
        await search.fill("abc")
        await page.wait_for_function(
            "() => location.search.includes('search=abc') && location.search.includes('page=1')"
        )
        await page.wait_for_function(
            "(pageOneTitle) => document.title === pageOneTitle",
            arg=initial_title,
        )
        await self.wait_settled()
        self.assertEqual(await page.evaluate("document.activeElement.id"), "search")
        await self.assert_connected_non_body_focus()
        self.assertEqual(await page.title(), initial_title)
        self.assertNotIn("page 2", (await page.title()).lower())
        await page.unroute_all(behavior="ignoreErrors")


class TestPaginationHistoryFocus(PaginationAccessibilityBase):
    @async_e2e_test
    async def test_back_forward_preserves_survivor_and_repairs_detached_focus_once(self):
        page = self.page
        await page.wait_for_selector(".pagination-wrap")
        search = page.locator("#search")
        await search.focus()

        await page.locator("a[data-page='2']").first.click()
        await self.wait_settled()
        self.assertIn("page=2", page.url)
        await search.focus()
        before_scroll = await page.evaluate("window.scrollY")
        await page.evaluate("history.back()")
        await page.wait_for_function("() => !location.search.includes('page=2')")
        await page.wait_for_function("() => document.activeElement.id === 'search'")
        back_focus = await page.evaluate(
            """() => ({
                id: document.activeElement.id,
                tagName: document.activeElement.tagName,
                connected: document.activeElement.isConnected,
                isBody: document.activeElement === document.body,
            })"""
        )
        print(f"ACTIVE_ELEMENT_AFTER_BACK={back_focus}")
        self.assertEqual(back_focus["id"], "search")
        self.assertEqual(back_focus["tagName"], "INPUT")
        self.assertTrue(back_focus["connected"])
        self.assertFalse(back_focus["isBody"])
        await page.evaluate("history.forward()")
        await page.wait_for_function("() => location.search.includes('page=2')")
        await page.wait_for_timeout(100)
        self.assertEqual(await page.evaluate("document.activeElement.id"), "search")
        self.assertLessEqual(
            abs((await page.evaluate("window.scrollY")) - before_scroll),
            2,
        )

        page_three = page.locator("a[data-page='3']").first
        await page_three.focus()
        await page_three.click()
        await self.wait_settled()
        await page.evaluate(
            """() => {
                window.__headingFocusCalls = 0;
                document.addEventListener('focusin', (event) => {
                    if (event.target?.id === 'gwflow-results-heading') {
                        window.__headingFocusCalls += 1;
                    }
                });
            }"""
        )
        detached = page.locator("a[data-page='5']").first
        self.assertEqual(await detached.count(), 1)
        detached_handle = await detached.element_handle()
        self.assertIsNotNone(detached_handle)
        await detached.focus()
        self.assertEqual(
            await page.evaluate("document.activeElement.getAttribute('data-page')"),
            "5",
        )

        await page.evaluate("history.back()")
        await page.wait_for_function("() => location.search.includes('page=2')")
        await page.wait_for_function("() => document.activeElement.id === 'gwflow-results-heading'")
        self.assertFalse(
            await detached_handle.evaluate("(element) => element.isConnected"),
            "page-5 pagination link must be detached after restoring page 2",
        )
        self.assertEqual(await page.evaluate("window.__headingFocusCalls"), 1)

        await page.evaluate("history.forward()")
        await page.wait_for_function("() => location.search.includes('page=3')")
        await page.wait_for_function("() => document.activeElement.id === 'gwflow-results-heading'")
        await self.assert_connected_non_body_focus()
        self.assertEqual(
            await page.evaluate("document.activeElement.id"),
            "gwflow-results-heading",
        )
        self.assertEqual(
            await page.evaluate("window.__headingFocusCalls"),
            1,
            "detached-focus repair must occur exactly once across Back/Forward",
        )
        self.assertIn("page 3", (await page.title()).lower())


class TestPaginationKeyboardResponsiveAxe(PaginationAccessibilityBase):
    @async_e2e_test
    async def test_keyboard_first_middle_last_reflow_zoom_targets_and_axe(self):
        page = self.page
        await page.wait_for_selector(".pagination-wrap")

        self.assertEqual(await page.locator("a[rel='prev']").count(), 0)
        await page.locator("a[rel='next']").focus()
        await page.locator("a[rel='next']").press("Enter")
        await self.wait_settled()
        self.assertIn("page=2", page.url)
        self.assertEqual(
            await page.locator(".pagination-wrap [aria-current='page']").get_attribute("aria-label"),
            "Page 2, current page",
        )

        await page.goto(f"{self.gwflow_url()}?page=5")
        await page.wait_for_selector(".pagination-wrap")
        self.assertEqual(await page.locator("a[rel='next']").count(), 0)
        self.assertEqual(await page.locator("a[rel='prev']").count(), 1)

        await page.set_viewport_size({"width": 320, "height": 700})
        await page.reload()
        await page.wait_for_selector(".pagination-wrap")
        metrics = await page.evaluate(
            """() => ({
                scrollWidth: document.documentElement.scrollWidth,
                innerWidth: window.innerWidth,
                contextVisible: Array.from(
                    document.querySelectorAll('.pagination__context')
                ).some(el => getComputedStyle(el).display !== 'none'),
                numberedVisible: Array.from(
                    document.querySelectorAll('.pagination__number')
                ).some(el => getComputedStyle(el).display !== 'none'),
            })"""
        )
        self.assertLessEqual(metrics["scrollWidth"], metrics["innerWidth"])
        self.assertTrue(metrics["contextVisible"])
        self.assertFalse(metrics["numberedVisible"])

        controls = await page.evaluate(
            """() => Array.from(
                document.querySelectorAll('.pagination-wrap a[href]')
            ).map(el => {
                const style = getComputedStyle(el);
                const box = el.getBoundingClientRect();
                const rendered = style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && box.width > 0
                    && box.height > 0
                    && el.getClientRects().length > 0;
                return {
                    label: el.getAttribute('aria-label') || el.textContent.trim(),
                    rel: el.getAttribute('rel'),
                    width: box.width,
                    height: box.height,
                    rendered,
                };
            })"""
        )
        rendered_controls = [control for control in controls if control["rendered"]]
        print(f"PAGINATION_CONTROLS_320={controls}")
        self.assertTrue(rendered_controls)
        self.assertEqual(
            {control["rel"] for control in rendered_controls},
            {"prev"},
            "last-page 320px state must expose Previous as the actionable direction",
        )
        for control in rendered_controls:
            self.assertGreaterEqual(
                control["width"],
                24,
                f"{control['label']} width {control['width']}px < 24px",
            )
            self.assertGreaterEqual(
                control["height"],
                24,
                f"{control['label']} height {control['height']}px < 24px",
            )

        await page.goto(self.gwflow_url())
        await page.set_viewport_size({"width": 320, "height": 700})
        await page.wait_for_selector(".pagination-wrap")
        first_controls = await page.evaluate(
            """() => Array.from(
                document.querySelectorAll('.pagination-wrap a[href]')
            ).filter(el => {
                const box = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && box.width > 0
                    && box.height > 0
                    && el.getClientRects().length > 0;
            }).map(el => el.getAttribute('rel'))"""
        )
        self.assertEqual(set(first_controls), {"next"})

        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.reload()
        await page.wait_for_selector(".pagination-wrap")
        await page.evaluate("document.body.style.zoom = '200%'")
        zoom_metrics = await page.evaluate(
            """() => ({
                scrollWidth: document.documentElement.scrollWidth,
                innerWidth: window.innerWidth,
                visibleControls: Array.from(
                    document.querySelectorAll('.pagination-wrap a[href]')
                ).filter(el => {
                    const box = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && box.width > 0
                        && box.height > 0
                        && el.getClientRects().length > 0;
                }).length,
            })"""
        )
        self.assertLessEqual(
            zoom_metrics["scrollWidth"],
            zoom_metrics["innerWidth"],
        )
        self.assertGreaterEqual(zoom_metrics["visibleControls"], 1)

        await load_axe(page)
        violations = await run_axe(page, "#gwflow-results-region")
        blocking = [violation for violation in violations if violation.get("impact") in {"serious", "critical"}]
        self.assertEqual([], blocking, str(blocking))
