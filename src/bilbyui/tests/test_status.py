from bilbyui.status import JobStatus
from bilbyui.tests.testcases import BilbyTestCase


class TestJobStatusDisplayName(BilbyTestCase):
    def test_display_name_known_statuses(self):
        cases = [
            (JobStatus.DRAFT, "Draft"),
            (JobStatus.PENDING, "Pending"),
            (JobStatus.SUBMITTING, "Submitting"),
            (JobStatus.SUBMITTED, "Submitted"),
            (JobStatus.QUEUED, "Queued"),
            (JobStatus.RUNNING, "Running"),
            (JobStatus.CANCELLING, "Cancelling"),
            (JobStatus.CANCELLED, "Cancelled"),
            (JobStatus.DELETING, "Deleting"),
            (JobStatus.DELETED, "Deleted"),
            (JobStatus.ERROR, "Error"),
            (JobStatus.WALL_TIME_EXCEEDED, "Wall Time Exceeded"),
            (JobStatus.OUT_OF_MEMORY, "Out of Memory"),
            (JobStatus.COMPLETED, "Completed"),
        ]
        for status, expected in cases:
            with self.subTest(status=status, expected=expected):
                self.assertEqual(JobStatus.display_name(status), expected)

    def test_display_name_unknown_status(self):
        self.assertEqual(JobStatus.display_name(999), "Unknown")
