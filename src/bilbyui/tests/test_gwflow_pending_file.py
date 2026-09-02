from graphql_relay.node.node import to_global_id

from bilbyui.models import GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _gwflow_pending_file


class GWFlowPendingFileTestCase(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()

    def test_dict_input_encodes_fields(self):
        entry = {
            "id": 7,
            "sname": "S230601ag",
            "analysis_uid": "analysis-1",
            "path": "data/file1.txt",
            "file_name": "file1.txt",
            "md5_sum": "abc123",
        }

        result = _gwflow_pending_file(entry)

        self.assertEqual(result.id, to_global_id("GWFlowFileNode", 7))
        self.assertEqual(result.sname, "S230601ag")
        self.assertEqual(result.analysis_uid, "analysis-1")
        self.assertEqual(result.path, "data/file1.txt")
        self.assertEqual(result.file_name, "file1.txt")
        self.assertEqual(result.md5_sum, "abc123")

    def test_model_input_uses_job_sname(self):
        job = GWFlowJob.objects.create(
            sname="S230601ag",
            user=self.user,
        )
        file_obj = GWFlowFile.objects.create(
            job=job,
            analysis_uid="analysis-2",
            path="data/file2.txt",
            file_name="file2.txt",
            md5_sum="def456",
        )

        result = _gwflow_pending_file(file_obj)

        self.assertEqual(result.id, to_global_id("GWFlowFileNode", file_obj.id))
        self.assertEqual(result.sname, "S230601ag")
        self.assertEqual(result.analysis_uid, "analysis-2")
        self.assertEqual(result.path, "data/file2.txt")
        self.assertEqual(result.file_name, "file2.txt")
        self.assertEqual(result.md5_sum, "def456")
