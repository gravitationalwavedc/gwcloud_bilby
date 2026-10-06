"""Validate Elasticsearch field and visibility policy parity."""

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from bilbyui.utils.embargo import get_embargo_start
from bilbyui.utils.es_policy_validation import (
    collect_shadow_comparison,
    collect_visibility_parity,
)
from bilbyui.utils.reindex import collect_search_trigger_time_parity

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


class Command(BaseCommand):
    help = "Validate Elasticsearch trigger-time fields and embargo visibility policy parity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=("bilby", "gwflow", "all"),
            default="all",
        )
        parser.add_argument("--threshold", type=float, default=None)
        parser.add_argument("--batch", type=int, default=200)
        parser.add_argument("--report", default=None)
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--environment", default=None)
        parser.add_argument("--release-id", default=None)

    def execute(self, *args, **options):
        self._exit_code = EXIT_OK
        super().execute(*args, **options)
        if self._exit_code != EXIT_OK:
            raise CommandError(
                f"es_policy_validate exited with code {self._exit_code}",
                returncode=self._exit_code,
            )
        return self._exit_code

    def handle(self, *args, **options):
        batch = options["batch"]
        if not 1 <= batch <= 200:
            raise CommandError("--batch must be between 1 and 200", returncode=EXIT_USAGE)

        if getattr(settings, "IGNORE_ELASTIC_SEARCH", False):
            raise CommandError(
                "Elasticsearch is disabled; policy validation cannot run.",
                returncode=EXIT_FAILURE,
            )

        threshold = options["threshold"]
        if threshold is not None and not math.isfinite(threshold):
            raise CommandError("--threshold must be finite", returncode=EXIT_USAGE)
        if threshold is None:
            threshold = get_embargo_start()
            if threshold is None:
                raise CommandError(
                    "A finite comparison threshold is required.",
                    returncode=EXIT_USAGE,
                )

        kinds = ("bilby", "gwflow") if options["kind"] == "all" else (options["kind"],)
        kind_results = {}

        for kind in kinds:
            checks = {}

            try:
                parity = collect_search_trigger_time_parity(kind, batch=batch)
                checks["field_parity"] = {
                    "status": "pass" if parity.failures == 0 else "fail",
                    "checked": parity.checked,
                    "failures": parity.failures,
                }
            except Exception as exc:
                checks["field_parity"] = {
                    "status": "error",
                    "error": str(exc),
                }

            try:
                visibility = collect_visibility_parity(kind, threshold, batch=batch)
                checks["visibility_parity"] = {
                    "status": "pass" if visibility.ok else "fail",
                    "orm_public": visibility.orm_public,
                    "es_public": visibility.es_public,
                    "missing_in_es": visibility.missing_in_es,
                    "extra_in_es": visibility.extra_in_es,
                    "classes": visibility.classes,
                }
            except Exception as exc:
                checks["visibility_parity"] = {
                    "status": "error",
                    "error": str(exc),
                }

            try:
                shadow = collect_shadow_comparison(kind, threshold, batch=batch)
                checks["shadow"] = {
                    "status": "pass" if shadow.ok else "fail",
                    "flag_drift": shadow.flag_drift,
                    "simulation": shadow.simulation,
                    "unknown_trigger": shadow.unknown_trigger,
                    "threshold_boundary": shadow.threshold_boundary,
                    "unexplained": shadow.unexplained,
                    "new_exposures": shadow.new_exposures,
                    "total_mismatches": shadow.total_mismatches,
                }
            except Exception as exc:
                checks["shadow"] = {
                    "status": "error",
                    "error": str(exc),
                }

            kind_results[kind] = checks

        overall = (
            "pass"
            if all(check["status"] == "pass" for checks in kind_results.values() for check in checks.values())
            else "fail"
        )
        result = {
            "environment": options["environment"],
            "release_id": options["release_id"],
            "threshold": threshold,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "indexes": {
                "bilby": settings.ELASTIC_SEARCH_INDEX,
                "gwflow": settings.ELASTIC_SEARCH_GWFLOW_INDEX,
            },
            "kinds": kind_results,
            "overall": overall,
        }
        encoded = json.dumps(result, indent=2)

        for kind, checks in kind_results.items():
            summary = " ".join(f"{name}={check['status']}" for name, check in checks.items())
            self.stdout.write(f"{kind}: {summary}")

        if options["report"]:
            Path(options["report"]).write_text(f"{encoded}\n", encoding="utf-8")
        if options["json"]:
            self.stdout.write(encoded)

        self._exit_code = EXIT_OK if overall == "pass" else EXIT_FAILURE
