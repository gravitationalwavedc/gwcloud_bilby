import re
from datetime import datetime, timedelta
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.test_utils import create_test_ini_string, generate_elastic_doc
from bilbyui.tests.testcases import BilbyTestCase


def _extract_search_term(q):
    if not q:
        return None

    if q.startswith("((("):
        match = re.search(r"\(\(\(([^()]+)\)", q)
        if match:
            term = match.group(1).strip()
            if term not in ("*", ""):
                return term
        return None

    match = re.match(r"^\(([^()]+)\)", q)
    if not match:
        return None

    term = match.group(1).strip()
    if term in ("*", ""):
        return None

    if term.startswith("job.creationTime"):
        return None

    return term


def _job_matches_embargo_filter(job, q):
    if "params.trigger_time" not in q:
        return True

    if settings.EMBARGO_START_TIME is None:
        return True

    trigger_kv = job.inikeyvalue_set.filter(key="trigger_time", processed=True).first()
    simulated_kv = job.inikeyvalue_set.filter(key="n_simulation", processed=False).first()

    trigger_time = float(trigger_kv.value) if trigger_kv else None
    simulated = int(simulated_kv.value) if simulated_kv else 0

    if simulated > 0:
        return True

    if trigger_time is None:
        return True

    return trigger_time < settings.EMBARGO_START_TIME


def _job_matches_time_range(job, q):
    match = re.search(r'job\.creationTime:\["([^"]+)" TO "([^"]+)"\]', q)
    if not match:
        return True

    start = datetime.fromisoformat(match.group(1))
    end = datetime.fromisoformat(match.group(2))
    updated = job.last_updated
    if timezone.is_naive(updated):
        updated = timezone.make_aware(updated)

    return start <= updated <= end


def elasticsearch_search_mock(*args, **kwargs):
    user = {"name": "buffy summers", "id": 1}
    from_ = kwargs.get("from_", 0)
    size = kwargs.get("size", 21)
    q = kwargs.get("q", "")

    jobs = []
    for job in BilbyJob.objects.filter(private=False).order_by("-last_updated", "-id"):
        if not _job_matches_embargo_filter(job, q):
            continue
        if not _job_matches_time_range(job, q):
            continue

        search_term = _extract_search_term(q)
        if search_term and search_term not in job.name and search_term not in (job.description or ""):
            continue

        jobs.append({"_source": generate_elastic_doc(job, user), "_id": job.id})

    page = jobs[from_ : from_ + size]
    return {"hits": {"hits": page}}


def elasticsearch_search_mock_no_hits(*args, **kwargs):
    return {"hits": {}}


def request_job_filter_mock(*args, **kwargs):
    requested_ids = set(kwargs.get("ids", []))
    jobs = []
    for job in BilbyJob.objects.filter(job_controller_id__in=requested_ids):
        jobs.append(
            {
                "id": job.job_controller_id,
                "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}],
            }
        )

    return True, jobs


class TestPublicJobsView(BilbyTestCase):
    url = "/"

    def setUp(self):
        self.deauthenticate()

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_renders_empty_list(self, elasticsearch_search):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No jobs")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_renders_list_with_data(self, request_job_filter, elasticsearch_search):
        for index in range(25):
            BilbyJob.objects.create(
                user_id=1,
                name=f"Job {index}",
                description=f"Description {index}",
                job_controller_id=1000 + index,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']", "label": f"Job {index}"}),
            )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Job 24")
        self.assertContains(response, "Job 5")
        self.assertNotContains(response, "Job 4")
        self.assertContains(response, "Loading more")
        self.assertContains(response, "page=2")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_search_filters(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=1,
            name="GW150914",
            description="matched event",
            job_controller_id=2001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "GW150914"}),
        )
        BilbyJob.objects.create(
            user_id=1,
            name="Other job",
            description="unrelated",
            job_controller_id=2002,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Other job"}),
        )

        response = self.client.get(self.url, {"search": "GW150914"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GW150914")
        self.assertNotContains(response, "Other job")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_time_range_filters(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=1,
            name="Recent job",
            description="recent",
            job_controller_id=3001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Recent job"}),
        )
        old_job = BilbyJob.objects.create(
            user_id=1,
            name="Old job",
            description="old",
            job_controller_id=3002,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Old job"}),
        )
        BilbyJob.objects.filter(pk=old_job.pk).update(
            last_updated=timezone.now() - timedelta(days=2),
        )

        response = self.client.get(self.url, {"time_range": "1d"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent job")
        self.assertNotContains(response, "Old job")

    @override_settings(EMBARGO_START_TIME=1234.0)
    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_embargo_filter(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=1,
            name="Public job",
            description="allowed",
            job_controller_id=4001,
            private=False,
            ini_string=create_test_ini_string(
                {
                    "detectors": "['H1']",
                    "label": "Public job",
                    "trigger-time": 1000,
                    "n-simulation": 1,
                }
            ),
        )
        BilbyJob.objects.create(
            user_id=1,
            name="Embargoed job",
            description="hidden",
            job_controller_id=4002,
            private=False,
            ini_string=create_test_ini_string(
                {
                    "detectors": "['H1']",
                    "label": "Embargoed job",
                    "trigger-time": settings.EMBARGO_START_TIME + 1,
                    "n-simulation": 0,
                    "gaussian-noise": False,
                }
            ),
        )

        self.authenticate()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public job")
        self.assertNotContains(response, "Embargoed job")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_unauthenticated_anonymous(self, elasticsearch_search):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "My Jobs")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_authenticated_user_sees_my_jobs_link(self, elasticsearch_search):
        self.authenticate()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        my_jobs_url = reverse("bilbyui:my_jobs")
        self.assertContains(response, f'href="{my_jobs_url}"')
        self.assertContains(response, "My Jobs")
        self.assertNotContains(response, 'href="#">My Jobs')

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_htmx_request_returns_fragment(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=1,
            name="Fragment job",
            description="fragment",
            job_controller_id=5001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Fragment job"}),
        )

        response = self.client.get(
            self.url,
            {"page": 1},
            HTTP_HX_REQUEST="true",
            HTTP_HX_TARGET="job-list",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<!doctype html>", status_code=200)
        self.assertContains(response, "Fragment job")
        self.assertNotContains(response, "Public Jobs")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_renders_event_id_values(self, request_job_filter, elasticsearch_search):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        BilbyJob.objects.create(
            user_id=1,
            name="Event job",
            description="with event id",
            job_controller_id=5101,
            private=False,
            event_id=event_id,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Event job"}),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GW123456_123456")
        self.assertContains(response, "S123456a")
        self.assertContains(response, "GW123456")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_renders_no_event_ids_when_missing(self, request_job_filter, elasticsearch_search):
        BilbyJob.objects.create(
            user_id=1,
            name="No event job",
            description="without event id",
            job_controller_id=5102,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "No event job"}),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No event ids")
