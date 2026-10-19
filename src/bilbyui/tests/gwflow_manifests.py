"""Tuple manifests proving GWFlow reconciliation preserves protected identities."""

from bilbyui.models import BilbyJob, EventID, ExternalBilbyJob, GWFlowJob


def _identity_tuple(instance):
    if isinstance(instance, GWFlowJob):
        return ("GWFlowJob", instance.pk, instance.user_id, instance.event_id_id)
    if isinstance(instance, BilbyJob):
        return (
            "BilbyJob",
            instance.pk,
            instance.user_id,
            instance.event_id_id,
            instance.gwflow_job_id,
        )
    if isinstance(instance, ExternalBilbyJob):
        return (
            "ExternalBilbyJob",
            instance.pk,
            instance.job.user_id,
            instance.job_id,
        )
    if isinstance(instance, EventID):
        return ("EventID", instance.pk, instance.trigger_id)
    raise TypeError(f"Unsupported protected model: {type(instance).__name__}")


def protected_identity_manifest():
    """Return the complete, sorted protected-identity tuple set."""
    rows = []
    rows.extend(_identity_tuple(row) for row in GWFlowJob.objects.all())
    rows.extend(_identity_tuple(row) for row in BilbyJob.objects.all())
    rows.extend(_identity_tuple(row) for row in ExternalBilbyJob.objects.select_related("job").all())
    rows.extend(_identity_tuple(row) for row in EventID.objects.all())
    return sorted(rows, key=repr)


def assert_preserved(before, after):
    """Raise an actionable assertion when any protected tuple differs."""
    before_set = set(before)
    after_set = set(after)
    if before_set != after_set or len(before) != len(after):
        deleted_or_changed = sorted(before_set - after_set, key=repr)
        created_or_changed = sorted(after_set - before_set, key=repr)
        raise AssertionError(
            "Protected identity manifest changed: "
            f"deleted_or_changed={deleted_or_changed!r}; "
            f"created_or_changed={created_or_changed!r}; "
            f"before_length={len(before)}; after_length={len(after)}"
        )


def assert_manifest_can_fail():
    """Exercise deletion, owner-change, and FK-change comparator failures."""
    baseline = [
        ("BilbyJob", 7, 10, 20, 30),
        ("GWFlowJob", 30, 10, 20),
    ]
    variants = {
        "deleted row": baseline[1:],
        "changed owner": [("BilbyJob", 7, 11, 20, 30), baseline[1]],
        "changed FK": [("BilbyJob", 7, 10, 21, 30), baseline[1]],
    }
    evidence = {}
    for label, changed in variants.items():
        try:
            assert_preserved(baseline, changed)
        except AssertionError as error:
            evidence[label] = str(error)
        else:
            raise AssertionError(f"Comparator failed to detect {label}")
    return evidence
