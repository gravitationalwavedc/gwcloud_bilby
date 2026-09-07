import sqlite3
import unittest

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


class TestSyncState(GWFlowTestBase):
    def test_get_missing_key_returns_none(self):
        cur = self.con.cursor()
        self.assertIsNone(state.get_sync_state(cur, "missing"))

    def test_insert_and_get_round_trip(self):
        cur = self.con.cursor()
        self.assertIsNone(state.get_sync_state(cur, "key1"))
        state.set_sync_state(self.con, cur, "key1", "value1")
        self.assertEqual(state.get_sync_state(cur, "key1"), "value1")

    def test_upsert_overwrites_existing_value(self):
        cur = self.con.cursor()
        state.set_sync_state(self.con, cur, "key1", "value1")
        state.set_sync_state(self.con, cur, "key1", "value2")
        self.assertEqual(state.get_sync_state(cur, "key1"), "value2")

    def test_distinct_keys_do_not_collide(self):
        cur = self.con.cursor()
        state.set_sync_state(self.con, cur, "key1", "value1")
        state.set_sync_state(self.con, cur, "key2", "value2")
        self.assertEqual(state.get_sync_state(cur, "key1"), "value1")
        self.assertEqual(state.get_sync_state(cur, "key2"), "value2")


class TestFailuresUnder(GWFlowTestBase):
    def test_returns_only_keys_with_count_below_cap(self):
        cur = self.con.cursor()
        state.ensure_pending(self.con, cur, "zero")
        state.record_failure(self.con, cur, "one", "x")
        state.record_failure(self.con, cur, "two", "x")
        state.record_failure(self.con, cur, "two", "x")

        self.assertEqual(sorted(state.failures_under(cur, cap=2)), ["one", "zero"])
        self.assertEqual(state.failures_under(cur, cap=1), ["zero"])
        self.assertEqual(sorted(state.failures_under(cur, cap=3)), ["one", "two", "zero"])


class TestEnsurePending(GWFlowTestBase):
    def test_creates_row_with_zero_failure_count(self):
        cur = self.con.cursor()
        state.ensure_pending(self.con, cur, "bilby:S1/uid1")
        self.assertEqual(state.get_failure_count(cur, "bilby:S1/uid1"), 0)
        row = cur.execute(
            "SELECT last_failure, last_error FROM job_errors WHERE job_id = ?", ("bilby:S1/uid1",)
        ).fetchone()
        self.assertIsNone(row["last_failure"])
        self.assertIsNone(row["last_error"])

    def test_does_not_reset_existing_row_counter(self):
        cur = self.con.cursor()
        state.record_failure(self.con, cur, "bilby:S1/uid1", "boom")
        self.assertEqual(state.get_failure_count(cur, "bilby:S1/uid1"), 1)

        state.ensure_pending(self.con, cur, "bilby:S1/uid1")
        self.assertEqual(state.get_failure_count(cur, "bilby:S1/uid1"), 1)


class TestJobRef(GWFlowTestBase):
    def test_set_and_get_round_trip(self):
        cur = self.con.cursor()
        state.ensure_pending(self.con, cur, "bilby:S1/uid1")
        self.assertIsNone(state.get_failure_job_ref(cur, "bilby:S1/uid1"))

        state.set_job_ref(self.con, cur, "bilby:S1/uid1", "orphan-1")
        self.assertEqual(state.get_failure_job_ref(cur, "bilby:S1/uid1"), "orphan-1")

        state.set_job_ref(self.con, cur, "bilby:S1/uid1", "orphan-2")
        self.assertEqual(state.get_failure_job_ref(cur, "bilby:S1/uid1"), "orphan-2")

    def test_get_returns_none_for_unknown_key(self):
        cur = self.con.cursor()
        self.assertIsNone(state.get_failure_job_ref(cur, "bilby:S1/uid1"))

    def test_clear_failure_removes_job_ref(self):
        cur = self.con.cursor()
        state.ensure_pending(self.con, cur, "bilby:S1/uid1")
        state.set_job_ref(self.con, cur, "bilby:S1/uid1", "orphan-1")
        self.assertEqual(state.get_failure_job_ref(cur, "bilby:S1/uid1"), "orphan-1")

        state.clear_failure(self.con, cur, "bilby:S1/uid1")
        self.assertIsNone(state.get_failure_job_ref(cur, "bilby:S1/uid1"))


