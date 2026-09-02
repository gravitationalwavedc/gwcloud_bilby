from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.test import override_settings

from bilbyui.models import GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _reconcile_gwflow_files


class GWFlowReconcileTestCase(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user()
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _make_job_and_files(self, sname, paths):
        job = GWFlowJob.objects.create(sname=sname, user=self.user, ligo_only=False)
        files = []
        job_file_dir = Path(self.temp_dir.name) / str(job.id)
        for path in paths:
            f = GWFlowFile.objects.create(
                job=job,
                analysis_uid="",
                path=path,
                file_name=Path(path).name,
                uploaded=True,
            )
            job_file_dir.mkdir(parents=True, exist_ok=True)
            (job_file_dir / str(f.id)).write_bytes(b"mirrored")
            (job_file_dir / f"{f.id}.part").write_bytes(b"partial")
            files.append(f)
        return job, files

    def _entry(self, path):
        return SimpleNamespace(analysis_uid="", path=path, file_name=Path(path).name)

    def test_reconcile_none_skips_entirely(self):
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job, files = self._make_job_and_files("S_reconcile_none", ["a.h5", "b.h5"])
            removed = _reconcile_gwflow_files(job, None)
            self.assertEqual(removed, [])
            self.assertEqual(job.files.count(), 2)

    def test_reconcile_empty_manifest_removes_all(self):
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job, files = self._make_job_and_files("S_reconcile_empty", ["a.h5", "b.h5"])
            removed = _reconcile_gwflow_files(job, [])
            self.assertEqual(len(removed), 2)
            self.assertEqual(job.files.count(), 0)
            job_file_dir = Path(self.temp_dir.name) / str(job.id)
            for f in files:
                self.assertFalse((job_file_dir / str(f.id)).exists())
                self.assertFalse((job_file_dir / f"{f.id}.part").exists())

    def test_reconcile_matching_manifest_is_noop(self):
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job, files = self._make_job_and_files("S_reconcile_match", ["a.h5", "b.h5"])
            removed = _reconcile_gwflow_files(job, [self._entry("a.h5"), self._entry("b.h5")])
            self.assertEqual(removed, [])
            self.assertEqual(job.files.count(), 2)

    def test_reconcile_partial_match_removes_orphans(self):
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job, files = self._make_job_and_files("S_reconcile_partial", ["keep.h5", "orphan.h5"])
            removed = _reconcile_gwflow_files(job, [self._entry("keep.h5")])
            self.assertEqual(len(removed), 1)
            self.assertEqual(removed[0]["path"], "orphan.h5")
            self.assertEqual(list(job.files.values_list("path", flat=True)), ["keep.h5"])
            job_file_dir = Path(self.temp_dir.name) / str(job.id)
            orphan = files[1]
            self.assertFalse((job_file_dir / str(orphan.id)).exists())
            self.assertFalse((job_file_dir / f"{orphan.id}.part").exists())
            keep = files[0]
            self.assertTrue((job_file_dir / str(keep.id)).exists())
