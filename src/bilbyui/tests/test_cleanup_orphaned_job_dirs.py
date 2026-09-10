from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command

from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestCleanupOrphanedJobDirs(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.valid_job = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="Valid_Job_1",
            description="Valid job description",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def setUp(self):
        super().setUp()
        self.temp_dir = TemporaryDirectory()
        self.upload_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()
        super().tearDown()

    def _setup_mixed_directory_tree(self):
        """Helper to construct a realistic mixed directory tree on Lustre:
        - Valid job dir matching existing BilbyJob ID
        - Orphan job dir (numeric name, no DB record)
        - Non-numeric directory
        - Non-numeric file (.gitkeep)
        - Numeric file (not a directory)
        """
        # Valid job directory
        valid_dir = self.upload_dir / str(self.valid_job.id)
        valid_dir.mkdir()
        (valid_dir / "archive.tar.gz").write_text("valid archive")
        (valid_dir / "result").mkdir()

        # Orphan job directory (numeric name with no BilbyJob record)
        orphan_id = 99999
        self.assertFalse(BilbyJob.objects.filter(id=orphan_id).exists())
        orphan_dir = self.upload_dir / str(orphan_id)
        orphan_dir.mkdir()
        (orphan_dir / "archive.tar.gz").write_text("orphan archive")
        (orphan_dir / "data").mkdir()

        # Non-numeric directory
        non_numeric_dir = self.upload_dir / "temporary_extract_dir"
        non_numeric_dir.mkdir()
        (non_numeric_dir / "temp.log").write_text("temporary content")

        # Non-numeric file
        gitkeep_file = self.upload_dir / ".gitkeep"
        gitkeep_file.write_text("")

        # Numeric file (not a directory - must be skipped by is_dir() check)
        numeric_file = self.upload_dir / "88888"
        numeric_file.write_text("not a directory")

        return valid_dir, orphan_dir, non_numeric_dir, gitkeep_file, numeric_file

    def test_cleanup_default_dry_run_leaves_orphans_intact(self):
        """Running cleanup without --delete defaults to dry-run mode.
        It must list orphaned directories, report candidate counts, and delete nothing.
        """
        valid_dir, orphan_dir, non_numeric_dir, gitkeep_file, numeric_file = self._setup_mixed_directory_tree()

        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", stdout=out)

        output = out.getvalue()
        # Verify candidate counting and listing
        self.assertIn("Found 1 orphaned job directory (2 checked):", output)
        self.assertIn(str(orphan_dir), output)
        self.assertIn("Dry-run complete: 1 orphaned directory found. No files were deleted.", output)
        self.assertIn("Pass --delete to purge them.", output)

        # Assert all files and directories remain intact on disk
        self.assertTrue(orphan_dir.exists())
        self.assertTrue(valid_dir.exists())
        self.assertTrue(non_numeric_dir.exists())
        self.assertTrue(gitkeep_file.exists())
        self.assertTrue(numeric_file.exists())

    def test_cleanup_explicit_dry_run_flag(self):
        """Explicit --dry-run must leave all directories intact."""
        valid_dir, orphan_dir, non_numeric_dir, gitkeep_file, numeric_file = self._setup_mixed_directory_tree()

        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("Found 1 orphaned job directory (2 checked):", output)
        self.assertIn(str(orphan_dir), output)
        self.assertIn("Dry-run complete: 1 orphaned directory found.", output)

        self.assertTrue(orphan_dir.exists())
        self.assertTrue(valid_dir.exists())

    def test_cleanup_dry_run_precedence_over_delete(self):
        """When both --delete and --dry-run are provided, --dry-run takes precedence as a safeguard."""
        valid_dir, orphan_dir, non_numeric_dir, gitkeep_file, numeric_file = self._setup_mixed_directory_tree()

        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", "--delete", "--dry-run", stdout=out)

        output = out.getvalue()
        self.assertIn("Dry-run complete: 1 orphaned directory found.", output)
        self.assertTrue(orphan_dir.exists())
        self.assertTrue(valid_dir.exists())

    def test_cleanup_delete_removes_orphans_only(self):
        """Running with --delete removes orphaned job directories while preserving
        valid job directories, non-numeric directories, and files.
        """
        valid_dir, orphan_dir, non_numeric_dir, gitkeep_file, numeric_file = self._setup_mixed_directory_tree()

        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", "--delete", stdout=out)

        output = out.getvalue()
        # Verify deletion output
        self.assertIn("Deleting 1 orphaned job directory (2 checked)...", output)
        self.assertIn(f"✓ Deleted: {orphan_dir}", output)
        self.assertIn("Cleanup complete: 1 orphaned directory removed.", output)

        # Assert orphan directory is removed from disk
        self.assertFalse(orphan_dir.exists())

        # Assert valid job directory and contents remain untouched
        self.assertTrue(valid_dir.exists())
        self.assertTrue((valid_dir / "archive.tar.gz").exists())
        self.assertTrue((valid_dir / "result").is_dir())

        # Assert non-candidate entries remain untouched
        self.assertTrue(non_numeric_dir.exists())
        self.assertTrue(gitkeep_file.exists())
        self.assertTrue(numeric_file.exists())

    def test_cleanup_idempotency(self):
        """Running --delete a second time reports 0 orphaned directories found and makes no changes."""
        valid_dir, orphan_dir, non_numeric_dir, gitkeep_file, numeric_file = self._setup_mixed_directory_tree()

        # First run: deletes the orphan
        out1 = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", "--delete", stdout=out1)

        self.assertFalse(orphan_dir.exists())
        self.assertIn("Cleanup complete: 1 orphaned directory removed.", out1.getvalue())

        # Second run: clean state
        out2 = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", "--delete", stdout=out2)

        output2 = out2.getvalue()
        self.assertIn("1 directories checked. 0 orphaned directories found.", output2)
        self.assertTrue(valid_dir.exists())
        self.assertTrue(numeric_file.exists())

    def test_cleanup_zero_candidate_directories(self):
        """When JOB_UPLOAD_DIR has no numeric subdirectories, reports 0 directories checked."""
        # Add non-numeric dir and file
        (self.upload_dir / "temp_cache").mkdir()
        (self.upload_dir / ".gitkeep").write_text("")

        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", stdout=out)

        self.assertIn("0 directories checked. No candidate job directories found.", out.getvalue())

    def test_cleanup_empty_upload_dir(self):
        """When JOB_UPLOAD_DIR is completely empty, reports 0 directories checked."""
        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", stdout=out)

        self.assertIn("0 directories checked. No candidate job directories found.", out.getvalue())

    def test_cleanup_upload_dir_does_not_exist(self):
        """When JOB_UPLOAD_DIR path does not exist on disk, outputs a warning and exits gracefully."""
        non_existent_dir = self.upload_dir / "non_existent_path"

        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(non_existent_dir)):
            call_command("cleanup_orphaned_job_dirs", stdout=out)

        self.assertIn(f"JOB_UPLOAD_DIR directory does not exist: {non_existent_dir}", out.getvalue())

    def test_cleanup_upload_dir_setting_not_configured(self):
        """When JOB_UPLOAD_DIR setting is None or empty, outputs a warning and exits gracefully."""
        out = StringIO()
        with self.settings(JOB_UPLOAD_DIR=None):
            call_command("cleanup_orphaned_job_dirs", stdout=out)

        self.assertIn("JOB_UPLOAD_DIR setting is not configured.", out.getvalue())

    def test_cleanup_multiple_orphans_pluralization(self):
        """Tests handling and plural formatting when multiple orphaned directories are found."""
        valid_dir = self.upload_dir / str(self.valid_job.id)
        valid_dir.mkdir()

        orphan1 = self.upload_dir / "10001"
        orphan1.mkdir()
        orphan2 = self.upload_dir / "10002"
        orphan2.mkdir()

        out_dry = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", stdout=out_dry)

        output_dry = out_dry.getvalue()
        self.assertIn("Found 2 orphaned job directories (3 checked):", output_dry)
        self.assertIn(str(orphan1), output_dry)
        self.assertIn(str(orphan2), output_dry)
        self.assertIn("Dry-run complete: 2 orphaned directories found.", output_dry)

        out_del = StringIO()
        with self.settings(JOB_UPLOAD_DIR=str(self.upload_dir)):
            call_command("cleanup_orphaned_job_dirs", "--delete", stdout=out_del)

        output_del = out_del.getvalue()
        self.assertIn("Deleting 2 orphaned job directories (3 checked)...", output_del)
        self.assertIn(f"✓ Deleted: {orphan1}", output_del)
        self.assertIn(f"✓ Deleted: {orphan2}", output_del)
        self.assertIn("Cleanup complete: 2 orphaned directories removed.", output_del)

        self.assertFalse(orphan1.exists())
        self.assertFalse(orphan2.exists())
        self.assertTrue(valid_dir.exists())
