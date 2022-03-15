import unittest
from unittest.mock import patch


class TestMisc(unittest.TestCase):
    @patch("settings.job_directory", '/my/test/directory')
    def test_working_directory(self):
        import settings
        from core.misc import working_directory

        details = {
            'job_id': 1234
        }

        self.assertEqual(
            working_directory(details),
            f"{settings.job_directory}/{str(details['job_id'])}"
        )