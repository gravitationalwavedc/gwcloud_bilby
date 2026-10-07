"""
Regression guard: scan tracked repository files for removed legacy LIGO flag tokens.

The five removed field spellings are built from fragments below so this guard
does not match its own source after it becomes tracked.

Allowed paths (exhaustive list; do NOT add broad exclusions):
  - src/bilbyui/migrations/0047_drop_legacy_flag_columns.py, whose RemoveField
    operations must name the removed fields.
  - Numbered migration files with a numeric prefix lower than 0047, which are
    immutable historical migrations that may legitimately name those fields.

All other files, including migrations numbered 0047 or later, are forbidden.
"""

import os
import re
import subprocess

from django.test import SimpleTestCase

# ---------------------------------------------------------------------------
# Token list — built from fragments so this source file does not self-match.
# ---------------------------------------------------------------------------
_TOKENS = [
    "ligo" + "_only",
    "is_ligo" + "_job",
    "is_ligo" + "_event",
    "ligo" + "Only",
    "isLigo" + "Event",
]

_PATTERN = re.compile("|".join(re.escape(t) for t in _TOKENS))

# ---------------------------------------------------------------------------
# Allowed paths (relative to repo root).
# Only immutable migrations before 0047 and the named 0047 removal migration
# are permitted; everything else is a violation.
# ---------------------------------------------------------------------------
_REMOVAL_MIGRATION = "src/bilbyui/migrations/0047_drop_legacy_flag_columns.py"
_NUMBERED_MIGRATION_RE = re.compile(r"^src/bilbyui/migrations/(?P<number>\d{4})_.*\.py$")


def _is_allowed_path(rel_path):
    if rel_path == _REMOVAL_MIGRATION:
        return True

    match = _NUMBERED_MIGRATION_RE.fullmatch(rel_path)
    return match is not None and int(match.group("number")) < 47


class LegacyFlagAllowlistTest(SimpleTestCase):
    """Verify the migration allowlist cannot admit future schema changes."""

    def test_allows_only_pre_0047_history_and_named_removal_migration(self):
        self.assertTrue(_is_allowed_path("src/bilbyui/migrations/0013_example.py"))
        self.assertTrue(_is_allowed_path("src/bilbyui/migrations/0046_example.py"))
        self.assertTrue(_is_allowed_path(_REMOVAL_MIGRATION))

        self.assertFalse(_is_allowed_path("src/bilbyui/migrations/0047_other.py"))
        self.assertFalse(_is_allowed_path("src/bilbyui/migrations/0048_example.py"))
        self.assertFalse(_is_allowed_path("src/bilbyui/migrations/0050_example.py"))
        self.assertFalse(_is_allowed_path("src/bilbyui/migrations/not_numbered.py"))
        self.assertFalse(_is_allowed_path("src/bilbyui/models.py"))


class LegacyFlagTokensAbsentTest(SimpleTestCase):
    """Fail if any tracked file outside the allowlist references removed flag columns."""

    def test_no_legacy_flag_references_outside_allowlist(self):
        # Determine repo root (two levels up from this file: tests/ -> bilbyui/ -> src/ -> repo)
        this_file = os.path.abspath(__file__)
        repo_root = os.path.dirname(  # gwcloud_bilby-113
            os.path.dirname(          # src
                os.path.dirname(      # bilbyui
                    os.path.dirname(  # tests
                        this_file
                    )
                )
            )
        )

        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        tracked_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]

        violations = []
        for rel_path in tracked_files:
            if _is_allowed_path(rel_path):
                continue
            abs_path = os.path.join(repo_root, rel_path)
            try:
                with open(abs_path, encoding="utf-8", errors="ignore") as fh:
                    for lineno, line in enumerate(fh, 1):
                        if _PATTERN.search(line):
                            violations.append(f"{rel_path}:{lineno}: {line.rstrip()}")
            except (OSError, IsADirectoryError):
                pass

        if violations:
            formatted = "\n".join(violations)
            self.fail(
                f"Found {len(violations)} non-allowlisted reference(s) to removed LIGO flag tokens.\n"
                f"These references must be removed:\n\n{formatted}"
            )
