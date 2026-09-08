"""Shared canonical fixture module for GWFlow ES migration and service tests.

Implements the 5-document canonical fixture matrix from issue #71 once, so the
migration tests (and future service tests) reuse a single dataset instead of
maintaining near-identical copies.

Each entry in FIXTURE_MATRIX describes a GWFlowJob row and the portal
metadata used to build its ES document. build_canonical_fixtures() creates the
model rows and their built documents (via build_gwflow_es_doc) and returns
them keyed by the document ``_id`` (the GWFlowJob primary key).
"""

from datetime import UTC, datetime

from bilbyui.models import EventID, GWFlowJob
from bilbyui.utils.gwflow_es import build_gwflow_es_doc

# Canonical 5-document fixture matrix (issue #71). ``review_statuses`` and
# ``last_updated_time`` are the expected envelope values derived from the
# model row + metadata; ``metadata`` is the raw portal payload passed to the
# builder.
FIXTURE_MATRIX = [
    {
        "id": 1,
        "sname": "S230601ag",
        "ligo_only": False,
        "is_pruned": False,
        "libraries": ["cbc-workflow-o4a"],
        "event_trigger_id": "S230601ag",
        "current_history_timestamp": datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
        "last_updated_time": "2026-08-31T12:00:00+00:00",
        "review_statuses": ["approved"],
        "metadata": {
            "ParameterEstimation": {
                "results": [
                    {
                        "uid": "pe-1",
                        "inference_software": "bilby",
                        "review_status": "approved",
                    }
                ]
            }
        },
    },
    {
        "id": 2,
        "sname": "S230602ag",
        "ligo_only": False,
        "is_pruned": False,
        "libraries": ["cbc-workflow-o4c"],
        "event_trigger_id": "S230602ag",
        "current_history_timestamp": datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC),
        "last_updated_time": "2026-08-01T00:00:00+00:00",
        "review_statuses": ["pending", "reviewed"],
        "metadata": {
            "TGR": [
                {"uid": "tgr-1", "software": "pycbc", "review_status": "pending"},
                {"uid": "tgr-2", "software": "pycbc", "review_status": "reviewed"},
            ]
        },
    },
    {
        "id": 3,
        "sname": "S230603ag",
        "ligo_only": True,
        "is_pruned": False,
        "libraries": [],
        "event_trigger_id": "S230603ag",
        "current_history_timestamp": datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC),
        "last_updated_time": "2026-07-01T00:00:00+00:00",
        "review_statuses": ["approved"],
        "metadata": {
            "GraceDB": {"Events": [{"uid": "G197392"}]},
            "ParameterEstimation": {"results": [{"uid": "pe-3", "review_status": "approved"}]},
        },
    },
    {
        "id": 4,
        "sname": "S230604ag",
        "ligo_only": False,
        "is_pruned": True,
        "libraries": ["cbc-workflow-o4a"],
        "event_trigger_id": None,
        "current_history_timestamp": datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC),
        "last_updated_time": "2026-06-01T00:00:00+00:00",
        "review_statuses": [],
        "metadata": {"UnknownSection": {"x": 1}},
    },
    {
        "id": 5,
        "sname": "S230605ag",
        "ligo_only": False,
        "is_pruned": False,
        "libraries": ["cbc-workflow-o4a", "cbc-workflow-o4c"],
        "event_trigger_id": "S230605ag",
        "current_history_timestamp": None,
        "last_updated_time": None,
        "review_statuses": ["Approved"],
        "metadata": {
            "ParameterEstimation": {
                "results": [
                    {
                        "uid": "pe-5",
                        "inference_software": "bilby",
                        "review_status": "Approved",
                    }
                ]
            }
        },
    },
]


