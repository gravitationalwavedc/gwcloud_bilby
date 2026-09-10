import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from bilbyui.models import BilbyJob

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scan JOB_UPLOAD_DIR on Lustre and purge directories with no matching BilbyJob in the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            default=False,
            help="Delete orphaned directories. If omitted, runs in dry-run mode.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Simulate cleanup without deleting directories.",
        )

    def _get_upload_dir(self) -> Path | None:
        """Validate and return the configured JOB_UPLOAD_DIR path, or None if invalid."""
        upload_dir_setting = getattr(settings, "JOB_UPLOAD_DIR", None)
        if not upload_dir_setting:
            msg = "JOB_UPLOAD_DIR setting is not configured."
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
            return None

        upload_dir = Path(upload_dir_setting)
        if not upload_dir.exists() or not upload_dir.is_dir():
            msg = f"JOB_UPLOAD_DIR directory does not exist: {upload_dir}"
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
            return None

        return upload_dir

    def _find_orphaned_dirs(self, upload_dir: Path) -> tuple[int, list[Path]]:
        """Scan upload_dir for numeric subdirectories and return candidate count and orphan paths."""
        candidate_map: dict[int, Path] = {
            int(entry.name): entry
            for entry in upload_dir.iterdir()
            if entry.is_dir() and entry.name.isdigit()
        }

        if not candidate_map:
            return 0, []

        existing_ids = set(
            BilbyJob.objects.filter(id__in=list(candidate_map.keys())).values_list("id", flat=True)
        )
        orphan_ids = sorted([cid for cid in candidate_map if cid not in existing_ids])
        orphan_dirs = [candidate_map[cid] for cid in orphan_ids]
        return len(candidate_map), orphan_dirs

    def _report_dry_run(self, candidate_count: int, orphan_dirs: list[Path]) -> None:
        """Output candidate list and summary in dry-run mode without modifying filesystem."""
        count = len(orphan_dirs)
        plural = "y" if count == 1 else "ies"
        self.stdout.write(
            f"Found {count} orphaned job director{plural} ({candidate_count} checked):"
        )
        for path in orphan_dirs:
            logger.info("Found orphaned job directory: %s", path)
            self.stdout.write(f"  - {path}")

        logger.info("Dry-run complete: %d orphaned directories found.", count)
        self.stdout.write(
            self.style.NOTICE(
                f"\nDry-run complete: {count} orphaned director{plural} found. "
                "No files were deleted. Pass --delete to purge them."
            )
        )

    def _delete_orphans(self, candidate_count: int, orphan_dirs: list[Path]) -> None:
        """Purge confirmed orphaned directories from filesystem and report results."""
        count = len(orphan_dirs)
        plural = "y" if count == 1 else "ies"
        self.stdout.write(
            f"Deleting {count} orphaned job director{plural} ({candidate_count} checked)..."
        )
        deleted_count = 0
        for path in orphan_dirs:
            shutil.rmtree(path, ignore_errors=True)
            deleted_count += 1
            logger.info("Deleted orphaned job directory: %s", path)
            self.stdout.write(self.style.SUCCESS(f"  ✓ Deleted: {path}"))

        deleted_plural = "y" if deleted_count == 1 else "ies"
        logger.info("Cleanup complete: %d orphaned directories removed.", deleted_count)
        self.stdout.write(
            self.style.SUCCESS(
                f"\nCleanup complete: {deleted_count} orphaned director{deleted_plural} removed."
            )
        )

    def handle(self, *_args, **options):
        upload_dir = self._get_upload_dir()
        if not upload_dir:
            return

        candidate_count, orphan_dirs = self._find_orphaned_dirs(upload_dir)
        if candidate_count == 0:
            msg = "0 directories checked. No candidate job directories found."
            logger.info(msg)
            self.stdout.write(msg)
            return

        if not orphan_dirs:
            msg = f"{candidate_count} directories checked. 0 orphaned directories found."
            logger.info(msg)
            self.stdout.write(self.style.SUCCESS(msg))
            return

        is_dry_run = options.get("dry_run", False) or not options.get("delete", False)
        if is_dry_run:
            self._report_dry_run(candidate_count, orphan_dirs)
        else:
            self._delete_orphans(candidate_count, orphan_dirs)
