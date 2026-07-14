from io import StringIO
from unittest import mock

from django.core.management import call_command

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestEsIngestCommand(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        for i in range(3):
            BilbyJob.objects.create(
                user_id=cls.user.id,
                name=f"Test_Job_{i}",
                description="Test job description",
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

    def test_es_ingest_success(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True) as mock_save:
            call_command("es_ingest", stdout=out)

        self.assertEqual(mock_save.call_count, 3)
        output = out.getvalue()
        self.assertIn("Ingestion complete: 3 succeeded, 0 failed", output)
        self.assertIn("✓ Job", output)

    def test_es_ingest_error(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True, side_effect=Exception("boom")):
            call_command("es_ingest", stdout=out)

        output = out.getvalue()
        self.assertIn("Ingestion complete: 0 succeeded, 3 failed", output)
        self.assertIn("✗ Job", output)
        self.assertIn("boom", output)
