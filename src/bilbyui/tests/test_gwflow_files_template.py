from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from bilbyui.models import BilbyJob, GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase


def _create_job(user, sname="S230601ag", **kwargs):
    defaults = {
        "sname": sname,
        "user": user,
        "libraries": ["cbc-workflow-o4a"],
        "schema_version": "v2",
    }
    defaults.update(kwargs)
    return GWFlowJob.objects.create(**defaults)


def _make_file(job, analysis_uid, path, uploaded, file_size=1024):
    return GWFlowFile.objects.create(
        job=job,
        analysis_uid=analysis_uid,
        path=path,
        file_name=path.rsplit("/", 1)[-1],
        file_size=file_size,
        uploaded=uploaded,
    )


class TestGWFlowFilesTemplateStates(BilbyTestCase):
    def setUp(self):
        self.ligo_user = self.create_user(
            id=10,
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"],
        )
        self.authenticate(user=self.ligo_user)
        self.job = _create_job(self.ligo_user)
        self.url = reverse("bilbyui:gwflow_job_files", args=[self.job.sname])

    def test_mirrored_state(self):
        _make_file(self.job, "analysis-1", "outdir/a.h5", uploaded=True)
        _make_file(self.job, "analysis-1", "outdir/b.h5", uploaded=True)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 of 2 mirrored ✓")
        self.assertContains(response, "✓ mirrored")
        self.assertNotContains(response, "pending")
        self.assertNotContains(response, "Why can't I download?")

    def test_pending_state(self):
        _make_file(self.job, "analysis-1", "outdir/a.h5", uploaded=False)
        _make_file(self.job, "analysis-1", "outdir/b.h5", uploaded=False)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 of 2 pending ⏳ syncing")
        self.assertContains(response, "pending")
        self.assertContains(response, "Why can't I download?")
        self.assertContains(
            response,
            "This file is still being mirrored from the portal. Once mirroring finishes, the download will be available here.",
        )

    def test_mixed_state(self):
        _make_file(self.job, "analysis-1", "outdir/a.h5", uploaded=True)
        _make_file(self.job, "analysis-1", "outdir/b.h5", uploaded=False)
        _make_file(self.job, "analysis-1", "outdir/c.h5", uploaded=False)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 of 3 pending ⏳ syncing")
        self.assertContains(response, "✓ mirrored")
        self.assertContains(response, "Why can't I download?")

    def test_zero_files_state(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "async-empty")
        self.assertContains(response, "No files yet.")
        self.assertContains(
            response, "Files will appear here once the superevent's analyses have been mirrored from the portal."
        )
        self.assertNotContains(response, "gw-analysis-block")

    def test_superevent_section_titled_explicitly(self):
        _make_file(self.job, "", "outdir/super.h5", uploaded=True)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Superevent-level files")
        self.assertContains(response, 'role="region"')

    def test_orphan_uid_grouped_with_available_metadata(self):
        _make_file(self.job, "orphan-uid", "outdir/o.h5", uploaded=True)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Analysis")
        self.assertContains(response, "orphan-uid")

    def test_linked_job_link_inside_block(self):
        child = BilbyJob.objects.create(
            user=self.ligo_user,
            name="bilby-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )
        _make_file(self.job, "analysis-1", "outdir/a.h5", uploaded=True)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Linked Bilby job:")
        self.assertContains(
            response,
            f'href="{reverse("bilbyui:view_job", args=[child.id])}"',
        )
        self.assertContains(response, f"bilby-child (#{child.id})")
        self.assertNotContains(response, "Linked Bilby jobs")

    def test_full_path_hidden_behind_disclosure(self):
        _make_file(self.job, "analysis-1", "outdir/deep/nested/a.h5", uploaded=True)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "a.h5")
        self.assertContains(response, "outdir/deep")
        self.assertContains(response, "hidden")
        self.assertContains(response, "Show full path")

    def test_href_audit_uses_named_route(self):
        uploaded = _make_file(self.job, "analysis-1", "outdir/a.h5", uploaded=True)
        _make_file(self.job, "analysis-1", "outdir/b.h5", uploaded=False)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/file_download/?fileId=")
        self.assertContains(
            response,
            reverse("bilbyui:gwflow_file_download", args=[uploaded.download_token]),
        )

    def test_files_partial_render_query_count_bounded(self):
        # Many files across multiple blocks plus a linked bilby job: the full
        # view + template render path must stay within a constant query bound
        # (prefetched files/bilby_jobs; no per-file or per-block N+1).
        for i in range(20):
            _make_file(
                self.job,
                "analysis-1" if i % 2 else "",
                f"outdir/f{i}.h5",
                uploaded=bool(i % 2),
            )
        BilbyJob.objects.create(
            user=self.ligo_user,
            name="bilby-child",
            gwflow_job=self.job,
            gwflow_analysis_uid="analysis-1",
        )

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(ctx), 8)
