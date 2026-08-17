from unittest import mock

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.contrib.auth import get_user_model
from graphql_relay.node.node import to_global_id

from bilbyui.models import BilbyJob, EventID, GWFlowFile, GWFlowJob
from bilbyui.schema import BilbyJobNode, GWFlowJobNode, PublicBilbyJobFilter, UserBilbyJobFilter
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.types import GWFlowFileType

User = get_user_model()


class TestGWFlowQueries(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate()
        self.normal_user = self.user
        self.ligo_user = self.create_user(
            id=10,
            name="ligo user",
            primary_email="ligo@ligo.org",
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.ingest_user = self.create_user(
            id=99,
            name="ingest user",
            primary_email="ingest@gwflow.org",
        )

        self.event_id = EventID.objects.create(trigger_id="S230601ag")

        # Public GWFlowJob
        self.job_public = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.ingest_user,
            schema_version="v1",
            libraries=["cbc-workflow-o4a"],
            ligo_only=False,
            is_pruned=False,
            event_id=self.event_id,
        )
        self.file_public = GWFlowFile.objects.create(
            job=self.job_public,
            analysis_uid="c01:bilby",
            path="outdir/result.json",
            file_name="result.json",
            file_size=1024,
            uploaded=True,
        )

        # LIGO-only GWFlowJob
        self.job_ligo = GWFlowJob.objects.create(
            sname="S230601ah",
            user=self.ingest_user,
            schema_version="v1",
            libraries=["cbc-workflow-o4a"],
            ligo_only=True,
            is_pruned=False,
        )

        # Pruned GWFlowJob
        self.job_pruned = GWFlowJob.objects.create(
            sname="S230601ai",
            user=self.ingest_user,
            schema_version="v1",
            libraries=["cbc-workflow-o4a"],
            ligo_only=False,
            is_pruned=True,
        )

    def _auth_as(self, user):
        if user is None:
            self.deauthenticate()
        else:
            self.authenticate(user=user)

    def test_gwflow_job_by_sname_visibility(self):
        query = """
            query GetBySname($sname: String!) {
                gwflowJobBySname(sname: $sname) {
                    id
                    sname
                    schemaVersion
                    libraries
                    isPruned
                    ligoOnly
                    files {
                        id
                        analysisUid
                        path
                        fileName
                        fileSize
                        uploaded
                        downloadToken
                    }
                }
            }
        """

        # 1. Anonymous user: sees public job, cannot see ligo_only or pruned
        self._auth_as(None)
        res = self.query(query, variables={"sname": "S230601ag"})
        self.assertResponseNoErrors(res)
        job_data = res.data["gwflowJobBySname"]
        self.assertIsNotNone(job_data)
        self.assertEqual(job_data["sname"], "S230601ag")
        self.assertEqual(job_data["schemaVersion"], "v1")
        self.assertEqual(len(job_data["files"]), 1)
        self.assertEqual(job_data["files"][0]["fileName"], "result.json")

        res_ligo = self.query(query, variables={"sname": "S230601ah"})
        self.assertResponseNoErrors(res_ligo)
        self.assertIsNone(res_ligo.data["gwflowJobBySname"])

        res_pruned = self.query(query, variables={"sname": "S230601ai"})
        self.assertResponseNoErrors(res_pruned)
        self.assertIsNone(res_pruned.data["gwflowJobBySname"])

        # 2. Non-LIGO user: sees public job, cannot see ligo_only or pruned
        self._auth_as(self.normal_user)
        res_ligo = self.query(query, variables={"sname": "S230601ah"})
        self.assertResponseNoErrors(res_ligo)
        self.assertIsNone(res_ligo.data["gwflowJobBySname"])

        # 3. LIGO user: sees ligo_only job
        self._auth_as(self.ligo_user)
        res_ligo = self.query(query, variables={"sname": "S230601ah"})
        self.assertResponseNoErrors(res_ligo)
        self.assertIsNotNone(res_ligo.data["gwflowJobBySname"])
        self.assertEqual(res_ligo.data["gwflowJobBySname"]["sname"], "S230601ah")

    def test_gwflow_job_node_query_visibility(self):
        query = """
            query GetNode($id: ID!) {
                gwflowJob(id: $id) {
                    id
                    sname
                    ligoOnly
                }
            }
        """
        node_id_ligo = to_global_id("GWFlowJob", self.job_ligo.id)

        # Non-LIGO user cannot retrieve ligo_only node
        self._auth_as(self.normal_user)
        res = self.query(query, variables={"id": node_id_ligo})
        self.assertResponseNoErrors(res)
        self.assertIsNone(res.data["gwflowJob"])

        # LIGO user can retrieve ligo_only node
        self._auth_as(self.ligo_user)
        res = self.query(query, variables={"id": node_id_ligo})
        self.assertResponseNoErrors(res)
        self.assertIsNotNone(res.data["gwflowJob"])
        self.assertEqual(res.data["gwflowJob"]["sname"], "S230601ah")

    @mock.patch("bilbyui.schema.list_gwflow_jobs")
    def test_gwflow_jobs_connection(self, mock_list_jobs):
        query = """
            query GetJobs($search: String, $timeRange: String, $includePruned: Boolean, $first: Int) {
                gwflowJobs(search: $search, timeRange: $timeRange, includePruned: $includePruned, first: $first) {
                    edges {
                        node {
                            id
                            sname
                        }
                    }
                }
            }
        """
        mock_list_jobs.return_value = {
            "jobs": {self.job_public.id: self.job_public},
            "records": [{"_id": str(self.job_public.id)}],
            "has_next": False,
            "page": 1,
            "page_size": 20,
        }

        self._auth_as(self.normal_user)
        res = self.query(query, variables={"search": "S230601ag", "first": 20})
        self.assertResponseNoErrors(res)

        mock_list_jobs.assert_called_once_with(
            self.normal_user,
            search="S230601ag",
            time_range="all",
            page_size=20,
            offset=0,
            include_pruned=False,
        )
        edges = res.data["gwflowJobs"]["edges"]
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["node"]["sname"], "S230601ag")

    @mock.patch("bilbyui.schema.list_gwflow_jobs")
    def test_gwflow_jobs_connection_first_null(self, mock_list_jobs):
        # An explicit `first: null` connection argument should fall back to the default
        # page size instead of raising a TypeError (500).
        query = """
            query {
                gwflowJobs(first: null) {
                    edges {
                        node {
                            id
                            sname
                        }
                    }
                }
            }
        """
        mock_list_jobs.return_value = {
            "jobs": {self.job_public.id: self.job_public},
            "records": [{"_id": str(self.job_public.id)}],
            "has_next": False,
            "page": 1,
            "page_size": 20,
        }

        self._auth_as(self.normal_user)
        res = self.query(query)
        self.assertResponseNoErrors(res)

        mock_list_jobs.assert_called_once_with(
            self.normal_user,
            search="",
            time_range="all",
            page_size=20,
            offset=0,
            include_pruned=False,
        )

    @mock.patch("elasticsearch.Elasticsearch")
    def test_gwflow_jobs_connection_files_no_nplus1(self, mock_es_cls):
        """
        gwflowJobs connection querying files should not issue one query per node (N+1).
        """
        jobs = [self.job_public]
        for i in range(2):
            job = GWFlowJob.objects.create(
                sname=f"S230601b{i}",
                user=self.ingest_user,
                schema_version="v1",
                libraries=["cbc-workflow-o4a"],
                ligo_only=False,
                is_pruned=False,
            )
            GWFlowFile.objects.create(
                job=job,
                analysis_uid="c01:bilby",
                path=f"outdir/result{i}.json",
                file_name=f"result{i}.json",
                file_size=1024,
                uploaded=True,
            )
            jobs.append(job)

        mock_client = mock.MagicMock()
        mock_es_cls.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "hits": [{"_id": job.id} for job in jobs],
            }
        }

        query = """
            query {
                gwflowJobs(first: 20) {
                    edges {
                        node {
                            sname
                            files {
                                fileName
                            }
                        }
                    }
                }
            }
        """

        self._auth_as(self.normal_user)
        with self.assertNumQueries(6):
            res = self.query(query)
        self.assertResponseNoErrors(res)
        self.assertEqual(len(res.data["gwflowJobs"]["edges"]), 3)

    @mock.patch("bilbyui.schema.request_job_filter", return_value=(True, []))
    def test_bilby_job_node_gwflow_additions(self, mock_req_filter):
        # Create a BilbyJob linked to GWFlowJob
        linked_job = BilbyJob.objects.create(
            user=self.normal_user,
            name="Test Linked Bilby Job",
            gwflow_job=self.job_public,
            gwflow_analysis_uid="c01:bilby",
        )
        # Create an unlinked BilbyJob
        unlinked_job = BilbyJob.objects.create(
            user=self.normal_user,
            name="Test Unlinked Bilby Job",
        )

        query = """
            query GetBilbyJob($id: ID!) {
                bilbyJob(id: $id) {
                    id
                    name
                    gwflowAnalysisUid
                    gwflowJob {
                        id
                        sname
                    }
                }
            }
        """

        self._auth_as(self.normal_user)

        # 1. Linked job
        linked_id = to_global_id("BilbyJobNode", linked_job.id)
        res = self.query(query, variables={"id": linked_id})
        self.assertResponseNoErrors(res)
        job_data = res.data["bilbyJob"]
        self.assertEqual(job_data["gwflowAnalysisUid"], "c01:bilby")
        self.assertIsNotNone(job_data["gwflowJob"])
        self.assertEqual(job_data["gwflowJob"]["sname"], "S230601ag")

        # 2. Unlinked job
        unlinked_id = to_global_id("BilbyJobNode", unlinked_job.id)
        res_unlinked = self.query(query, variables={"id": unlinked_id})
        self.assertResponseNoErrors(res_unlinked)
        unlinked_data = res_unlinked.data["bilbyJob"]
        self.assertIsNone(unlinked_data["gwflowAnalysisUid"])
        self.assertIsNone(unlinked_data["gwflowJob"])

    @mock.patch("bilbyui.schema.request_job_filter", return_value=(True, []))
    def test_bilby_job_node_gwflow_job_visibility(self, mock_req_filter):
        # Bilby job linked to LIGO-only GWFlowJob
        ligo_linked_job = BilbyJob.objects.create(
            user=self.ligo_user,
            name="LIGO Linked Job",
            gwflow_job=self.job_ligo,
            gwflow_analysis_uid="c01:bilby_ligo",
            private=False,
            is_ligo_job=False,
        )
        query = """
            query GetBilbyJob($id: ID!) {
                bilbyJob(id: $id) {
                    id
                    gwflowJob {
                        sname
                    }
                }
            }
        """
        job_id = to_global_id("BilbyJobNode", ligo_linked_job.id)

        # Non-LIGO user sees BilbyJob, but gwflowJob resolves to None
        self._auth_as(self.normal_user)
        res = self.query(query, variables={"id": job_id})
        self.assertResponseNoErrors(res)
        self.assertIsNone(res.data["bilbyJob"]["gwflowJob"])

        # LIGO user sees gwflowJob
        self._auth_as(self.ligo_user)
        res_ligo = self.query(query, variables={"id": job_id})
        self.assertResponseNoErrors(res_ligo)
        self.assertIsNotNone(res_ligo.data["bilbyJob"]["gwflowJob"])
        self.assertEqual(res_ligo.data["bilbyJob"]["gwflowJob"]["sname"], "S230601ah")

    def test_filter_qs_properties(self):
        class DummyRequest:
            def __init__(self, user):
                self.user = user

        req_normal = DummyRequest(self.normal_user)
        user_filter = UserBilbyJobFilter(request=req_normal)
        self.assertIsNotNone(user_filter.qs)

        public_filter = PublicBilbyJobFilter(request=req_normal)
        self.assertIsNotNone(public_filter.qs)

    def test_gwflow_file_type_resolvers_edge_cases(self):
        file_type = GWFlowFileType()
        info = mock.Mock()

        # Dict input with integer id and uuid token
        dict_file = {"id": 42, "download_token": "123e4567-e89b-12d3-a456-426614174000"}
        res_id = (
            file_type.resolve_id(info)
            if not hasattr(GWFlowFileType, "resolve_id")
            else GWFlowFileType.resolve_id(dict_file, info)
        )
        self.assertEqual(res_id, to_global_id("GWFlowFileNode", 42))

        res_token = GWFlowFileType.resolve_download_token(dict_file, info)
        self.assertEqual(res_token, "123e4567-e89b-12d3-a456-426614174000")

        # Dict input with None id and None token
        dict_none = {"id": None, "download_token": None}
        self.assertIsNone(GWFlowFileType.resolve_id(dict_none, info))
        self.assertIsNone(GWFlowFileType.resolve_download_token(dict_none, info))

        # Dict input without keys
        dict_empty = {}
        self.assertIsNone(GWFlowFileType.resolve_id(dict_empty, info))
        self.assertIsNone(GWFlowFileType.resolve_download_token(dict_empty, info))

    def test_gwflow_job_node_resolvers_edge_cases(self):
        info = mock.Mock()

        class BadUserJob:
            @property
            def user(self):
                raise AttributeError("No user name")

            last_updated = None

        bad_job = BadUserJob()
        self.assertEqual(GWFlowJobNode.resolve_user(bad_job, info), "Unknown User")
        self.assertIsNone(GWFlowJobNode.resolve_last_updated(bad_job, info))
        self.assertEqual(BilbyJobNode.resolve_user(bad_job, info), "Unknown User")
        self.assertIsNone(BilbyJobNode.resolve_last_updated(bad_job, info))

    @mock.patch("bilbyui.schema.list_gwflow_jobs")
    def test_gwflow_jobs_connection_empty_and_cursor(self, mock_list_jobs):
        query = """
            query GetJobs($first: Int, $after: String) {
                gwflowJobs(first: $first, after: $after) {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """

        # 1. Empty records returned from service
        mock_list_jobs.return_value = {
            "jobs": {},
            "records": [],
            "has_next": False,
            "page": 1,
            "page_size": 20,
        }

        self._auth_as(self.normal_user)
        res = self.query(query, variables={"first": 20})
        self.assertResponseNoErrors(res)
        self.assertEqual(res.data["gwflowJobs"]["edges"], [])

        # 2. Query with cursor 'after'
        mock_list_jobs.return_value = {
            "jobs": {self.job_public.id: self.job_public},
            "records": [{"_id": str(self.job_public.id)}],
            "has_next": False,
            "page": 1,
            "page_size": 20,
        }
        cursor_0 = to_global_id("arrayconnection", 0)
        res_cursor = self.query(query, variables={"first": 20, "after": cursor_0})
        self.assertResponseNoErrors(res_cursor)
        self.assertEqual(len(res_cursor.data["gwflowJobs"]["edges"]), 1)

    @mock.patch("bilbyui.schema.list_gwflow_jobs")
    def test_gwflow_jobs_connection_malformed_cursor(self, mock_list_jobs):
        query = """
            query GetJobs($first: Int, $after: String) {
                gwflowJobs(first: $first, after: $after) {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        """
        mock_list_jobs.return_value = {
            "jobs": {self.job_public.id: self.job_public},
            "records": [{"_id": str(self.job_public.id)}],
            "has_next": False,
            "page": 1,
            "page_size": 20,
        }

        self._auth_as(self.normal_user)

        # A malformed cursor (invalid base64 or a non-numeric id) should fall back to the first page
        # instead of raising a ValueError and returning a 500.
        for malformed_cursor in ["YXJyYXljb25uZWN0aW9uOmFiYw==", "bm90aGluZw==", "not-base64!!"]:
            res = self.query(query, variables={"first": 20, "after": malformed_cursor})
            self.assertResponseNoErrors(res)
            edges = res.data["gwflowJobs"]["edges"]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0]["node"]["id"], to_global_id("GWFlowJob", self.job_public.id))

        mock_list_jobs.assert_called_with(
            self.normal_user,
            search="",
            time_range="all",
            page_size=20,
            offset=0,
            include_pruned=False,
        )
