import math
from unittest import mock

import elasticsearch
from django.conf import settings
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.reindex import (
    ReindexCounts,
    ReindexError,
    reindex_affected_event,
    reindex_jobs,
    verify_search_trigger_time,
)


def bulk_error(stable_id, status, error_type="test_error"):
    return {
        "index": {
            "_id": str(stable_id),
            "status": status,
            "error": {"type": error_type, "reason": f"status {status}"},
        }
    }


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class TestReindexJobs(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()

    def make_bilby(self, number, **kwargs):
        defaults = {
            "user": self.user,
            "name": f"bilby-{number}",
            "ini_string": create_test_ini_string({"detectors": "['H1']"}),
        }
        defaults.update(kwargs)
        return BilbyJob.objects.create(**defaults)

    def make_gwflow(self, number, **kwargs):
        defaults = {
            "user": self.user,
            "sname": f"S2309{number:02d}a",
            "current_history_id": f"sha-{number}",
        }
        defaults.update(kwargs)
        return GWFlowJob.objects.create(**defaults)

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    def test_reindex_jobs_is_noop_when_ignore_elastic_search(self):
        with mock.patch("bilbyui.utils.reindex.get_es_client") as client:
            counts = reindex_jobs([1, 2], "bilby")

        self.assertEqual(counts, ReindexCounts(0, 0, 0))
        client.assert_not_called()

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    def test_verify_is_noop_when_ignore_elastic_search(self):
        with mock.patch("bilbyui.utils.reindex.get_es_client") as client:
            verify_search_trigger_time("bilby")

        client.assert_not_called()

    def test_counts_contract_and_success_invariant(self):
        self.assertTrue(issubclass(ReindexCounts, tuple))
        self.assertEqual(ReindexCounts._fields, ("scanned", "succeeded", "failed"))
        self.assertFalse("__add__" in ReindexCounts.__dict__)

        with mock.patch("bilbyui.utils.reindex.get_es_client") as client:
            counts = reindex_jobs([], "bilby")

        self.assertEqual(counts, ReindexCounts(0, 0, 0))
        self.assertEqual(counts.scanned, counts.succeeded + counts.failed)
        client.assert_not_called()

    def test_unknown_kind_fails_before_io(self):
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client") as client,
            mock.patch("bilbyui.utils.reindex.BilbyJob.objects.filter") as query,
        ):
            with self.assertRaises(ValueError):
                reindex_jobs([1], "other")
        client.assert_not_called()
        query.assert_not_called()

    def test_bilby_deduplicates_sorts_and_builds_full_index_actions(self):
        first = self.make_bilby(1)
        second = self.make_bilby(2)
        documents = {
            first.id: {"canonical": first.id},
            second.id: {"canonical": second.id},
        }

        def builder(job):
            return documents[job.id]

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=mock.sentinel.es),
            mock.patch("bilbyui.utils.reindex.build_bilby_es_doc", side_effect=builder) as build,
            mock.patch("bilbyui.utils.reindex.helpers.bulk", return_value=(2, [])) as bulk,
        ):
            counts = reindex_jobs([second.id, first.id, second.id], "bilby")

        self.assertEqual(counts, ReindexCounts(2, 2, 0))
        self.assertEqual([call.args[0].id for call in build.call_args_list], [first.id, second.id])
        actions = bulk.call_args.args[1]
        self.assertEqual([action["_id"] for action in actions], [first.id, second.id])
        for action in actions:
            self.assertEqual(action["_op_type"], "index")
            self.assertEqual(action["_index"], settings.ELASTIC_SEARCH_INDEX)
            self.assertEqual(action["_source"], documents[action["_id"]])
        self.assertEqual(
            bulk.call_args.kwargs,
            {
                "raise_on_error": False,
                "raise_on_exception": False,
                "stats_only": False,
            },
        )

    def test_201_ids_are_two_sorted_chunks_of_200_and_one(self):
        jobs = BilbyJob.objects.bulk_create(
            [
                BilbyJob(user=self.user, name=f"batch-{number:03d}", ini_string="[job]\n")
                for number in range(201)
            ]
        )
        ids = [job.id for job in reversed(jobs)] + [jobs[0].id]
        sizes = []

        def successful_bulk(_es, actions, **_kwargs):
            sizes.append(len(actions))
            return len(actions), []

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=mock.sentinel.es),
            mock.patch(
                "bilbyui.utils.reindex.build_bilby_es_doc",
                side_effect=lambda job: {"id": job.id},
            ),
            mock.patch("bilbyui.utils.reindex.helpers.bulk", side_effect=successful_bulk),
        ):
            counts = reindex_jobs(ids, "bilby")

        self.assertEqual(sizes, [200, 1])
        self.assertEqual(counts, ReindexCounts(201, 201, 0))

    def test_queries_use_required_select_related(self):
        bilby = self.make_bilby(1)
        gwflow = self.make_gwflow(1)

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.build_bilby_es_doc",
                return_value={"canonical": "bilby"},
            ),
            mock.patch("bilbyui.utils.reindex.helpers.bulk", return_value=(1, [])),
            self.assertNumQueries(1) as bilby_queries,
        ):
            reindex_jobs([bilby.id], "bilby")
        self.assertIn(
            'LEFT OUTER JOIN "bilbyui_eventid"',
            bilby_queries.captured_queries[0]["sql"],
        )
        self.assertIn(
            'LEFT OUTER JOIN "bilbyui_gwflowjob"',
            bilby_queries.captured_queries[0]["sql"],
        )

        metadata = {"version": "current"}
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.get_version",
                return_value=(metadata, "live"),
            ) as get_version,
            mock.patch(
                "bilbyui.utils.reindex.build_gwflow_es_doc",
                return_value={"canonical": "gwflow"},
            ) as build,
            mock.patch("bilbyui.utils.reindex.helpers.bulk", return_value=(1, [])) as bulk,
            self.assertNumQueries(1) as gwflow_queries,
        ):
            reindex_jobs([gwflow.id], "gwflow")

        self.assertIn(
            'LEFT OUTER JOIN "bilbyui_eventid"',
            gwflow_queries.captured_queries[0]["sql"],
        )
        get_version.assert_called_once_with(gwflow.sname, gwflow.current_history_id)
        build.assert_called_once()
        self.assertEqual(bulk.call_args.args[1][0]["_index"], settings.ELASTIC_SEARCH_GWFLOW_INDEX)
        self.assertEqual(bulk.call_args.args[1][0]["_source"], {"canonical": "gwflow"})

    def test_mixed_response_retries_only_retryable_items(self):
        jobs = [self.make_bilby(number) for number in range(6)]
        statuses = dict(zip([job.id for job in jobs[1:]], [429, 502, 503, 504, 400], strict=True))
        calls = []

        def bulk_side_effect(_es, actions, **_kwargs):
            calls.append([action["_id"] for action in actions])
            if len(calls) == 1:
                errors = [
                    bulk_error(stable_id, status, "mapper_parsing_exception" if status == 400 else "busy")
                    for stable_id, status in statuses.items()
                ]
                return 1, errors
            return len(actions), []

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.build_bilby_es_doc",
                side_effect=lambda job: {"id": job.id},
            ),
            mock.patch("bilbyui.utils.reindex.helpers.bulk", side_effect=bulk_side_effect),
            mock.patch("bilbyui.utils.reindex.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(
                ReindexError,
                r"scanned=6 succeeded=5 failed=1",
            ):
                reindex_jobs([job.id for job in jobs], "bilby")

        self.assertEqual(calls[0], [job.id for job in jobs])
        self.assertEqual(calls[1], [job.id for job in jobs[1:5]])
        sleep.assert_called_once_with(0.5)

    def test_404_409_and_mapping_errors_are_permanent(self):
        jobs = [self.make_bilby(number) for number in range(3)]
        errors = [
            bulk_error(jobs[0].id, 404),
            bulk_error(jobs[1].id, 409),
            bulk_error(jobs[2].id, 400, "mapper_parsing_exception"),
        ]
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.build_bilby_es_doc",
                side_effect=lambda job: {"id": job.id},
            ),
            mock.patch(
                "bilbyui.utils.reindex.helpers.bulk",
                return_value=(0, errors),
            ) as bulk,
            mock.patch("bilbyui.utils.reindex.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(ReindexError, r"scanned=3 succeeded=0 failed=3"):
                reindex_jobs([job.id for job in jobs], "bilby")

        self.assertEqual(bulk.call_count, 1)
        sleep.assert_not_called()

    def test_retry_exhaustion_is_exactly_three_calls_and_two_sleeps(self):
        job = self.make_bilby(1)
        response = (0, [bulk_error(job.id, 429)])
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.build_bilby_es_doc",
                return_value={"id": job.id},
            ),
            mock.patch(
                "bilbyui.utils.reindex.helpers.bulk",
                return_value=response,
            ) as bulk,
            mock.patch("bilbyui.utils.reindex.time.sleep") as sleep,
        ):
            with self.assertRaisesRegex(ReindexError, r"scanned=1 succeeded=0 failed=1"):
                reindex_jobs([job.id], "bilby")

        self.assertEqual(bulk.call_count, 3)
        self.assertEqual(sleep.call_args_list, [mock.call(0.5), mock.call(1)])
        self.assertNotIn(mock.call(2), sleep.call_args_list)

    def test_transport_error_retries_current_pending_subset(self):
        jobs = [self.make_bilby(number) for number in range(2)]
        calls = []

        def side_effect(_es, actions, **_kwargs):
            calls.append([action["_id"] for action in actions])
            if len(calls) == 1:
                return 1, [bulk_error(jobs[1].id, 503)]
            if len(calls) == 2:
                raise elasticsearch.ConnectionError("connection lost")
            return 1, []

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.build_bilby_es_doc",
                side_effect=lambda job: {"id": job.id},
            ),
            mock.patch("bilbyui.utils.reindex.helpers.bulk", side_effect=side_effect),
            mock.patch("bilbyui.utils.reindex.time.sleep") as sleep,
        ):
            counts = reindex_jobs([job.id for job in jobs], "bilby")

        self.assertEqual(counts, ReindexCounts(2, 2, 0))
        self.assertEqual(calls, [[jobs[0].id, jobs[1].id], [jobs[1].id], [jobs[1].id]])
        self.assertEqual(sleep.call_args_list, [mock.call(0.5), mock.call(1)])

    def test_whole_call_transport_error_retries_pending_subset(self):
        jobs = [self.make_bilby(number) for number in range(2)]
        calls = []

        def side_effect(_es, actions, **_kwargs):
            calls.append([action["_id"] for action in actions])
            if len(calls) == 1:
                return 1, [bulk_error(jobs[1].id, 503)]
            if len(calls) == 2:
                raise elasticsearch.TransportError("transport error")
            return 1, []

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.build_bilby_es_doc",
                side_effect=lambda job: {"id": job.id},
            ),
            mock.patch("bilbyui.utils.reindex.helpers.bulk", side_effect=side_effect),
            mock.patch("bilbyui.utils.reindex.time.sleep") as sleep,
        ):
            counts = reindex_jobs([job.id for job in jobs], "bilby")

        self.assertEqual(counts, ReindexCounts(2, 2, 0))
        self.assertEqual(
            calls,
            [[jobs[0].id, jobs[1].id], [jobs[1].id], [jobs[1].id]],
        )
        self.assertEqual(sleep.call_args_list, [mock.call(0.5), mock.call(1)])

    def test_missing_row_and_metadata_failure_raise_without_partial_document(self):
        gwflow = self.make_gwflow(1)
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client"),
            mock.patch(
                "bilbyui.utils.reindex.get_version",
                return_value=(None, "down"),
            ),
            mock.patch("bilbyui.utils.reindex.build_gwflow_es_doc") as build,
            mock.patch("bilbyui.utils.reindex.helpers.bulk") as bulk,
        ):
            with self.assertRaisesRegex(ReindexError, r"scanned=2 succeeded=0 failed=2"):
                reindex_jobs([gwflow.id, gwflow.id + 1000], "gwflow")
        build.assert_not_called()
        bulk.assert_not_called()