def build_canonical_fixtures(testcase_cls):
    """Create the five canonical GWFlowJob rows and their built ES documents.

    ``testcase_cls`` must be a BilbyTestCase subclass exposing ``create_user``.
    Returns a dict keyed by document ``_id`` (the GWFlowJob pk) with entries
    ``{"id", "job", "doc", "spec"}`` where ``doc`` is the real output of
    build_gwflow_es_doc for that job.
    """
    user = testcase_cls.create_user(id=900, name="Fixture User", primary_email="fixture@example.com")
    fixtures = {}
    for spec in FIXTURE_MATRIX:
        event = None
        if spec["event_trigger_id"]:
            event = EventID.objects.create(
                event_id=f"GW123456_{spec['id']:06d}",
                trigger_id=spec["event_trigger_id"],
                nickname=f"Event {spec['id']}",
                gps_time=1126259462.4 + spec["id"],
            )
        job = GWFlowJob.objects.create(
            id=spec["id"],
            sname=spec["sname"],
            user=user,
            libraries=spec["libraries"],
            current_history_id=f"hist-{spec['id']:03d}",
            current_history_timestamp=spec["current_history_timestamp"],
            ligo_only=spec["ligo_only"],
            is_pruned=spec["is_pruned"],
            event_id=event,
        )
        doc = build_gwflow_es_doc(job, spec["metadata"])
        fixtures[spec["id"]] = {"id": spec["id"], "job": job, "doc": doc, "spec": spec}
    return fixtures


def assert_doc_matches_spec(testcase, doc, spec):
    """Assert a built ES document matches its canonical fixture spec."""
    envelope = doc["_gwcloud"]
    testcase.assertEqual(
        set(envelope.keys()),
        {"sname", "libraries", "isPruned", "ligoOnly", "lastUpdatedTime", "reviewStatuses", "eventTriggerId"},
    )
    testcase.assertEqual(envelope["sname"], spec["sname"])
    testcase.assertEqual(envelope["libraries"], spec["libraries"])
    testcase.assertEqual(envelope["isPruned"], spec["is_pruned"])
    testcase.assertEqual(envelope["ligoOnly"], spec["ligo_only"])
    testcase.assertEqual(envelope["reviewStatuses"], spec["review_statuses"])
    testcase.assertEqual(envelope["lastUpdatedTime"], spec["last_updated_time"])
    testcase.assertEqual(envelope["eventTriggerId"], spec["event_trigger_id"])
    testcase.assertEqual(doc["metadata"], spec["metadata"])


