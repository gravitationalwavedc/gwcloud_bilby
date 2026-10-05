"""Safely inventory and remove the two known-invalid test EventIDs."""

import hashlib
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.utils.reindex import reindex_jobs

_TARGET_NAMES = ("GW111111_222222", "GW222222_111111")


def _cascade_counts(instance):
    """Count rows owned through direct CASCADE reverse relations."""
    counts = {}
    for relation in instance._meta.related_objects:
        if relation.on_delete is not models.CASCADE:
            continue
        accessor = relation.get_accessor_name()
        counts[relation.related_model._meta.label_lower] = getattr(instance, accessor).count()
    return dict(sorted(counts.items()))


def _event_inventory(event):
    direct_bilby = list(BilbyJob.objects.filter(event_id=event).order_by("id"))
    direct_gwflow = list(GWFlowJob.objects.filter(event_id=event).order_by("id"))
    gwflow_children = list(
        BilbyJob.objects.filter(gwflow_job_id__in=[job.id for job in direct_gwflow])
        .order_by("gwflow_job_id", "id")
    )

    return {
        "event": {
            "id": event.id,
            "event_id": event.event_id,
            "trigger_id": event.trigger_id,
            "nickname": event.nickname,
            "gps_time": event.gps_time,
        },
        "direct_bilby_children": [
            {
                "id": job.id,
                "name": job.name,
                "cascade_owned_counts": _cascade_counts(job),
            }
            for job in direct_bilby
        ],
        "direct_gwflow_children": [
            {
                "id": job.id,
                "sname": job.sname,
                "cascade_owned_counts": _cascade_counts(job),
            }
            for job in direct_gwflow
        ],
        "gwflow_bilby_children": [
            {
                "gwflow_job_id": job.gwflow_job_id,
                "id": job.id,
                "name": job.name,
                "cascade_owned_counts": _cascade_counts(job),
            }
            for job in gwflow_children
        ],
    }


def build_inventory(events):
    """Return the canonical inventory and its deterministic digest."""
    by_name = {event.event_id: event for event in events}
    inventory = {
        "targets": [
            _event_inventory(by_name[name])
            if name in by_name
            else {"event": {"event_id": name, "state": "absent"}}
            for name in _TARGET_NAMES
        ],
        "default_action": "delete EventID rows and detach direct child references",
        "optional_action": "delete only enumerated direct Bilby and GWFlow child jobs",
    }
    canonical = json.dumps(
        inventory,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return inventory, canonical, digest


class Command(BaseCommand):
    help = "Inventory or remove the two fixed known-invalid test EventIDs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the reviewed deletion. Omit for a read-only inventory.",
        )
        parser.add_argument(
            "--delete-child-jobs",
            action="store_true",
            help="Also delete the exact direct child jobs listed in the reviewed inventory.",
        )
        parser.add_argument(
            "--expected-inventory-sha256",
            help="SHA-256 printed by the reviewed dry-run inventory.",
        )

    def handle(self, *_args, **options):
        if options["delete_child_jobs"] and not options["apply"]:
            raise CommandError("--delete-child-jobs requires --apply")

        if not options["apply"]:
            events = EventID.objects.filter(event_id__in=_TARGET_NAMES).order_by("id")
            inventory, canonical, digest = build_inventory(events)
            self.stdout.write(f"cleanup_inventory={canonical}")
            self.stdout.write(f"inventory_sha256={digest}")
            self.stdout.write("mode=dry-run writes=0 reindex=0")
            return

        expected_digest = options["expected_inventory_sha256"]
        if not expected_digest:
            raise CommandError("--apply requires --expected-inventory-sha256")

        surviving_bilby_ids = []
        surviving_gwflow_ids = []
        deleted_event_ids = []
        deleted_bilby_ids = []
        deleted_gwflow_ids = []

        with transaction.atomic():
            events = list(
                EventID.objects.select_for_update()
                .filter(event_id__in=_TARGET_NAMES)
                .order_by("id")
            )
            if not events:
                self.stdout.write("cleanup_applied status=already_complete targets_absent=2")
                return

            found_names = {event.event_id for event in events}
            missing = [name for name in _TARGET_NAMES if name not in found_names]
            if missing:
                raise CommandError(
                    "cleanup precondition failed: target set is partially absent "
                    f"missing={','.join(missing)}"
                )

            invalid_state = [
                event.event_id
                for event in events
                if event.gps_time != 0.0
            ]
            if invalid_state:
                raise CommandError(
                    "cleanup precondition failed: targets must have gps_time=0.0 "
                    f"invalid={','.join(invalid_state)}"
                )

            inventory, _canonical, digest = build_inventory(events)
            if digest != expected_digest:
                raise CommandError(
                    "cleanup inventory changed: "
                    f"expected={expected_digest} actual={digest}"
                )

            direct_bilby_ids = sorted(
                child["id"]
                for target in inventory["targets"]
                for child in target["direct_bilby_children"]
            )
            direct_gwflow_ids = sorted(
                child["id"]
                for target in inventory["targets"]
                for child in target["direct_gwflow_children"]
            )
            gwflow_bilby_ids = sorted(
                child["id"]
                for target in inventory["targets"]
                for child in target["gwflow_bilby_children"]
            )
            deleted_event_ids = sorted(event.id for event in events)

            if options["delete_child_jobs"]:
                deleted_bilby_ids = direct_bilby_ids
                deleted_gwflow_ids = direct_gwflow_ids
                BilbyJob.objects.filter(id__in=deleted_bilby_ids).delete()
                GWFlowJob.objects.filter(id__in=deleted_gwflow_ids).delete()

                surviving_bilby_ids = sorted(
                    BilbyJob.objects.filter(id__in=gwflow_bilby_ids)
                    .values_list("id", flat=True)
                )
            else:
                surviving_bilby_ids = sorted(set(direct_bilby_ids + gwflow_bilby_ids))
                surviving_gwflow_ids = direct_gwflow_ids

            EventID.objects.filter(id__in=deleted_event_ids).delete()

        try:
            reindex_jobs(surviving_bilby_ids, "bilby")
            reindex_jobs(surviving_gwflow_ids, "gwflow")
        except Exception as exc:
            raise CommandError(
                "cleanup committed but reindex failed; run es_reindex_reconcile "
                f"bilby_ids={','.join(map(str, surviving_bilby_ids)) or 'none'} "
                f"gwflow_ids={','.join(map(str, surviving_gwflow_ids)) or 'none'}"
            ) from exc

        self.stdout.write(
            "cleanup_applied "
            f"deleted_event_ids={','.join(map(str, deleted_event_ids))} "
            f"deleted_bilby_ids={','.join(map(str, deleted_bilby_ids)) or 'none'} "
            f"deleted_gwflow_ids={','.join(map(str, deleted_gwflow_ids)) or 'none'} "
            f"reindexed_bilby_ids={','.join(map(str, surviving_bilby_ids)) or 'none'} "
            f"reindexed_gwflow_ids={','.join(map(str, surviving_gwflow_ids)) or 'none'}"
        )