class TestRecordFailureJobRef(GWFlowTestBase):
    def test_record_failure_stores_job_ref(self):
        cur = self.con.cursor()
        state.record_failure(self.con, cur, "bilby:S1/uid1", "link failed", job_ref="orphan-1")
        self.assertEqual(state.get_failure_job_ref(cur, "bilby:S1/uid1"), "orphan-1")
        self.assertEqual(state.get_failure_count(cur, "bilby:S1/uid1"), 1)

    def test_rerecord_without_job_ref_preserves_existing(self):
        cur = self.con.cursor()
        state.record_failure(self.con, cur, "bilby:S1/uid1", "link failed", job_ref="orphan-1")
        state.record_failure(self.con, cur, "bilby:S1/uid1", "link failed again")
        self.assertEqual(state.get_failure_job_ref(cur, "bilby:S1/uid1"), "orphan-1")
        self.assertEqual(state.get_failure_count(cur, "bilby:S1/uid1"), 2)

    def test_rerecord_with_new_job_ref_updates(self):
        cur = self.con.cursor()
        state.record_failure(self.con, cur, "bilby:S1/uid1", "link failed", job_ref="orphan-1")
        state.record_failure(self.con, cur, "bilby:S1/uid1", "link failed", job_ref="orphan-2")
        self.assertEqual(state.get_failure_job_ref(cur, "bilby:S1/uid1"), "orphan-2")
        self.assertEqual(state.get_failure_count(cur, "bilby:S1/uid1"), 2)


class TestInitDbMigration(unittest.TestCase):
    def test_init_db_adds_job_ref_to_existing_table(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute(
            "CREATE TABLE job_errors (job_id TEXT PRIMARY KEY, failure_count INTEGER NOT NULL DEFAULT 0, "
            "last_failure TIMESTAMP, last_error TEXT)"
        )
        cur.execute("INSERT INTO job_errors (job_id, failure_count) VALUES ('existing', 3)")
        con.commit()

        state.init_db(con)

        cols = [row[1] for row in cur.execute("PRAGMA table_info(job_errors)").fetchall()]
        self.assertIn("job_ref", cols)
        row = cur.execute("SELECT job_ref FROM job_errors WHERE job_id = 'existing'").fetchone()
        self.assertIsNone(row["job_ref"])
        con.close()


class TestChangedSnames(GWFlowTestBase):
    def test_get_changed_snames_empty(self):
        cur = self.con.cursor()
        self.assertEqual(state.get_changed_snames(cur), [])

    def test_clear_record_get_round_trip(self):
        cur = self.con.cursor()
        self.assertEqual(state.get_changed_snames(cur), [])

        state.record_changed_sname(self.con, cur, "S1")
        state.record_changed_sname(self.con, cur, "S2")
        state.record_changed_sname(self.con, cur, "S3")

        self.assertEqual(state.get_changed_snames(cur), ["S1", "S2", "S3"])

        state.clear_changed_snames(self.con, cur)
        self.assertEqual(state.get_changed_snames(cur), [])

    def test_record_changed_sname_idempotent(self):
        cur = self.con.cursor()
        state.record_changed_sname(self.con, cur, "S1")
        state.record_changed_sname(self.con, cur, "S1")
        state.record_changed_sname(self.con, cur, "S1")

        self.assertEqual(state.get_changed_snames(cur), ["S1"])

    def test_commit_persists_across_cursor(self):
        cur = self.con.cursor()
        state.record_changed_sname(self.con, cur, "S1")
        state.record_changed_sname(self.con, cur, "S2")

        cur2 = self.con.cursor()
        self.assertEqual(state.get_changed_snames(cur2), ["S1", "S2"])

        state.clear_changed_snames(self.con, cur)
        self.assertEqual(state.get_changed_snames(cur2), [])


if __name__ == "__main__":
    import unittest

    unittest.main()