def assert_defect_queries_assertable(testcase, docs_by_id):
    """Assert the reimported docs carry the fields the defect queries need.

    The four defect queries from issue #71 (library filter, case-sensitive
    review-status filter, ``_gwcloud.libraries:*``, ``metadata.*`` fielded
    query) plus the ``_gwcloud.eventTriggerId:*`` exists query, the
    updated-past-30-days range, and the non-LIGO option aggregation are all
    expressible against the canonical fixture matrix. Full list-query
    construction is issue #72; here we only verify the fields are present
    with the correct values so those queries would work.
    """
    d1 = docs_by_id[1]["doc"]
    d2 = docs_by_id[2]["doc"]
    d3 = docs_by_id[3]["doc"]
    d4 = docs_by_id[4]["doc"]
    d5 = docs_by_id[5]["doc"]

    # Library filter: docs 1, 4, 5 contain cbc-workflow-o4a; doc 2 has o4c;
    # doc 3 has none.
    testcase.assertIn("cbc-workflow-o4a", d1["_gwcloud"]["libraries"])
    testcase.assertIn("cbc-workflow-o4a", d4["_gwcloud"]["libraries"])
    testcase.assertIn("cbc-workflow-o4a", d5["_gwcloud"]["libraries"])
    testcase.assertIn("cbc-workflow-o4c", d2["_gwcloud"]["libraries"])
    testcase.assertEqual(d3["_gwcloud"]["libraries"], [])

    # _gwcloud.libraries:* exists query: only doc 3 has an empty list.
    testcase.assertTrue(d1["_gwcloud"]["libraries"])
    testcase.assertTrue(d2["_gwcloud"]["libraries"])
    testcase.assertFalse(d3["_gwcloud"]["libraries"])
    testcase.assertTrue(d4["_gwcloud"]["libraries"])
    testcase.assertTrue(d5["_gwcloud"]["libraries"])

    # Case-sensitive review-status filter: "approved" matches docs 1 and 3;
    # "Approved" (capitalised) matches only doc 5; docs 2 and 4 differ.
    testcase.assertIn("approved", d1["_gwcloud"]["reviewStatuses"])
    testcase.assertIn("approved", d3["_gwcloud"]["reviewStatuses"])
    testcase.assertIn("Approved", d5["_gwcloud"]["reviewStatuses"])
    testcase.assertNotIn("Approved", d1["_gwcloud"]["reviewStatuses"])
    testcase.assertNotIn("approved", d5["_gwcloud"]["reviewStatuses"])
    testcase.assertEqual(d4["_gwcloud"]["reviewStatuses"], [])

    # metadata.* fielded query: inference_software "bilby" on docs 1 and 5;
    # TGR software "pycbc" on doc 2; GraceDB uid on doc 3; UnknownSection on
    # doc 4.
    testcase.assertEqual(d1["metadata"]["ParameterEstimation"]["results"][0]["inference_software"], "bilby")
    testcase.assertEqual(d5["metadata"]["ParameterEstimation"]["results"][0]["inference_software"], "bilby")
    testcase.assertEqual(d2["metadata"]["TGR"][0]["software"], "pycbc")
    testcase.assertEqual(d3["metadata"]["GraceDB"]["Events"][0]["uid"], "G197392")
    testcase.assertEqual(d4["metadata"]["UnknownSection"]["x"], 1)

    # _gwcloud.eventTriggerId:* exists query: docs 1, 2, 3, 5 have one;
    # doc 4 has none.
    for fx_id in (1, 2, 3, 5):
        testcase.assertIsNotNone(docs_by_id[fx_id]["doc"]["_gwcloud"]["eventTriggerId"])
    testcase.assertIsNone(d4["_gwcloud"]["eventTriggerId"])

    # updated-past-30-days: doc 1 (2026-08-31) is within 30 days of the
    # reference date; docs 2-4 are older; doc 5 has no timestamp.
    reference = datetime(2026, 9, 8, tzinfo=UTC)
    d1_parsed = datetime.fromisoformat(d1["_gwcloud"]["lastUpdatedTime"])
    testcase.assertLessEqual((reference - d1_parsed).days, 30)
    for fx_id in (2, 3, 4):
        ts = docs_by_id[fx_id]["doc"]["_gwcloud"]["lastUpdatedTime"]
        testcase.assertIsNotNone(ts)
        parsed = datetime.fromisoformat(ts)
        testcase.assertGreater((reference - parsed).days, 30)
    testcase.assertIsNone(d5["_gwcloud"]["lastUpdatedTime"])

    # Non-LIGO option aggregation: ligoOnly:false on docs 1, 2, 4, 5; doc 3
    # is LIGO-only.
    for fx_id in (1, 2, 4, 5):
        testcase.assertFalse(docs_by_id[fx_id]["doc"]["_gwcloud"]["ligoOnly"])
    testcase.assertTrue(d3["_gwcloud"]["ligoOnly"])


# Expected list-query results for the canonical fixture matrix (issue #72 query
# assertion table). Each entry is (label, list_gwflow_jobs kwargs, expected
# ordered document ids) for a public, non-pruned query (the default for a
# non-LIGO user). ``time_range`` assertions are evaluated against the fixed
# reference date 2026-09-08 (see the integration test, which pins
# timezone.now). Shared so migration and service integration tests assert the
# same expected behaviour without duplicating the table.
QUERY_ASSERTIONS = [
    ("library cbc-workflow-o4a", {"library": "cbc-workflow-o4a"}, [1, 5]),
    ("review-status approved", {"review_status": "approved"}, [1]),
    ("review-status Approved", {"review_status": "Approved"}, [5]),
    ("_gwcloud.libraries:*", {"search": "_gwcloud.libraries:*"}, [1, 2, 5]),
    (
        "metadata.ParameterEstimation.results.inference_software:bilby",
        {"search": "metadata.ParameterEstimation.results.inference_software:bilby"},
        [1, 5],
    ),
    ("_gwcloud.eventTriggerId:*", {"search": "_gwcloud.eventTriggerId:*"}, [1, 2, 5]),
    ("updated past 30 days", {"time_range": "1m"}, [1]),
]

# Reference date used to make the "updated past 30 days" assertion
# deterministic (fixture 1 is within 31 days; fixtures 2-4 are older;
# fixture 5 has no timestamp).
QUERY_REFERENCE_DATE = datetime(2026, 9, 8, tzinfo=UTC)
