import unittest

import gwosc_ingest


class TestFixJobName(unittest.TestCase):
    """Unit tests for fix_job_name sanitisation."""

    def test_preserves_alphanumerics_underscore_hyphen(self):
        self.assertEqual(gwosc_ingest.fix_job_name("GW150914_123456-v2"), "GW150914_123456-v2")

    def test_replaces_special_characters_with_hyphen(self):
        self.assertEqual(gwosc_ingest.fix_job_name("GW000001.123456"), "GW000001-123456")

    def test_replaces_colon_and_tilde(self):
        self.assertEqual(gwosc_ingest.fix_job_name("IMRPhenom:Test~3"), "IMRPhenom-Test-3")

    def test_replaces_spaces(self):
        self.assertEqual(gwosc_ingest.fix_job_name("GW event 1"), "GW-event-1")

    def test_replaces_uppercase_and_lowercase_special(self):
        self.assertEqual(gwosc_ingest.fix_job_name("GW@event#"), "GW-event-")


class TestBuildBilbyjobName(unittest.TestCase):
    """Unit tests for build_bilbyjob_name event--config join."""

    def test_joins_with_eventname_separator(self):
        self.assertEqual(
            gwosc_ingest.build_bilbyjob_name("GW000001_123456", "IMRPhenom"),
            f"GW000001_123456{gwosc_ingest.EVENTNAME_SEPARATOR}IMRPhenom",
        )

    def test_sanitises_both_parts(self):
        self.assertEqual(
            gwosc_ingest.build_bilbyjob_name("GW000001.123456", "IMRPhenom:Test~3"),
            "GW000001-123456--IMRPhenom-Test-3",
        )
