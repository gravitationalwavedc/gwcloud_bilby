import state
from tests.base import GWFlowTestBase


class TestState(GWFlowTestBase):
    def test_watermark_round_trip(self):
        cur = self.con.cursor()
        self.assertIsNone(state.get_watermark(cur))
        state.set_watermark(self.con, cur, "2026-08-04T00:00:00Z")
        self.assertEqual(state.get_watermark(cur), "2026-08-04T00:00:00Z")

    def test_last_sname_round_trip(self):
        cur = self.con.cursor()
        self.assertIsNone(state.get_last_sname(cur))
        state.set_last_sname(self.con, cur, "GW150914_095045")
        self.assertEqual(state.get_last_sname(cur), "GW150914_095045")

    def test_failure_recording_and_clearing(self):
        cur = self.con.cursor()
        job_id = "job-test-123"

        self.assertEqual(state.get_failure_count(cur, job_id), 0)

        state.record_failure(self.con, cur, job_id, "Connection timeout")
        self.assertEqual(state.get_failure_count(cur, job_id), 1)

        state.record_failure(self.con, cur, job_id, "Connection timeout 2")
        self.assertEqual(state.get_failure_count(cur, job_id), 2)

        state.record_failure(self.con, cur, job_id, "Connection timeout 3")
        self.assertEqual(state.get_failure_count(cur, job_id), 3)

        self.assertEqual(state.failures_over(cur, cap=2), [job_id])
        self.assertEqual(state.failures_over(cur, cap=5), [])

        state.clear_failure(self.con, cur, job_id)
        self.assertEqual(state.get_failure_count(cur, job_id), 0)
        self.assertEqual(state.failures_over(cur, cap=1), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
