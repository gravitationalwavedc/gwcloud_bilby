from pathlib import Path
from tempfile import TemporaryDirectory

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _file_response


class _Request:
    def __init__(self, get):
        self.GET = get


class FileResponseHelperTestCase(BilbyTestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.file_path = Path(self.temp_dir.name) / "data.txt"
        self.file_path.write_bytes(b"file contents")

    def test_inline_by_default(self):
        response = _file_response(_Request({}), self.file_path, "data.txt")
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'inline; filename="data.txt"',
        )

    def test_attachment_with_force_download(self):
        response = _file_response(_Request({"forceDownload": ""}), self.file_path, "data.txt")
        self.assertEqual(response.headers["Content-Type"], "application/octet-stream")
        self.assertEqual(
            response.headers["Content-Disposition"],
            'attachment; filename="data.txt"',
        )
