from datetime import datetime, timedelta
from unittest import mock

from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from bilbyui.models import BilbyJob, EventID
from bilbyui.tests.test_utils import create_test_ini_string, generate_elastic_doc
from bilbyui.tests.testcases import BilbyTestCase


def _bool_query(query):
    if not isinstance(query, dict):
        return {}
    bool_query = query.get("bool", {})
    return bool_query if isinstance(bool_query, dict) else {}


def _extract_search_term(query):
    for clause in _bool_query(query).get("must", []):
        if "match_all" in clause:
            continue
        query_string = clause.get("query_string")
        if isinstance(query_string, dict):
            term = query_string.get("query")
            if isinstance(term, str) and term:
                return term
    return None


def _structured_filters(query):
    filters = _bool_query(query).get("filter", [])
    return filters if isinstance(filters, list) else [filters]


def _job_matches_time_range(job, query):
    for clause in _structured_filters(query):
        bounds = clause.get("range", {}).get("job.creationTime")
        if not isinstance(bounds, dict):
            continue

        start = datetime.fromisoformat(bounds["gte"])
        end = datetime.fromisoformat(bounds["lte"])
        created = job.creation_time
        if timezone.is_naive(created):
            created = timezone.make_aware(created)
        return start <= created <= end

    return True


def _visibility_clause(query):
    for clause in _structured_filters(query):
        should = clause.get("bool", {}).get("should", [])
        if any(
            "searchTriggerTime" in candidate.get("range", {})
            or candidate.get("bool", {}).get("must_not", {}).get("exists", {}).get("field") == "searchTriggerTime"
            for candidate in should
        ):
            return clause
    return None


def _job_matches_embargo_filter(doc, query):
    clause = _visibility_clause(query)
    if clause is None:
        return True

    should = clause["bool"]["should"]
    threshold = next(
        candidate["range"]["searchTriggerTime"]["lt"]
        for candidate in should
        if "searchTriggerTime" in candidate.get("range", {})
    )
    simulated = doc.get("ini", {}).get("n_simulation", 0)

    return simulated > 0 or "searchTriggerTime" not in doc or doc["searchTriggerTime"] < threshold


def elasticsearch_search_mock(*args, **kwargs):
    user = {"name": "buffy summers", "id": 1}
    from_ = kwargs.get("from_", 0)
    size = kwargs.get("size", 21)
    query = kwargs.get("query")
    search_term = _extract_search_term(query)

    jobs = []
    queryset = (
        BilbyJob.objects.filter(private=False)
        .select_related("event_id", "gwflow_job__event_id")
        .order_by("-last_updated", "-id")
    )
    for job in queryset:
        doc = generate_elastic_doc(job, user)
        if not _job_matches_embargo_filter(doc, query):
            continue
        if not _job_matches_time_range(job, query):
            continue
        if search_term and search_term not in job.name and search_term not in (job.description or ""):
            continue

        jobs.append({"_source": doc, "_id": job.id})

    page = jobs[from_ : from_ + size]
    return {"hits": {"total": {"value": len(jobs)}, "hits": page}}


def elasticsearch_search_mock_no_hits(*args, **kwargs):
    return {"hits": {"hits": []}}


def request_job_filter_mock(*args, **kwargs):
    requested_ids = set(kwargs.get("ids", []))
    jobs = [
        {
            "id": job.job_controller_id,
            "history": [{"state": 500, "timestamp": "2020-01-01 12:00:00 UTC"}],
        }
        for job in BilbyJob.objects.filter(job_controller_id__in=requested_ids)
    ]

    return "OK", jobs


