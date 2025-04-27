from django.test import override_settings
from playwright.sync_api import expect
from .react_test_case import ReactPlaywrightTestCase
from unittest import mock
from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import (
    create_test_ini_string,
    generate_elastic_doc,
)
from bilbyui.tests.testcases import BilbyTestCase
from adacs_sso_plugin.adacs_user import ADACSUser
from django.contrib.auth import get_user_model
User = get_user_model()

def elasticsearch_search_mock(*args, **kwargs):
    user = {"name": "buffy summers", "id": 1}

    jobs = []
    for job in BilbyJob.objects.filter(user_id=user["id"]):
        doc = {"_source": generate_elastic_doc(job, user), "_id": job.id}
        jobs.append(doc)

    return {"hits": {"hits": jobs}}

def elasticsearch_search_mock_no_hits(*args, **kwargs):
    return {"hits": {}}

def request_lookup_users_mock(*args, **kwargs):
    user = User.objects.first()
    if user:
        return True, [{"id": user.id, "name": "buffy summers"}]
    return False, []

def request_job_filter_mock(*args, **kwargs):
        jobs = []
        for job in BilbyJob.objects.filter(user_id=1):
            jobs.append(
                {
                    "id": job.job_controller_id,
                    "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}],
                }
            )

        return True, jobs

@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestReactFrontend(ReactPlaywrightTestCase):
    """
    Test cases for the React frontend.
    """
    def setUp(self):
        self.user = ADACSUser(**BilbyTestCase.DEFAULT_USER)

        self.job1 = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            job_controller_id=2345,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    @mock.patch("bilbyui.utils.auth.lookup_users.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.schema.request_job_filter", side_effect=request_job_filter_mock)
    def test_homepage_loads(self,lookup, search, filter):
        """Test that the homepage loads correctly."""
        page = self.browser.new_page()

        try:
                    
            page.on("request", lambda request: print(">>", request.method, request.url, request.post_data) if request.url == "http://localhost:8000/graphql" else None)
            page.on("response", lambda response: print("<<", response.status, response.url, response.text()) if response.url == "http://localhost:8000/graphql" else None)
            page.on("console", lambda msg: print(f"console[{msg.type}] {msg.text}"))
            # Navigate to the React frontend
            print(f"Navigating to {self.react_url}")
            print(f"Backend at {self.live_server_url}")
            page.goto(self.react_url)
            
            print("waiting")
            page.wait_for_timeout(10000)
            print("done")

            # Take a screenshot for debugging
            page.screenshot(path="homepage.png")

            # Test that the page loads correctly
            # Note: Update the expected title to match your actual app title
            expect(page).to_have_title("GW Cloud")

        finally:
            # Always close the page to clean up
            page.close()

    # def test_graphiql_loads(self):
    #     page = self.browser.new_page()
    #     try:
    #         page.on("request", lambda request: print(">>", request.method, request.url, request.post_data))
    #         page.on("response", lambda response: print("<<", response.status, response.url))
    #         page.goto(f"{self.live_server_url}/graphql")
    #         page.wait_for_load_state()
    #         page.screenshot(path="graphql.png")
    #     finally:
    #         # Always close the page to clean up
    #         page.close()