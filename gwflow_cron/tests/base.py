import logging
import sqlite3
import unittest
from unittest.mock import patch

import settings
import state

logger = logging.getLogger("gwflow_ingest")
while logger.handlers:
    logger.removeHandler(logger.handlers[0])


class _NonClosingConnection:
    def __init__(self, con):
        object.__setattr__(self, "_con", con)

    def close(self):
        pass

    def __getattr__(self, attr):
        return getattr(object.__getattribute__(self, "_con"), attr)

    def __setattr__(self, attr, value):
        setattr(object.__getattribute__(self, "_con"), attr, value)


class GWFlowTestBase(unittest.TestCase):
    """Shared base test case for gwflow_cron tests."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        state.init_db(self.con)

        settings.DB_PATH = ":memory:"
        settings.GWCLOUD_TOKEN = "VALID"
        settings.GWCLOUD_ENDPOINT = "https://gwcloud.org.au/graphql"
        settings.JOB_CONTROLLER_JWT_SECRET = "VALID_SECRET"
        settings.JOB_CONTROLLER_BUNDLE = "VALID_BUNDLE"

        self.con_patch = patch("sqlite3.connect", lambda x: _NonClosingConnection(self.con))
        self.con_patch.start()

    def tearDown(self):
        self.con_patch.stop()
        self.con.close()