class TestPublicJobsView(BilbyTestCase):
    url = "/"

    def setUp(self):
        self.deauthenticate()

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_renders_empty_list(self, elasticsearch_search):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create a new job or try searching 'Any time'.")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_renders_list_with_data(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        for index in range(25):
            BilbyJob.objects.create(
                user_id=self.user.id,
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
        self.assertContains(response, 'aria-label="Public Jobs pagination"')
        self.assertContains(response, "page=2")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_full_page_title_includes_page_number_when_greater_than_one(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        for index in range(25):
            BilbyJob.objects.create(
                user_id=self.user.id,
                name=f"Job {index}",
                description=f"Description {index}",
                job_controller_id=1600 + index,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']", "label": f"Job {index}"}),
            )

        response = self.client.get(self.url, {"page": 2})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<title>Public Jobs — page 2 — GWCloud</title>")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_fragment_title_renders_page_number_and_prefix(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        for index in range(25):
            BilbyJob.objects.create(
                user_id=self.user.id,
                name=f"Job {index}",
                description=f"Description {index}",
                job_controller_id=1700 + index,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']", "label": f"Job {index}"}),
            )

        response = self.client.get(self.url, {"page": 2}, HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-document-title="Public Jobs — page 2 — GWCloud"')

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", return_value=("UNKNOWN", "Error getting job filter"))
    def test_controller_unavailable_renders_unknown(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="Offline job",
            description="controller down",
            job_controller_id=1501,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Offline job"}),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Offline job")
        self.assertContains(response, 'class="badge badge-dark">Unknown</span>')

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch(
        "bilbyui.services.jobs.request_job_filter",
        return_value=("OK", ["malformed", {"id": 999, "history": []}]),
    )
    def test_malformed_controller_entry_does_not_crash(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="Malformed controller job",
            description="should still render",
            job_controller_id=1502,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Malformed controller job"}),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Malformed controller job")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_search_filters(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW150914",
            description="matched event",
            job_controller_id=2001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "GW150914"}),
        )
        BilbyJob.objects.create(
            user_id=self.user.id,
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
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="Recent job",
            description="recent",
            job_controller_id=3001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Recent job"}),
        )
        old_job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Old job",
            description="old",
            job_controller_id=3002,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Old job"}),
        )
        BilbyJob.objects.filter(pk=old_job.pk).update(
            creation_time=timezone.now() - timedelta(days=2),
        )

        response = self.client.get(self.url, {"time_range": "1d"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recent job")
        self.assertNotContains(response, "Old job")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_invalid_time_range_defaults_to_all(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="Invalid range job",
            description="should still render",
            job_controller_id=3201,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Invalid range job"}),
        )

        response = self.client.get(self.url, {"time_range": "invalid"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid range job")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_invalid_page_defaults_to_one(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="Invalid page job",
            description="should still render",
            job_controller_id=3301,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Invalid page job"}),
        )

        response = self.client.get(self.url, {"page": "abc"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid page job")

    @override_settings(EMBARGO_START_TIME=1234.0)
    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_embargo_filter(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="Public job",
            description="allowed",
            job_controller_id=4001,
            private=False,
            trigger_time=1000.0,
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
            user_id=self.user.id,
            name="Embargoed job",
            description="hidden",
            job_controller_id=4002,
            private=False,
            trigger_time=settings.EMBARGO_START_TIME + 1,
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
        self.assertNotContains(response, "Switch to my jobs")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock_no_hits)
    def test_authenticated_user_sees_my_jobs_link(self, elasticsearch_search):
        self.authenticate()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        my_jobs_url = reverse("bilbyui:my_jobs")
        self.assertContains(response, f'href="{my_jobs_url}"')
        self.assertContains(response, "Switch to my jobs")
        self.assertNotContains(response, 'href="#">Switch to my jobs')

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_htmx_request_returns_fragment(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
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
        self.assertContains(response, 'data-document-title="Public Jobs — GWCloud"')
        self.assertNotContains(response, "<h1")

    @mock.patch("elasticsearch.Elasticsearch.search", side_effect=elasticsearch_search_mock)
    @mock.patch("bilbyui.services.jobs.request_job_filter", side_effect=request_job_filter_mock)
    def test_renders_event_id_values(self, request_job_filter, elasticsearch_search):
        self.user = self.create_user()
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        BilbyJob.objects.create(
            user_id=self.user.id,
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
        self.user = self.create_user()
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="No event job",
            description="without event id",
            job_controller_id=5102,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "No event job"}),
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No event IDs")

    def test_query_helper_edge_branches(self):
        match_all_query = {
            "bool": {
                "must": [{"match_all": {}}],
                "filter": [{"term": {"_private_info_.private": False}}],
            }
        }
        search_query = {
            "bool": {
                "must": [{"query_string": {"query": "GW150914"}}],
                "filter": [{"term": {"_private_info_.private": False}}],
            }
        }
        time_query = {
            "bool": {
                "must": [{"match_all": {}}],
                "filter": [
                    {"term": {"_private_info_.private": False}},
                    {
                        "range": {
                            "job.creationTime": {
                                "gte": "2020-01-01T00:00:00+00:00",
                                "lte": "2021-01-01T00:00:00+00:00",
                            }
                        }
                    },
                ],
            }
        }
        visibility_query = {
            "bool": {
                "must": [{"match_all": {}}],
                "filter": [
                    {"term": {"_private_info_.private": False}},
                    {
                        "bool": {
                            "should": [
                                {"range": {"ini.n_simulation": {"gt": 0}}},
                                {"bool": {"must_not": {"exists": {"field": "searchTriggerTime"}}}},
                                {"range": {"searchTriggerTime": {"lt": 1234.0}}},
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                ],
            }
        }

        self.assertIsNone(_extract_search_term(None))
        self.assertIsNone(_extract_search_term(match_all_query))
        self.assertEqual(_extract_search_term(search_query), "GW150914")

        self.user = self.create_user()
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Edge job",
            description="edge",
            job_controller_id=6001,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']", "label": "Edge job"}),
        )
        document = generate_elastic_doc(
            job,
            {"name": "buffy summers", "id": self.user.id},
        )

        self.assertTrue(_job_matches_embargo_filter(document, match_all_query))
        self.assertTrue(_job_matches_embargo_filter(document, visibility_query))

        job.creation_time = datetime(2020, 6, 1)
        self.assertTrue(_job_matches_time_range(job, time_query))
