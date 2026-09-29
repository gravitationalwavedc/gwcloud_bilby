import os
import sqlite3
import sys


def clear_event_failures(con, cur):
    """Purge failure records caused by past event_id creation issues.

    Events with max_retries_exceeded are re-evaluated as active delta jobs.
    """
    cur.execute("DELETE FROM job_errors WHERE last_error LIKE '%event_id%' OR last_error LIKE '%EventID%'")
    cur.execute(
        "DELETE FROM completed_jobs WHERE reason = 'max_retries_exceeded' "
        "AND (reason_data LIKE '%event_id%' OR reason_data LIKE '%EventID%')"
    )
    con.commit()


if __name__ == "__main__":
    try:
        from local import DB_PATH
    except ImportError:
        DB_PATH = os.getenv("DB_PATH")

    if not DB_PATH:
        print("Error: DB_PATH is not set in local.py or environment.", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to {DB_PATH}...")
    con = sqlite3.connect(DB_PATH)
    try:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        clear_event_failures(con, cur)
    finally:
        con.close()
    print("Event failures successfully cleared.")
