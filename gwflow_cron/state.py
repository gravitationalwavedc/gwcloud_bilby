import sqlite3


def init_db(con_or_cur):
    """Ensure sync_state and job_errors tables exist."""
    if isinstance(con_or_cur, sqlite3.Connection):
        cur = con_or_cur.cursor()
        con = con_or_cur
    else:
        cur = con_or_cur
        con = None

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS sync_state (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS job_errors (
        job_id TEXT PRIMARY KEY,
        failure_count INTEGER NOT NULL DEFAULT 0,
        last_failure TIMESTAMP,
        last_error TEXT
    );
    """
    )
    cols = [row[1] for row in cur.execute("PRAGMA table_info(job_errors)").fetchall()]
    if "job_ref" not in cols:
        cur.execute("ALTER TABLE job_errors ADD COLUMN job_ref TEXT")
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS changed_snames (
        sname TEXT PRIMARY KEY
    );
    """
    )
    if con:
        con.commit()


def get_sync_state(cur, key: str) -> str | None:
    row = cur.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_sync_state(con, cur, key: str, value: str):
    cur.execute(
        "INSERT INTO sync_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    if con:
        con.commit()


def get_watermark(cur) -> str | None:
    return get_sync_state(cur, "watermark")


def set_watermark(con, cur, value: str):
    set_sync_state(con, cur, "watermark", value)


def get_last_sname(cur) -> str | None:
    return get_sync_state(cur, "last_sname")


def set_last_sname(con, cur, value: str):
    set_sync_state(con, cur, "last_sname", value)


def record_failure(con, cur, job_id: str, error_msg: str, job_ref: str | None = None):
    cur.execute(
        "INSERT INTO job_errors (job_id, failure_count, last_failure, last_error, job_ref) VALUES (?, 1, CURRENT_TIMESTAMP, ?, ?) "
        "ON CONFLICT(job_id) DO UPDATE SET failure_count = failure_count + 1, last_failure = CURRENT_TIMESTAMP, last_error = ?, "
        "job_ref = COALESCE(excluded.job_ref, job_errors.job_ref)",
        (job_id, error_msg, job_ref, error_msg),
    )
    if con:
        con.commit()


def get_failure_count(cur, job_id: str) -> int:
    row = cur.execute("SELECT failure_count FROM job_errors WHERE job_id = ?", (job_id,)).fetchone()
    return row["failure_count"] if row else 0


def clear_failure(con, cur, job_id: str):
    cur.execute("DELETE FROM job_errors WHERE job_id = ?", (job_id,))
    if con:
        con.commit()


def failures_over(cur, cap: int) -> list[str]:
    rows = cur.execute("SELECT job_id FROM job_errors WHERE failure_count >= ?", (cap,)).fetchall()
    return [row["job_id"] for row in rows]


def failures_under(cur, cap: int) -> list[str]:
    rows = cur.execute("SELECT job_id FROM job_errors WHERE failure_count < ?", (cap,)).fetchall()
    return [row["job_id"] for row in rows]


def ensure_pending(con, cur, job_id: str):
    """Create a pending marker row without touching an existing row's failure_count."""
    cur.execute(
        "INSERT OR IGNORE INTO job_errors (job_id, failure_count, last_failure, last_error) VALUES (?, 0, NULL, NULL)",
        (job_id,),
    )
    if con:
        con.commit()


def set_job_ref(con, cur, job_id: str, job_ref: str):
    """Persist the id of a successfully-uploaded-but-unlinked job for this key."""
    cur.execute("UPDATE job_errors SET job_ref = ? WHERE job_id = ?", (job_ref, job_id))
    if con:
        con.commit()


def get_failure_job_ref(cur, job_id: str) -> str | None:
    row = cur.execute("SELECT job_ref FROM job_errors WHERE job_id = ?", (job_id,)).fetchone()
    return row["job_ref"] if row else None


def clear_changed_snames(con, cur):
    """Clear all rows from the changed_snames table."""
    cur.execute("DELETE FROM changed_snames")
    if con:
        con.commit()


def record_changed_sname(con, cur, sname: str):
    """Record a changed sname (idempotent via PRIMARY KEY)."""
    cur.execute(
        "INSERT OR REPLACE INTO changed_snames (sname) VALUES (?)",
        (sname,),
    )
    if con:
        con.commit()


def get_changed_snames(cur) -> list[str]:
    """Return all recorded changed snames."""
    rows = cur.execute("SELECT sname FROM changed_snames").fetchall()
    return [row["sname"] for row in rows]
