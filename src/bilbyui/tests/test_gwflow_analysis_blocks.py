from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.db import connection
from django.test.utils import CaptureQueriesContext

from bilbyui.models import BilbyJob, GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_gwflow_analysis_blocks


def _create_job(user, sname="S230601ag", **kwargs):
    defaults = {
        "sname": sname,
        "user": user,
        "libraries": ["cbc-workflow-o4a"],
        "schema_version": "v2",
    }
    defaults.update(kwargs)
    return GWFlowJob.objects.create(**defaults)


class TestBuildGWFlowAnalysisBlocks(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.job = _create_job(self.user)

    def _add_file(self, analysis_uid, file_name, uploaded=True, **kwargs):
        return GWFlowFile.objects.create(
            job=self.job,
            analysis_uid=analysis_uid,
            path=f"data/{file_name}",
            file_name=file_name,
            uploaded=uploaded,
            **kwargs,
        )

    def test_files_grouped_by_analysis_uid(self):
        self._add_file("analysis-1", "a.txt")
        self._add_file("analysis-1", "b.txt")
        self._add_file("analysis-2", "c.txt")

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual(len(blocks), 2)
        by_uid = {b["analysis_uid"]: b for b in blocks}
        self.assertEqual([f.file_name for f in by_uid["analysis-1"]["files"]], ["a.txt", "b.txt"])
        self.assertEqual([f.file_name for f in by_uid["analysis-2"]["files"]], ["c.txt"])

    def test_orphan_uid_grouped_with_available_metadata(self):
        self._add_file("long-analysis-uid-123", "a.txt")
        child = BilbyJob.objects.create(
            user=self.user,
            name="bilby-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="long-analysis-uid-123",
        )

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block["analysis_uid"], "long-analysis-uid-123")
        self.assertEqual(block["analysis_uid_short"], "long-ana")
        self.assertEqual(block["bilby_jobs"], [child])
        self.assertFalse(block["is_superevent"])

    def test_superevent_level_files_grouped_separately(self):
        self._add_file("", "super.txt")
        self._add_file("analysis-1", "a.txt")

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual(len(blocks), 2)
        self.assertTrue(blocks[0]["is_superevent"])
        self.assertEqual(blocks[0]["analysis_uid"], "")
        self.assertEqual([f.file_name for f in blocks[0]["files"]], ["super.txt"])
        self.assertFalse(blocks[1]["is_superevent"])
        self.assertEqual(blocks[1]["analysis_uid"], "analysis-1")

    def test_missing_bilby_job_tolerated(self):
        self._add_file("analysis-1", "a.txt")

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["bilby_jobs"], [])
        self.assertEqual(len(blocks[0]["files"]), 1)

    def test_linked_bilby_job_matched_by_uid(self):
        self._add_file("analysis-1", "a.txt")
        child = BilbyJob.objects.create(
            user=self.user,
            name="bilby-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )
        other_child = BilbyJob.objects.create(
            user=self.user,
            name="other-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-other",
        )

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual(len(blocks), 2)
        by_uid = {b["analysis_uid"]: b for b in blocks}
        self.assertEqual(by_uid["analysis-1"]["bilby_jobs"], [child])
        self.assertEqual(by_uid["analysis-other"]["bilby_jobs"], [other_child])

    def test_blocks_ordered_by_uid(self):
        self._add_file("z-uid", "z.txt")
        self._add_file("a-uid", "a.txt")
        self._add_file("m-uid", "m.txt")

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual([b["analysis_uid"] for b in blocks], ["a-uid", "m-uid", "z-uid"])

    def test_duplicate_linked_jobs_same_uid_all_preserved(self):
        self._add_file("analysis-1", "a.txt")
        child_a = BilbyJob.objects.create(
            user=self.user,
            name="child-a",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )
        child_b = BilbyJob.objects.create(
            user=self.user,
            name="child-b",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["bilby_jobs"], [child_a, child_b])

    def test_linked_job_without_files_still_produces_block(self):
        child = BilbyJob.objects.create(
            user=self.user,
            name="job-only",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-only",
        )

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual(len(blocks), 1)
        block = blocks[0]
        self.assertEqual(block["analysis_uid"], "analysis-only")
        self.assertEqual(block["bilby_jobs"], [child])
        self.assertEqual(block["files"], [])

    def test_analyses_attaches_metadata_to_matching_block(self):
        self._add_file("pe-uid-1", "a.txt")
        analyses = {
            "pe-uid-1": {
                "software": "bilby",
                "waveform": "IMRPhenomXPHM",
                "run_status": "completed",
                "review_status": "approved",
                "deprecated": False,
            }
        }

        blocks = _build_gwflow_analysis_blocks(self.job, analyses)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["metadata"], analyses["pe-uid-1"])

    def test_blocks_follow_pe_results_order_when_analyses_passed(self):
        self._add_file("z-uid", "z.txt")
        self._add_file("a-uid", "a.txt")
        self._add_file("m-uid", "m.txt")
        analyses = {
            "m-uid": {"software": "bilby", "waveform": "", "run_status": "", "review_status": "", "deprecated": False},
            "z-uid": {"software": "pycbc", "waveform": "", "run_status": "", "review_status": "", "deprecated": False},
        }

        blocks = _build_gwflow_analysis_blocks(self.job, analyses)

        self.assertEqual([b["analysis_uid"] for b in blocks], ["m-uid", "z-uid", "a-uid"])

    def test_blocks_uid_sorted_when_no_analyses(self):
        self._add_file("z-uid", "z.txt")
        self._add_file("a-uid", "a.txt")

        blocks = _build_gwflow_analysis_blocks(self.job)

        self.assertEqual([b["analysis_uid"] for b in blocks], ["a-uid", "z-uid"])

    def test_query_count_bounded(self):
        self._add_file("", "super.txt")
        self._add_file("analysis-1", "a.txt")
        self._add_file("analysis-1", "b.txt")
        self._add_file("analysis-2", "c.txt")
        BilbyJob.objects.create(
            user=self.user,
            name="bilby-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )

        with CaptureQueriesContext(connection) as ctx:
            _build_gwflow_analysis_blocks(self.job)

        self.assertLessEqual(len(ctx), 2)
