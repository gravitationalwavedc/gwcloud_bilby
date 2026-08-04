import argparse
import fcntl
import logging
import sqlite3
import sys
from pathlib import Path

import settings
import state

logger = logging.getLogger("gwflow_ingest")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    fh = logging.FileHandler("gwflow_ingest.log")
    fh.setLevel(logging.DEBUG)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    sh.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(sh)


def phase_metadata():
    logger.info("phase_metadata: not implemented")


def phase_bilby_children():
    logger.info("phase_bilby_children: not implemented")


def phase_file_mirror():
    logger.info("phase_file_mirror: not implemented")


def parse_args(args=None):
    parser = argparse.ArgumentParser(description="GWFlow ingest cron job")
    parser.add_argument("--backfill", action="store_true", help="Lift per-run caps for backfill mode")
    return parser.parse_args(args)


def run(args=None):
    parsed = parse_args(args)
    settings.BACKFILL = parsed.backfill

    settings.validate_settings()

    lock_path = str(Path(settings.DB_PATH).with_suffix(".lock"))
    lock_file = None
    try:
        lock_file = open(lock_path, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError):
        logger.warning("Another instance of gwflow_ingest is already running.")
        if lock_file:
            lock_file.close()
        return 0

    try:
        logger.info("Starting gwflow_ingest run")
        con = sqlite3.connect(settings.DB_PATH)
        con.row_factory = sqlite3.Row
        state.init_db(con)
        con.close()

        phase_metadata()
        phase_bilby_children()
        phase_file_mirror()

        logger.info("Completed gwflow_ingest run")
        return 0
    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            lock_file.close()


if __name__ == "__main__":
    sys.exit(run())
