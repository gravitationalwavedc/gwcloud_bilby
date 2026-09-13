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
    def test_cancel_with_unknown_scheduler(self, get_scheduler_mock):
        get_scheduler_mock.return_value = None

        from core.cancel import cancel

        result = cancel({"job_id": 1}, {"submit_id": 1234})

        self.assertFalse(result)

    @patch("core.cancel.get_scheduler")
    def test_cancel_without_submit_id(self, get_scheduler_mock):
        sched_mock = Mock()
        get_scheduler_mock.return_value = sched_mock

        from core.cancel import cancel

        result = cancel({"job_id": 1}, {"job_id": 1})

        self.assertFalse(result)
        sched_mock.cancel.assert_not_called()
