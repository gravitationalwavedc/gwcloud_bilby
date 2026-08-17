from unittest import TestCase
from unittest.mock import Mock, patch


class TestCancel(TestCase):
    @patch("core.cancel.get_scheduler")
    def test_cancel_with_submit_id(self, get_scheduler_mock):
        sched_mock = Mock()
        sched_mock.cancel.return_value = True
        get_scheduler_mock.return_value = sched_mock

        from core.cancel import cancel

        details = {"job_id": 1}
        job_data = {"submit_id": 1234}

        result = cancel(details, job_data)

        self.assertTrue(result)
        sched_mock.cancel.assert_called_once_with(1234, details)

    @patch("core.cancel.get_scheduler")
    def test_cancel_without_submit_id(self, get_scheduler_mock):
        sched_mock = Mock()
        get_scheduler_mock.return_value = sched_mock

        from core.cancel import cancel

        result = cancel({"job_id": 1}, {"job_id": 1})

        self.assertFalse(result)
        sched_mock.cancel.assert_not_called()


class TestDelete(TestCase):
    @patch("core.delete.shutil.rmtree")
    @patch("core.delete.working_directory")
    def test_delete(self, working_directory_mock, rmtree_mock):
        working_directory_mock.return_value = "/some/path"

        from core.delete import delete

        details = {"job_id": 1}
        job_data = {"job_id": 1}

        delete(details, job_data)

        working_directory_mock.assert_called_once_with(details, job_data)
        rmtree_mock.assert_called_once_with("/some/path")

    @patch("core.delete.shutil.rmtree")
    @patch("core.delete.working_directory")
    def test_delete_suppresses_oserror(self, working_directory_mock, rmtree_mock):
        working_directory_mock.return_value = "/some/path"
        rmtree_mock.side_effect = OSError("boom")

        from core.delete import delete

        delete({"job_id": 1}, {"job_id": 1})

        rmtree_mock.assert_called_once_with("/some/path")