class TestReindexAffectedEvent(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()

    def bilby(self, name, **kwargs):
        return BilbyJob.objects.create(
            user=self.user,
            name=name,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            **kwargs,
        )

    def test_three_set_fanout_union_dedup_bounded_and_accumulated(self):
        event = EventID.objects.create(event_id="G1001", trigger_id="G1001")
        other = EventID.objects.create(event_id="G1002", trigger_id="G1002")
        linked = GWFlowJob.objects.create(user=self.user, sname="S230901a", event_id=event)
        unrelated_gwflow = GWFlowJob.objects.create(user=self.user, sname="S230902a", event_id=other)
        direct = self.bilby("direct", event_id=event)
        child = self.bilby("child", gwflow_job=linked)
        overlap = self.bilby("overlap", event_id=event, gwflow_job=linked)
        unrelated = self.bilby("unrelated", event_id=other, gwflow_job=unrelated_gwflow)
        calls = []

        def fake_reindex(ids, kind):
            calls.append((list(ids), kind))
            return ReindexCounts(len(ids), len(ids), 0)

        with mock.patch("bilbyui.utils.reindex.reindex_jobs", side_effect=fake_reindex):
            counts = reindex_affected_event(event.id)

        bilby_ids = [stable_id for ids, kind in calls if kind == "bilby" for stable_id in ids]
        gwflow_ids = [stable_id for ids, kind in calls if kind == "gwflow" for stable_id in ids]
        self.assertEqual(bilby_ids, sorted([direct.id, child.id, overlap.id]))
        self.assertEqual(bilby_ids.count(overlap.id), 1)
        self.assertEqual(gwflow_ids, [linked.id])
        self.assertNotIn(unrelated.id, bilby_ids)
        self.assertNotIn(unrelated_gwflow.id, gwflow_ids)
        self.assertTrue(all(len(ids) <= 200 for ids, _kind in calls))
        self.assertEqual(counts, ReindexCounts(4, 4, 0))


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class TestVerifySearchTriggerTime(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()

    def bilby(self, name, **kwargs):
        return BilbyJob.objects.create(
            user=self.user,
            name=name,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            **kwargs,
        )

    @staticmethod
    def mget_response(rows, sources):
        return {
            "docs": [
                {"_id": str(row.id), "found": True, "_source": sources[row.id]}
                for row in rows
            ]
        }

    def test_bilby_uses_maximum_of_all_four_raw_fields(self):
        direct_event = EventID.objects.create(event_id="G2001", gps_time=20.0)
        parent_event = EventID.objects.create(event_id="G2002", gps_time=40.0)
        parent = GWFlowJob.objects.create(
            user=self.user,
            sname="S231001a",
            event_id=parent_event,
            trigger_time=30.0,
        )
        job = self.bilby(
            "four-fields",
            event_id=direct_event,
            gwflow_job=parent,
            trigger_time=10.0,
        )
        es = mock.Mock()
        es.mget.return_value = self.mget_response(
            [job],
            {job.id: {"searchTriggerTime": 40.0}},
        )

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
            mock.patch("bilbyui.utils.reindex.build_bilby_es_doc") as builder,
        ):
            verify_search_trigger_time("bilby")

        builder.assert_not_called()
        es.mget.assert_called_once_with(index=settings.ELASTIC_SEARCH_INDEX, ids=[job.id])

    def test_gwflow_uses_maximum_of_both_raw_fields(self):
        event = EventID.objects.create(event_id="G2101", gps_time=60.0)
        job = GWFlowJob.objects.create(
            user=self.user,
            sname="S231101a",
            event_id=event,
            trigger_time=50.0,
        )
        es = mock.Mock()
        es.mget.return_value = self.mget_response(
            [job],
            {job.id: {"_gwcloud": {"searchTriggerTime": 60.0}}},
        )

        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
            mock.patch("bilbyui.utils.reindex.build_gwflow_es_doc") as builder,
        ):
            verify_search_trigger_time("gwflow")

        builder.assert_not_called()
        es.mget.assert_called_once_with(
            index=settings.ELASTIC_SEARCH_GWFLOW_INDEX,
            ids=[job.id],
        )

    def test_absent_field_is_allowed_only_without_finite_non_boolean_input(self):
        absent = self.bilby("absent", trigger_time=None)
        invalid_source = self.bilby("invalid-source", trigger_time=math.nan)
        es = mock.Mock()
        es.mget.return_value = self.mget_response(
            [absent, invalid_source],
            {absent.id: {}, invalid_source.id: {}},
        )
        with mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es):
            verify_search_trigger_time("bilby")

        present = self.bilby("present", trigger_time=1.0)
        es.mget.return_value = self.mget_response([present], {present.id: {}})
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
            self.assertRaises(ReindexError),
        ):
            verify_search_trigger_time("bilby")

    def test_rejects_missing_document_unexpected_path_and_bad_values(self):
        bad_values = [None, True, "12", math.nan, math.inf]
        for number, value in enumerate(bad_values):
            with self.subTest(value=value):
                BilbyJob.objects.all().delete()
                job = self.bilby(f"bad-{number}", trigger_time=12.0)
                es = mock.Mock()
                es.mget.return_value = self.mget_response(
                    [job],
                    {job.id: {"searchTriggerTime": value}},
                )
                with (
                    mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
                    self.assertRaises(ReindexError),
                ):
                    verify_search_trigger_time("bilby")

        BilbyJob.objects.all().delete()
        job = self.bilby("unexpected", trigger_time=12.0)
        es = mock.Mock()
        es.mget.return_value = self.mget_response(
            [job],
            {job.id: {"_gwcloud": {"searchTriggerTime": 12.0}}},
        )
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
            self.assertRaises(ReindexError),
        ):
            verify_search_trigger_time("bilby")

        es.mget.return_value = {"docs": [{"_id": str(job.id), "found": False}]}
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
            self.assertRaises(ReindexError),
        ):
            verify_search_trigger_time("bilby")

    def test_rejects_mismatch_and_unexpected_field_when_no_expected_value(self):
        job = self.bilby("mismatch", trigger_time=12.0)
        es = mock.Mock()
        es.mget.return_value = self.mget_response(
            [job],
            {job.id: {"searchTriggerTime": 13.0}},
        )
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
            self.assertRaises(ReindexError),
        ):
            verify_search_trigger_time("bilby")

        job.trigger_time = None
        job.save(update_fields=["trigger_time"])
        es.mget.return_value = self.mget_response(
            [job],
            {job.id: {"searchTriggerTime": 13.0}},
        )
        with (
            mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es),
            self.assertRaises(ReindexError),
        ):
            verify_search_trigger_time("bilby")

    def test_mget_pages_are_bounded_to_200(self):
        jobs = BilbyJob.objects.bulk_create(
            [
                BilbyJob(
                    user=self.user,
                    name=f"verify-{number:03d}",
                    ini_string=create_test_ini_string({"detectors": "['H1']"}),
                    trigger_time=float(number),
                )
                for number in range(201)
            ]
        )
        es = mock.Mock()

        def mget(*, index, ids):
            self.assertEqual(index, settings.ELASTIC_SEARCH_INDEX)
            self.assertLessEqual(len(ids), 200)
            expected = {job.id: job.trigger_time for job in jobs}
            return {
                "docs": [
                    {
                        "_id": str(stable_id),
                        "found": True,
                        "_source": {"searchTriggerTime": expected[stable_id]},
                    }
                    for stable_id in ids
                ]
            }

        es.mget.side_effect = mget
        with mock.patch("bilbyui.utils.reindex.get_es_client", return_value=es):
            verify_search_trigger_time("bilby")

        self.assertEqual([len(call.kwargs["ids"]) for call in es.mget.call_args_list], [200, 1])
