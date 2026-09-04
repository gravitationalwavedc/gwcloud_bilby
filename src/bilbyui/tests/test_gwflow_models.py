import uuid

from django.db import IntegrityError, transaction

from bilbyui.models import BilbyJob, EventID, GWFlowFile, GWFlowJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class GWFlowModelsTestCase(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()

    def test_gwflow_job_minimal_creation_and_defaults(self):
        job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
        )

        self.assertEqual(job.sname, "S230601ag")
        self.assertEqual(job.user, self.user)
        self.assertTrue(job.ligo_only)
        self.assertFalse(job.is_pruned)
        self.assertEqual(job.libraries, [])
        self.assertEqual(job.schema_version, "")
        self.assertEqual(job.current_history_id, "")
        self.assertIsNone(job.current_history_timestamp)
        self.assertIsNone(job.event_id)
        self.assertIsNotNone(job.creation_time)
        self.assertIsNotNone(job.last_updated)

    def test_gwflow_job_sname_uniqueness(self):
        GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            GWFlowJob.objects.create(
                sname="S230601ag",
                user=self.user,
            )

    def test_gwflow_file_unique_together_and_token(self):
        job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
        )

        file1 = GWFlowFile.objects.create(
            job=job,
            analysis_uid="",
            path="data/file1.txt",
            file_name="file1.txt",
        )

        self.assertIsNotNone(file1.download_token)
        self.assertFalse(file1.uploaded)

        # Duplicate (job, analysis_uid, path) should raise IntegrityError
        with self.assertRaises(IntegrityError), transaction.atomic():
            GWFlowFile.objects.create(
                job=job,
                analysis_uid="",
                path="data/file1.txt",
                file_name="file1.txt",
            )

        # Different analysis_uid or path should succeed and have distinct token
        file2 = GWFlowFile.objects.create(
            job=job,
            analysis_uid="analysis_1",
            path="data/file1.txt",
            file_name="file1.txt",
        )
        self.assertNotEqual(file1.download_token, file2.download_token)

    def test_bilby_job_gwflow_job_relation_and_set_null(self):
        gwflow_job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
        )

        bilby_job = BilbyJob.objects.create(
            user=self.user,
            ini_string=create_test_ini_string(),
            gwflow_job=gwflow_job,
            gwflow_analysis_uid="analysis_123",
        )

        self.assertEqual(gwflow_job.bilby_jobs.count(), 1)
        self.assertEqual(gwflow_job.bilby_jobs.first(), bilby_job)

        gwflow_job.delete()

        bilby_job.refresh_from_db()
        self.assertIsNone(bilby_job.gwflow_job)
        self.assertEqual(bilby_job.gwflow_analysis_uid, "analysis_123")

    def test_event_id_set_null_on_gwflow_job(self):
        event = EventID.objects.create(
            event_id="GW150914_095045",
            trigger_id="S150914a",
        )

        gwflow_job = GWFlowJob.objects.create(
            sname="S150914a",
            user=self.user,
            event_id=event,
        )

        self.assertEqual(gwflow_job.event_id, event)

        event.delete()

        gwflow_job.refresh_from_db()
        self.assertIsNone(gwflow_job.event_id)

    def test_get_by_download_token_invalid(self):
        job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
        )
        GWFlowFile.objects.create(
            job=job,
            analysis_uid="",
            path="data/file1.txt",
            file_name="file1.txt",
        )

        self.assertIsNone(GWFlowFile.get_by_download_token(str(uuid.uuid4())))

    def test_get_by_download_token(self):
        job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
        )
        gwflow_file = GWFlowFile.objects.create(
            job=job,
            analysis_uid="",
            path="data/file1.txt",
            file_name="file1.txt",
        )

        result = GWFlowFile.get_by_download_token(gwflow_file.download_token)

        self.assertEqual(result.id, gwflow_file.id)
        self.assertEqual(result.job, job)
