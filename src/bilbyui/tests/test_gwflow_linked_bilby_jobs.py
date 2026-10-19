from unittest import mock

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from graphql_relay.node.node import to_global_id

from bilbyui.models import BilbyJob, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import get_gwflow_linked_bilby_jobs

QUERY = """
query Linked($sname: String!) {
  gwflowLinkedBilbyJobs(sname: $sname) {
    id
    gwflowAnalysisUid
  }
}
"""


class TestGWFlowLinkedBilbyJobs(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.normal_user = self.create_user(id=2, name="normal user")
        self.ingest_user = self.create_user(
            id=99,
            name="ingest user",
            primary_email="ingest@gwflow.org",
        )
        self.other_user = self.create_user(id=3, name="other user")
        self.parent = GWFlowJob.objects.create(
            sname="S230601linked",
            user=self.ingest_user,
        )

    def _auth_as(self, user):
        if user is None:
            self.deauthenticate()
        else:
            self.authenticate(user=user)

    def _child(self, uid, *, parent=None, user=None, private=False):
        return BilbyJob.objects.create(
            user=user or self.other_user,
            name=f"job-{uid}-{BilbyJob.objects.count()}",
            ini_string="",
            private=private,
            gwflow_job=parent or self.parent,
            gwflow_analysis_uid=uid,
        )

    def _query(self, sname):
        return self.query(QUERY, variables={"sname": sname})

    def test_sl1_permission_matrix_is_independent_of_sname_existence(self):
        for sname in (self.parent.sname, "S230601missing"):
            with self.subTest(sname=sname, actor="anonymous"):
                self._auth_as(None)
                response = self._query(sname)
                self.assertIsNotNone(response.errors)
                self.assertTrue(
                    any(
                        "Permission Denied" in error["message"] or "do not have permission" in error["message"]
                        for error in response.errors
                    )
                )

            with self.subTest(sname=sname, actor="non-ingest"):
                self._auth_as(self.normal_user)
                with override_settings(GWFLOW_INGEST_USER=99):
                    response = self._query(sname)
                self.assertIsNotNone(response.errors)
                self.assertIn("Permission Denied", response.errors[0]["message"])

            with self.subTest(sname=sname, actor="unset"):
                self._auth_as(self.ingest_user)
                with override_settings(GWFLOW_INGEST_USER=None):
                    response = self._query(sname)
                self.assertIsNotNone(response.errors)
                self.assertIn("Permission Denied", response.errors[0]["message"])

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_sl2_lookup_is_select_only_and_has_no_side_effects(self):
        self._child("pe-read-only")
        with (
            mock.patch("bilbyui.views.reindex_jobs") as reindex,
            mock.patch("bilbyui.views.gwflow_elastic_search_update") as es_update,
            mock.patch("bilbyui.views.cache.delete") as cache_delete,
            CaptureQueriesContext(connection) as captured,
        ):
            result = get_gwflow_linked_bilby_jobs(
                self.ingest_user,
                self.parent.sname,
            )

        self.assertEqual(len(result), 1)
        bilby_statements = [query["sql"] for query in captured.captured_queries if "bilbyui_" in query["sql"].lower()]
        self.assertTrue(bilby_statements)
        self.assertTrue(
            all(statement.lstrip().upper().startswith("SELECT") for statement in bilby_statements),
            bilby_statements,
        )
        reindex.assert_not_called()
        es_update.assert_not_called()
        cache_delete.assert_not_called()

    @override_settings(GWFLOW_INGEST_USER=99, EMBARGO_START_TIME=1500.0)
    def test_sl3_unscoped_correctness_unknown_and_ordering(self):
        private = self._child("beta", private=True)
        first_alpha = self._child("alpha")
        second_alpha = self._child("alpha")
        blank = self._child("")
        other_parent = GWFlowJob.objects.create(
            sname="S230601other",
            user=self.ingest_user,
        )
        other = self._child("aardvark", parent=other_parent)

        expected_jobs = sorted(
            (private, first_alpha, second_alpha),
            key=lambda job: (job.gwflow_analysis_uid, job.id),
        )
        expected = [
            {
                "id": to_global_id("BilbyJobNode", job.id),
                "gwflow_analysis_uid": job.gwflow_analysis_uid,
            }
            for job in expected_jobs
        ]

        result = get_gwflow_linked_bilby_jobs(
            self.ingest_user,
            self.parent.sname,
        )
        self.assertEqual(result, expected)
        self.assertIn(to_global_id("BilbyJobNode", private.id), {row["id"] for row in result})

        self.parent.is_pruned = True
        self.parent.save(update_fields=["is_pruned"])
        self.assertEqual(
            get_gwflow_linked_bilby_jobs(self.ingest_user, self.parent.sname),
            expected,
        )

        self.parent.is_pruned = False
        self.parent.trigger_time = 2000.0
        self.parent.save(update_fields=["is_pruned", "trigger_time"])
        self.assertEqual(
            get_gwflow_linked_bilby_jobs(self.ingest_user, self.parent.sname),
            expected,
        )

        returned_ids = {row["id"] for row in result}
        self.assertNotIn(to_global_id("BilbyJobNode", blank.id), returned_ids)
        self.assertNotIn(to_global_id("BilbyJobNode", other.id), returned_ids)
        self.assertEqual(
            get_gwflow_linked_bilby_jobs(self.ingest_user, "S230601unknown"),
            [],
        )

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_sl4_query_count_is_constant_for_zero_one_and_five_children(self):
        for count in (0, 1, 5):
            parent = GWFlowJob.objects.create(
                sname=f"S23060{count}bound",
                user=self.ingest_user,
            )
            for index in range(count):
                self._child(f"pe-{index}", parent=parent)
            with self.subTest(count=count), self.assertNumQueries(1):
                result = get_gwflow_linked_bilby_jobs(
                    self.ingest_user,
                    parent.sname,
                )
                self.assertEqual(len(result), count)

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_sl5_protected_manifest_equal_after_one_and_several_calls(self):
        from bilbyui.models import ExternalBilbyJob
        from bilbyui.tests.gwflow_manifests import (
            assert_preserved,
            protected_identity_manifest,
        )

        private = self._child("pe-private-preserved", private=True)
        ExternalBilbyJob.objects.create(job=private)
        self.parent.is_pruned = True
        self.parent.save(update_fields=["is_pruned"])
        before = protected_identity_manifest()

        get_gwflow_linked_bilby_jobs(
            self.ingest_user,
            self.parent.sname,
        )
        after_one = protected_identity_manifest()
        assert_preserved(before, after_one)

        for _ in range(4):
            result = get_gwflow_linked_bilby_jobs(
                self.ingest_user,
                self.parent.sname,
            )

        assert_preserved(before, protected_identity_manifest())
        self.assertEqual(
            result,
            [
                {
                    "id": to_global_id("BilbyJobNode", private.pk),
                    "gwflow_analysis_uid": "pe-private-preserved",
                }
            ],
        )

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_sl6_schema_contract_and_name_rejected(self):
        self._auth_as(self.ingest_user)
        response = self.query(
            """
            query {
              __type(name: "GWFlowLinkedBilbyJob") {
                fields { name }
              }
            }
            """
        )
        self.assertResponseNoErrors(response)
        self.assertEqual(
            {field["name"] for field in response.data["__type"]["fields"]},
            {"id", "gwflowAnalysisUid"},
        )

        invalid = self.query(
            """
            query {
              gwflowLinkedBilbyJobs(sname: "S230601linked") {
                id
                name
              }
            }
            """
        )
        self.assertIsNotNone(invalid.errors)
        self.assertIn(
            "Cannot query field 'name' on type 'GWFlowLinkedBilbyJob'",
            invalid.errors[0]["message"],
        )

    @override_settings(GWFLOW_INGEST_USER=99)
    def test_si4b_nested_query_omits_private_child_but_lookup_returns_it(self):
        private = self._child("pe-private", private=True)
        self._auth_as(self.ingest_user)
        response = self.query(
            """
            query {
              gwflowJobBySname(sname: "S230601linked") {
                bilbyJobs { id }
              }
              gwflowLinkedBilbyJobs(sname: "S230601linked") {
                id
                gwflowAnalysisUid
              }
            }
            """
        )
        self.assertResponseNoErrors(response)
        global_id = to_global_id("BilbyJobNode", private.id)
        self.assertNotIn(
            global_id,
            [job["id"] for job in response.data["gwflowJobBySname"]["bilbyJobs"]],
        )
        self.assertEqual(
            response.data["gwflowLinkedBilbyJobs"],
            [{"id": global_id, "gwflowAnalysisUid": "pe-private"}],
        )
