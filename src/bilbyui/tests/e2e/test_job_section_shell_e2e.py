"""Browser coverage for the Bilby job section lifecycle."""

from unittest import mock

from asgiref.sync import sync_to_async
from django.test import override_settings
from django.urls import reverse

from bilbyui.models import BilbyJob
from bilbyui.tests.e2e.utils import AsyncE2ETestCase, async_e2e_test
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class JobSectionShellBase(AsyncE2ETestCase):
    """Authenticated Bilby job page with deterministic backend responses."""

    user = None
    job = None
    page = None
    _patchers = ()

    async def asetUp(self):
        self.user = await sync_to_async(self._create_user)()
        self.job = await sync_to_async(BilbyJob.objects.create)(
            user_id=self.user.id,
            name="e2e section job",
            description="e2e",
            private=False,
            job_controller_id=10001,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "e2e section job"}),
        )
        await self.login(self.user)

        self._patchers = (
            mock.patch(
                "bilbyui.views.request_job_filter",
                return_value=(
                    "OK",
                    [
                        {
                            "id": self.job.job_controller_id,
                            "history": [
                                {
                                    "state": 500,
                                    "timestamp": "2020-01-01 12:00:00 UTC",
                                }
                            ],
                        }
                    ],
                ),
            ),
            mock.patch.object(BilbyJob, "get_file_list", return_value=(True, [])),
        )
        for patcher in self._patchers:
            patcher.start()
        self.addCleanup(self._stop_patchers)

        self.page = await self.browser_context.new_page()

    async def aTearDown(self):
        if self.page is not None:
            await self.page.close()
            self.page = None

    def _stop_patchers(self):
        for patcher in self._patchers:
            patcher.stop()

    def _create_user(self):
        return BilbyTestCase.create_user(
            name="e2e job sections",
            primary_email="e2e-job-sections@example.com",
        )

    @property
    def parameters_url(self):
        path = reverse(
            "bilbyui:view_job_parameters_section",
            kwargs={"job_id": self.job.id},
        )
        return f"{self.live_server_url}{path}"

    @property
    def results_url(self):
        path = reverse(
            "bilbyui:view_job_results_section",
            kwargs={"job_id": self.job.id},
        )
        return f"{self.live_server_url}{path}"


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestJobSectionShellLifecycle(JobSectionShellBase):
    @async_e2e_test
    async def test_section_navigation_and_back(self):
        page = self.page
        await page.goto(self.parameters_url)

        heading = page.locator("#job-section-heading")
        parameters_link = page.locator('a[data-job-section][href*="/parameters/"]')
        results_link = page.locator('a[data-job-section][href*="/results/"]')

        self.assertEqual((await heading.text_content()).strip(), "Parameters")

        await results_link.click()
        await page.wait_for_url("**/results/")
        await page.wait_for_function(
            "document.getElementById('job-section-heading') && "
            "document.getElementById('job-section-heading').textContent.trim() "
            "=== 'Results'"
        )

        self.assertEqual((await heading.text_content()).strip(), "Results")
        self.assertEqual(await results_link.get_attribute("aria-current"), "page")
        self.assertIsNone(await parameters_link.get_attribute("aria-current"))

        await page.go_back()
        await page.wait_for_url("**/parameters/")
        await page.wait_for_function(
            "document.getElementById('job-section-heading') && "
            "document.getElementById('job-section-heading').textContent.trim() "
            "=== 'Parameters'"
        )

        self.assertEqual((await heading.text_content()).strip(), "Parameters")
        self.assertEqual(
            await parameters_link.get_attribute("aria-current"),
            "page",
        )
        self.assertIsNone(await results_link.get_attribute("aria-current"))


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestJobSectionKeyboardFocus(JobSectionShellBase):
    @async_e2e_test
    async def test_enter_navigation_focuses_heading(self):
        page = self.page
        await page.goto(self.parameters_url)

        results_link = page.locator('a[data-job-section][href*="/results/"]')
        await results_link.focus()
        await page.keyboard.press("Enter")
        await page.wait_for_url("**/results/")
        await page.wait_for_function("document.activeElement && document.activeElement.id === 'job-section-heading'")

        self.assertEqual(
            await page.evaluate("document.activeElement.id"),
            "job-section-heading",
        )
