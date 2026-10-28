import json
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import DatabaseError
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, GWFlowJob, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class _MockResponse:
    def __init__(self, payload, status_code):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TestEsIngestCommand(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        for i in range(3):
            BilbyJob.objects.create(
                user_id=cls.user.id,
                name=f"Test_Job_{i}",
                description="Test job description",
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

    def test_es_ingest_success(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True) as mock_save:
            call_command("es_ingest", stdout=out)

        self.assertEqual(mock_save.call_count, 3)
        output = out.getvalue()
        self.assertIn("Ingestion complete: 3 succeeded, 0 failed", output)
        self.assertIn("✓ Job", output)

    def test_es_ingest_drops_bilby_index_before_ingesting(self):
        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.get_es_client") as mock_get_es:
            mock_es = mock_get_es.return_value
            with override_settings(IGNORE_ELASTIC_SEARCH=False):
                with mock.patch.object(BilbyJob, "save", autospec=True):
                    call_command("es_ingest", stdout=out)

        mock_es.indices.delete.assert_called_once_with(
            index="gwcloud-bilbyjob",
            ignore_unavailable=True,
        )
        self.assertIn("Ingestion complete: 3 succeeded, 0 failed", out.getvalue())

    def test_es_ingest_skips_index_drop_when_es_ignored(self):
        out = StringIO()
        with mock.patch("bilbyui.management.commands.es_ingest.get_es_client") as mock_get_es:
            with mock.patch.object(BilbyJob, "save", autospec=True):
                call_command("es_ingest", stdout=out)

        mock_get_es.assert_not_called()
        self.assertIn("Ingestion complete: 3 succeeded, 0 failed", out.getvalue())

    def test_es_ingest_error(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True, side_effect=DatabaseError("boom")):
            call_command("es_ingest", stdout=out)

        output = out.getvalue()
        self.assertIn("Ingestion complete: 0 succeeded, 3 failed", output)
        self.assertIn("✗ Job", output)
        self.assertIn("boom", output)

    def test_es_ingest_continues_after_non_database_error(self):
        out = StringIO()
        with mock.patch.object(BilbyJob, "save", autospec=True, side_effect=[ValueError("bad detectors"), None, None]):
            call_command("es_ingest", stdout=out)

        output = out.getvalue()
        self.assertIn("Ingestion complete: 2 succeeded, 1 failed", output)
        self.assertIn("✗ Job", output)
        self.assertIn("bad detectors", output)

    def test_handle_bilby_backfills_gwosc_job_with_version_suffix(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW150914-v4--IMRPhenomD",
            description="Historical GWOSC job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value=json.dumps("1126259462.42"),
            index=0,
            processed=True,
        )

        out = StringIO()
        call_command("es_ingest", stdout=out)

        job.refresh_from_db()
        self.assertIsNotNone(job.event_id)
        self.assertEqual(job.event_id.event_id, "GW150914")
        self.assertAlmostEqual(job.event_id.gps_time, 1126259462.42)

    def test_handle_bilby_backfills_gwflow_child_via_bilby_jobs(self):
        event = EventID.objects.create(
            event_id="GW190425",
            gps_time=1239082262.22,
        )
        parent_gwflow = GWFlowJob.objects.create(
            sname="S190425z",
            user=self.user,
            event_id=event,
        )
        child = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Child_PE_GWFlow",
            description="Child Bilby job",
            private=False,
            gwflow_job=parent_gwflow,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        self.assertIsNone(child.event_id)

        out = StringIO()
        call_command("es_ingest", stdout=out)

        child.refresh_from_db()
        self.assertEqual(child.event_id, event)

    def test_handle_bilby_child_follows_unlinked_gwflow_parent(self):
        """GWF-9 rule 2: an unlinked parent leaves its child unlinked without fallback."""
        # GWF-9 rule 2: identifier fallback is removed; the child copies parent None.
        event = EventID.objects.create(
            event_id="GW190426",
            trigger_id="S190426c",
            gps_time=1239082262.22,
        )
        parent_gwflow = GWFlowJob.objects.create(
            sname="S190426c",
            user=self.user,
            event_id=None,
        )
        child = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Child_PE_Fallback_Trigger",
            description="Child Bilby job",
            private=False,
            gwflow_job=parent_gwflow,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        self.assertIsNone(child.event_id)

        out = StringIO()
        call_command("es_ingest", stdout=out)

        parent_gwflow.refresh_from_db()
        child.refresh_from_db()
        self.assertIsNone(parent_gwflow.event_id)
        self.assertIsNone(child.event_id)
        self.assertEqual(EventID.objects.get(pk=event.pk).trigger_id, "S190426c")

    def test_handle_bilby_backfills_gwosc_job_raw_float_string(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW170817-v1--TaylorF2",
            description="Historical GWOSC raw float job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value="1187008882.43",
            index=0,
            processed=False,
        )

        out = StringIO()
        call_command("es_ingest", stdout=out)

        job.refresh_from_db()
        self.assertIsNotNone(job.event_id)
        self.assertEqual(job.event_id.event_id, "GW170817")
        self.assertAlmostEqual(job.event_id.gps_time, 1187008882.43)

    def test_es_ingest_source_has_no_legacy_flag_or_sentinel(self):
        import inspect

        from bilbyui.management.commands import es_ingest as es_ingest_module

        source = inspect.getsource(es_ingest_module)
        flag = "is_ligo" + "_event"
        sentinel = "1126259462" + ".391"
        self.assertNotIn(flag, source)
        self.assertNotIn(sentinel, source)

    def test_handle_bilby_huge_int_gps_creates_null_gps_link(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW150914-v4--IMRPhenomD",
            description="Historical GWOSC job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value=json.dumps(str(10**400)),
            index=0,
            processed=True,
        )

        out = StringIO()
        call_command("es_ingest", stdout=out)

        job.refresh_from_db()
        self.assertIsNotNone(job.event_id)
        self.assertEqual(job.event_id.event_id, "GW150914")
        self.assertIsNone(job.event_id.gps_time)

    def test_handle_bilby_boolean_gps_creates_null_gps_link(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW150914-v4--IMRPhenomD",
            description="Historical GWOSC job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value=json.dumps(True),
            index=0,
            processed=True,
        )

        out = StringIO()
        call_command("es_ingest", stdout=out)

        job.refresh_from_db()
        self.assertIsNotNone(job.event_id)
        self.assertEqual(job.event_id.event_id, "GW150914")
        self.assertIsNone(job.event_id.gps_time)

    def test_handle_bilby_unparseable_gps_creates_null_gps_link(self):
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="GW150914-v4--IMRPhenomD",
            description="Historical GWOSC job",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        IniKeyValue.objects.create(
            job=job,
            key="trigger_time",
            value="not-a-number",
            index=0,
            processed=True,
        )

        out = StringIO()
        call_command("es_ingest", stdout=out)

        job.refresh_from_db()
        self.assertIsNotNone(job.event_id)
        self.assertEqual(job.event_id.event_id, "GW150914")
        self.assertIsNone(job.event_id.gps_time)


class TestGWFlowIngestFailureBranches(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.command_path = "bilbyui.management.commands.es_ingest"
        self.user = self.create_user()
        self.job = GWFlowJob.objects.create(
            sname="S000001a",
            user=self.user,
            current_version_number=1,
        )

    def _command(self):
        from bilbyui.management.commands.es_ingest import Command

        out = StringIO()
        command = Command(stdout=out, stderr=out)
        return command, out

    def _document(self):
        return {
            "_gwcloud": {
                "sname": self.job.sname,
                "searchTriggerTime": 150.0,
            },
            "metadata": {
                "analyses": [
                    {
                        "type": "pe",
                        "status": "complete",
                        "review_status": "approved",
                    }
                ]
            },
        }

    def _run_handle(
        self,
        *,
        es=None,
        fetch=None,
        build=None,
        bulk=None,
        before="same",
        after="same",
        wipe=False,
    ):
        command, out = self._command()
        es = es if es is not None else mock.MagicMock()
        fetch = fetch if fetch is not None else mock.Mock(return_value=({"analyses": []}, "live"))
        build = build if build is not None else mock.Mock(return_value=self._document())
        if bulk is None:

            def successful_stream(_es, actions, **_kwargs):
                return iter(
                    (
                        True,
                        {
                            "index": {
                                "_id": str(action["_id"]),
                                "_index": str(action["_index"]),
                                "status": 201,
                            }
                        },
                    )
                    for action in actions
                )

            bulk = mock.Mock(side_effect=successful_stream)

        with (
            override_settings(
                IGNORE_ELASTIC_SEARCH=False,
                CBCFLOW_PORTAL_URL="https://portal.example.test",
                CBCFLOW_PORTAL_TOKEN="secret",
                ELASTIC_SEARCH_GWFLOW_INDEX="gwcloud-gwflowjob",
            ),
            mock.patch(f"{self.command_path}.eligible_gwflow_jobs", return_value=[self.job]),
            mock.patch(f"{self.command_path}.clear_gwflow_portal_cache"),
            mock.patch(f"{self.command_path}.get_superevent", fetch),
            mock.patch(f"{self.command_path}.build_gwflow_es_doc", build),
            mock.patch(f"{self.command_path}.get_es_client", return_value=es),
            mock.patch(f"{self.command_path}.helpers.streaming_bulk", bulk),
            mock.patch(
                f"{self.command_path}.compute_protected_identity_digest",
                side_effect=[before, after],
            ),
            mock.patch(f"{self.command_path}.invalidate_gwflow_facet_caches"),
        ):
            result = command.handle_gwflow(wipe_and_rebuild=wipe)
        return result, out.getvalue()

    def test_gwflow_requires_portal_configuration(self):
        from django.core.management import CommandError

        command, _ = self._command()
        with override_settings(
            IGNORE_ELASTIC_SEARCH=False,
            CBCFLOW_PORTAL_URL="",
            CBCFLOW_PORTAL_TOKEN="",
        ):
            with self.assertRaisesRegex(CommandError, "CBCFLOW_PORTAL_URL"):
                command.handle_gwflow()

    def test_query_checks_issue_exact_five_queries_with_expected_ids(self):
        command, out = self._command()
        documents = {
            "1": {
                "_gwcloud": {"sname": "S000002b", "searchTriggerTime": 150.0},
                "metadata": {
                    "analyses": [
                        {
                            "type": "pe",
                            "status": "complete",
                            "review_status": "approved",
                        },
                        {
                            "type": "event_validation",
                            "status": "running",
                            "review_status": "pending",
                        },
                    ]
                },
            },
            "2": {
                "_gwcloud": {"sname": "S000001a", "searchTriggerTime": 99.0},
                "metadata": {
                    "analyses": [
                        {
                            "type": "event_validation",
                            "status": "complete",
                            "review_status": "approved",
                        }
                    ]
                },
            },
            "3": {
                "_gwcloud": {"sname": "S000001a", "searchTriggerTime": 199.5},
                "metadata": {
                    "analyses": [
                        {
                            "type": "pe",
                            "status": "running",
                            "review_status": "pending",
                        }
                    ]
                },
            },
        }
        expected_ids = {
            json.dumps(
                {"term": {"_gwcloud.sname": "S000001a"}},
                sort_keys=True,
            ): {"2", "3"},
            json.dumps(
                {"term": {"metadata.analyses.type": "event_validation"}},
                sort_keys=True,
            ): {"1", "2"},
            json.dumps(
                {"term": {"metadata.analyses.status": "complete"}},
                sort_keys=True,
            ): {"1", "2"},
            json.dumps(
                {"term": {"metadata.analyses.review_status": "approved"}},
                sort_keys=True,
            ): {"1", "2"},
            json.dumps(
                {
                    "range": {
                        "_gwcloud.searchTriggerTime": {
                            "gte": 100.0,
                            "lt": 200.0,
                        }
                    }
                },
                sort_keys=True,
            ): {"1", "3"},
        }
        seen_queries = []

        def search(*, index, query, size):
            self.assertEqual(index, "gwcloud-gwflowjob")
            self.assertEqual(size, 10000)
            key = json.dumps(query, sort_keys=True)
            seen_queries.append(key)
            return {"hits": {"hits": [{"_id": item_id} for item_id in sorted(expected_ids[key])]}}

        failures = []
        es = mock.Mock()
        es.search.side_effect = search

        command._run_gwflow_query_checks(
            es,
            "gwcloud-gwflowjob",
            documents,
            lambda phase, **details: failures.append((phase, details["reason"])),
        )

        self.assertEqual(failures, [])
        self.assertCountEqual(seen_queries, expected_ids)
        self.assertEqual(es.search.call_count, 5)
        self.assertIn("✓ query analyses.status=complete: 2 hit(s)", out.getvalue())

    def test_query_checks_range_excludes_golden_upper_boundary(self):
        command, _ = self._command()
        first = self.job
        first.trigger_time = 100.0
        first.save(update_fields=["trigger_time"])
        second = GWFlowJob.objects.create(
            sname="S000002b",
            user=self.user,
            trigger_time=200.0,
        )
        documents = {
            str(first.pk): {
                "_gwcloud": {
                    "sname": first.sname,
                    "searchTriggerTime": first.trigger_time,
                },
                "metadata": {
                    "analyses": [
                        {
                            "type": "pe",
                            "status": "complete",
                            "review_status": "approved",
                        }
                    ]
                },
            },
            str(second.pk): {
                "_gwcloud": {
                    "sname": second.sname,
                    "searchTriggerTime": second.trigger_time,
                },
                "metadata": {
                    "analyses": [
                        {
                            "type": "event_validation",
                            "status": "running",
                            "review_status": "pending",
                        }
                    ]
                },
            },
        }
        expected_range = {
            "range": {
                "_gwcloud.searchTriggerTime": {
                    "gte": 100.0,
                    "lt": 200.0,
                }
            }
        }
        range_ids = set()

        def search(*, index, query, size):
            self.assertEqual(index, "gwcloud-gwflowjob")
            self.assertEqual(size, 10000)
            if query == expected_range:
                hits = [{"_id": str(first.pk)}]
                range_ids.update(hit["_id"] for hit in hits)
                return {"hits": {"hits": hits}}

            if "term" in query:
                field, expected = next(iter(query["term"].items()))
                hits = []
                for document_id, document in documents.items():
                    if field == "_gwcloud.sname":
                        matched = document["_gwcloud"]["sname"] == expected
                    else:
                        analysis_field = field.rsplit(".", 1)[-1]
                        matched = any(
                            analysis.get(analysis_field) == expected for analysis in document["metadata"]["analyses"]
                        )
                    if matched:
                        hits.append({"_id": document_id})
                return {"hits": {"hits": hits}}

            self.fail(f"Unexpected Elasticsearch query: {query!r}")

        failures = []
        es = mock.Mock()
        es.search.side_effect = search

        command._run_gwflow_query_checks(
            es,
            "gwcloud-gwflowjob",
            documents,
            lambda phase, **details: failures.append((phase, details["reason"])),
        )

        self.assertEqual(failures, [])
        self.assertIn(
            mock.call(
                index="gwcloud-gwflowjob",
                query=expected_range,
                size=10000,
            ),
            es.search.call_args_list,
        )
        self.assertEqual(range_ids, {str(first.pk)})
        self.assertNotIn(str(second.pk), range_ids)

    def test_query_checks_fail_required_gate_with_no_analysis_value(self):
        from django.core.management import CommandError

        document = self._document()
        del document["metadata"]["analyses"][0]["review_status"]
        search_bodies = []

        with self.assertRaises(CommandError) as caught:
            self._run_rebuild_command(
                [self.job],
                mock.Mock(return_value=({"analyses": []}, "live")),
                mock.Mock(return_value=document),
                [],
                search_bodies,
            )

        self.assertEqual(caught.exception.returncode, 1)
        self.assertIn(
            "analyses.review_status query gate: no analysis carries metadata.analyses.review_status",
            caught.exception.command_output,
        )
        self.assertFalse(any("metadata.analyses.review_status" in body.get("term", {}) for body in search_bodies))

    def _run_rebuild_command(
        self,
        jobs,
        fetch,
        build,
        captured_runs,
        captured_searches=None,
        captured_audits=None,
    ):
        from django.core.management import CommandError

        from bilbyui.management.commands.es_ingest import build_gwflow_es_mapping

        documents = {}

        es = mock.MagicMock()
        es.indices.get_mapping.return_value = {"gwcloud-gwflowjob": build_gwflow_es_mapping()}

        def count(*, index):
            result = {"count": len(documents)}
            if captured_audits is not None:
                captured_audits.append(("count", index, result["count"]))
            return result

        es.count.side_effect = count

        def search(*, index, query, size, **kwargs):
            if captured_searches is not None:
                captured_searches.append(query)
            if "match_all" in query:
                ids = sorted(documents)
                if captured_audits is not None:
                    captured_audits.append(("parity", index, tuple(ids)))
            elif "term" in query:
                field, expected = next(iter(query["term"].items()))
                ids = []
                for document_id, document in documents.items():
                    if field == "_gwcloud.sname":
                        matched = document["_gwcloud"]["sname"] == expected
                    else:
                        analysis_field = field.rsplit(".", 1)[-1]
                        matched = any(
                            analysis.get(analysis_field) == expected
                            for analysis in document.get("metadata", {}).get("analyses", [])
                        )
                    if matched:
                        ids.append(document_id)
            elif "range" in query:
                field, bounds = next(iter(query["range"].items()))
                self.assertEqual(field, "_gwcloud.searchTriggerTime")
                ids = [
                    document_id
                    for document_id, document in documents.items()
                    if bounds["gte"] <= document["_gwcloud"]["searchTriggerTime"] < bounds["lt"]
                ]
            else:
                self.fail(f"Unexpected Elasticsearch query: {query!r}")
            return {"hits": {"hits": [{"_id": document_id} for document_id in ids[:size]]}}

        es.search.side_effect = search

        def streaming_bulk(_es, actions, **kwargs):
            captured = list(actions)
            captured_runs.append(captured)
            documents.clear()
            documents.update({str(action["_id"]): action["_source"] for action in captured})
            return iter(
                (
                    True,
                    {
                        "index": {
                            "_id": str(action["_id"]),
                            "_index": str(action["_index"]),
                            "status": 201,
                        }
                    },
                )
                for action in captured
            )

        out = StringIO()
        with (
            override_settings(
                IGNORE_ELASTIC_SEARCH=False,
                CBCFLOW_PORTAL_URL="https://portal.example.test",
                CBCFLOW_PORTAL_TOKEN="secret",
                ELASTIC_SEARCH_GWFLOW_INDEX="gwcloud-gwflowjob",
            ),
            mock.patch(
                f"{self.command_path}.eligible_gwflow_jobs",
                return_value=jobs,
            ),
            mock.patch(f"{self.command_path}.clear_gwflow_portal_cache"),
            mock.patch(f"{self.command_path}.get_superevent", side_effect=fetch),
            mock.patch(f"{self.command_path}.build_gwflow_es_doc", side_effect=build),
            mock.patch(f"{self.command_path}.get_es_client", return_value=es),
            mock.patch(
                f"{self.command_path}.helpers.streaming_bulk",
                side_effect=streaming_bulk,
            ),
            mock.patch(
                f"{self.command_path}.compute_protected_identity_digest",
                return_value="same",
            ),
            mock.patch(f"{self.command_path}.invalidate_gwflow_facet_caches"),
        ):
            try:
                call_command(
                    "es_ingest",
                    "--gwflow",
                    "--wipe-and-rebuild",
                    stdout=out,
                    stderr=out,
                )
            except CommandError as exc:
                exc.command_output = out.getvalue()
                raise

        return out.getvalue()

    def test_stale_portal_detail_is_fetch_failure_and_command_exits_one(self):
        from django.core.management import CommandError

        captured_runs = []
        fetch = mock.Mock(return_value=({"analyses": []}, "stale"))
        build = mock.Mock()

        with self.assertRaises(CommandError) as caught:
            self._run_rebuild_command(
                [self.job],
                fetch,
                build,
                captured_runs,
            )

        self.assertEqual(caught.exception.returncode, 1)
        self.assertIn("phase=fetch", caught.exception.command_output)
        self.assertIn("state=stale; expected live state with object data", caught.exception.command_output)
        self.assertIn("0 indexed", caught.exception.command_output)
        build.assert_not_called()
        self.assertEqual(captured_runs, [])

    def test_two_rebuilds_have_identical_ids_and_sources(self):
        import copy

        second_job = GWFlowJob.objects.create(
            sname="S000002b",
            user=self.user,
            trigger_time=200.5,
            current_version_number=2,
        )
        self.job.trigger_time = 150.0
        self.job.save(update_fields=["trigger_time"])

        jobs = [self.job, second_job]
        details = {
            job.sname: {
                "sname": job.sname,
                "analyses": [
                    {
                        "uid": f"{job.sname}-pe",
                        "type": "pe",
                        "status": "complete",
                        "review_status": "approved",
                    }
                ],
            }
            for job in jobs
        }

        def fetch(sname):
            return copy.deepcopy(details[sname]), "live"

        def build(job, detail):
            return {
                "_gwcloud": {
                    "sname": job.sname,
                    "searchTriggerTime": job.trigger_time,
                },
                "metadata": {
                    "analyses": copy.deepcopy(detail["analyses"]),
                },
            }

        captured_runs = []
        first_searches = []
        second_searches = []
        first_audits = []
        second_audits = []
        first_output = self._run_rebuild_command(
            jobs,
            fetch,
            build,
            captured_runs,
            first_searches,
            first_audits,
        )
        second_output = self._run_rebuild_command(
            jobs,
            fetch,
            build,
            captured_runs,
            second_searches,
            second_audits,
        )

        self.assertIn("2 indexed, 0 failed", first_output)
        self.assertIn("2 indexed, 0 failed", second_output)
        self.assertEqual(len(captured_runs), 2)

        first = {str(action["_id"]): copy.deepcopy(action["_source"]) for action in captured_runs[0]}
        second = {str(action["_id"]): copy.deepcopy(action["_source"]) for action in captured_runs[1]}
        self.assertEqual(set(first), set(second))
        self.assertEqual(first, second)
        self.assertEqual(first_audits, second_audits)
        self.assertEqual(
            first_audits,
            [
                ("count", "gwcloud-gwflowjob", 2),
                ("parity", "gwcloud-gwflowjob", tuple(sorted(first))),
            ],
        )
        self.assertEqual(first_searches, second_searches)
        self.assertEqual(len(first_searches), 6)
        self.assertEqual(first_searches[0], {"match_all": {}})

        first_query_successes = [line for line in first_output.splitlines() if line.startswith("✓ query ")]
        second_query_successes = [line for line in second_output.splitlines() if line.startswith("✓ query ")]
        self.assertEqual(first_query_successes, second_query_successes)
        self.assertEqual(
            first_query_successes,
            [
                "✓ query sname=S000001a: 1 hit(s)",
                "✓ query analyses.type=pe: 2 hit(s)",
                "✓ query analyses.status=complete: 2 hit(s)",
                "✓ query analyses.review_status=approved: 2 hit(s)",
                "✓ query searchTriggerTime range [100, 200): 1 hit(s)",
            ],
        )
        self.assertEqual(
            second[str(second_job.pk)]["_gwcloud"]["searchTriggerTime"],
            200.5,
        )

    def test_fetch_exception_is_reported_without_attempting_bulk(self):
        fetch = mock.Mock(side_effect=RuntimeError("portal unavailable"))
        bulk = mock.Mock()

        result, output = self._run_handle(fetch=fetch, bulk=bulk)

        self.assertEqual(result, 1)
        self.assertIn("phase=fetch", output)
        self.assertIn("portal unavailable", output)
        bulk.assert_not_called()

    def test_invalid_metadata_is_reported_as_build_failure(self):
        from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata

        build = mock.Mock(side_effect=InvalidGWFlowMetadata("bad canonical analysis"))
        result, output = self._run_handle(build=build)

        self.assertEqual(result, 1)
        self.assertIn("phase=build", output)
        self.assertIn("bad canonical analysis", output)

    def test_client_creation_failure_is_reported(self):
        command, out = self._command()
        with (
            override_settings(
                IGNORE_ELASTIC_SEARCH=False,
                CBCFLOW_PORTAL_URL="https://portal.example.test",
                CBCFLOW_PORTAL_TOKEN="secret",
                ELASTIC_SEARCH_GWFLOW_INDEX="gwcloud-gwflowjob",
            ),
            mock.patch(f"{self.command_path}.eligible_gwflow_jobs", return_value=[self.job]),
            mock.patch(f"{self.command_path}.clear_gwflow_portal_cache"),
            mock.patch(
                f"{self.command_path}.get_superevent",
                return_value=({"analyses": []}, "live"),
            ),
            mock.patch(
                f"{self.command_path}.build_gwflow_es_doc",
                return_value=self._document(),
            ),
            mock.patch(
                f"{self.command_path}.get_es_client",
                side_effect=RuntimeError("client unavailable"),
            ),
            mock.patch(
                f"{self.command_path}.compute_protected_identity_digest",
                side_effect=["same", "same"],
            ),
        ):
            result = command.handle_gwflow()

        self.assertEqual(result, 1)
        self.assertIn("phase=client", out.getvalue())
        self.assertIn("client unavailable", out.getvalue())

    def test_mapping_recreation_failure_prevents_bulk(self):
        es = mock.MagicMock()
        es.indices.create.side_effect = RuntimeError("mapping rejected")
        bulk = mock.Mock()

        result, output = self._run_handle(es=es, bulk=bulk, wipe=True)

        self.assertEqual(result, 1)
        self.assertIn("phase=mapping", output)
        self.assertIn("index recreation failed", output)
        bulk.assert_not_called()

    def test_streaming_bulk_success_validates_every_item(self):
        bulk = mock.Mock(
            return_value=iter(
                [
                    (
                        True,
                        {
                            "index": {
                                "_id": str(self.job.pk),
                                "_index": "gwcloud-gwflowjob",
                                "status": 201,
                            }
                        },
                    )
                ]
            )
        )

        result, output = self._run_handle(bulk=bulk)

        self.assertEqual(result, 0)
        self.assertIn("1 indexed, 0 failed", output)
        bulk.assert_called_once()
        self.assertEqual(
            bulk.call_args.kwargs,
            {
                "raise_on_error": False,
                "raise_on_exception": False,
                "refresh": True,
                "chunk_size": 500,
            },
        )

    def test_streaming_bulk_item_failure_records_reason_and_status(self):
        bulk = mock.Mock(
            return_value=iter(
                [
                    (
                        False,
                        {
                            "index": {
                                "_id": str(self.job.pk),
                                "_index": "gwcloud-gwflowjob",
                                "status": 429,
                                "error": {"reason": "queue full"},
                            }
                        },
                    )
                ]
            )
        )

        result, output = self._run_handle(bulk=bulk)

        self.assertEqual(result, 1)
        self.assertIn("queue full (status=429)", output)
        self.assertIn("0 indexed", output)

    def test_streaming_bulk_malformed_item_is_not_counted_as_indexed(self):
        bulk = mock.Mock(return_value=iter([(True, {"index": "not-an-object"})]))

        result, output = self._run_handle(bulk=bulk)

        self.assertEqual(result, 1)
        self.assertIn("malformed/unknown item result", output)
        self.assertIn("missing item result", output)
        self.assertIn("0 indexed", output)

    def test_streaming_bulk_duplicate_success_rejects_document(self):
        success = (
            True,
            {
                "index": {
                    "_id": str(self.job.pk),
                    "_index": "gwcloud-gwflowjob",
                    "status": 200,
                }
            },
        )
        bulk = mock.Mock(return_value=iter([success, success]))

        result, output = self._run_handle(bulk=bulk)

        self.assertEqual(result, 1)
        self.assertIn("duplicate success", output)
        self.assertIn("0 indexed", output)

    def test_streaming_bulk_unknown_id_is_not_counted_as_indexed(self):
        bulk = mock.Mock(
            return_value=iter(
                [
                    (
                        True,
                        {
                            "index": {
                                "_id": "999999",
                                "_index": "gwcloud-gwflowjob",
                                "status": 200,
                            }
                        },
                    )
                ]
            )
        )

        result, output = self._run_handle(bulk=bulk)

        self.assertEqual(result, 1)
        self.assertIn("malformed/unknown item result", output)
        self.assertIn("missing item result", output)
        self.assertIn("0 indexed", output)

    def test_streaming_bulk_missing_result_is_reported(self):
        bulk = mock.Mock(return_value=iter([]))

        result, output = self._run_handle(bulk=bulk)

        self.assertEqual(result, 1)
        self.assertIn("missing item result", output)
        self.assertIn("0 indexed", output)

    def test_bulk_exception_marks_each_action_failed(self):
        def raise_during_stream(_es, _actions, **_kwargs):
            def results():
                raise RuntimeError("bulk transport failed")
                yield

            return results()

        result, output = self._run_handle(
            bulk=mock.Mock(side_effect=raise_during_stream),
        )

        self.assertEqual(result, 1)
        self.assertIn("phase=bulk", output)
        self.assertIn("bulk transport failed", output)
        self.assertIn("0 indexed", output)

    def test_rebuild_verification_failures_are_reported(self):
        es = mock.MagicMock()
        es.indices.get_mapping.return_value = {"gwcloud-gwflowjob": {"mappings": {"properties": {}}}}
        es.count.side_effect = RuntimeError("count unavailable")
        es.search.side_effect = RuntimeError("id search unavailable")

        result, output = self._run_handle(es=es, wipe=True)

        self.assertEqual(result, 1)
        self.assertIn("installed mapping does not satisfy the contract", output)
        self.assertIn("count verification failed: count unavailable", output)
        self.assertIn("id-set verification failed: id search unavailable", output)

    def test_refresh_and_mapping_lookup_exceptions_are_reported(self):
        es = mock.MagicMock()
        es.indices.refresh.side_effect = RuntimeError("refresh unavailable")
        es.indices.get_mapping.side_effect = RuntimeError("mapping unavailable")
        es.count.return_value = {"count": 1}
        es.search.return_value = {"hits": {"hits": [{"_id": str(self.job.pk)}]}}

        result, output = self._run_handle(es=es, wipe=True)

        self.assertEqual(result, 1)
        self.assertIn("phase=refresh", output)
        self.assertIn("mapping verification failed: mapping unavailable", output)

    def test_protected_identity_change_is_reported(self):
        result, output = self._run_handle(before="before", after="after")

        self.assertEqual(result, 1)
        self.assertIn("phase=postgres", output)
        self.assertIn("protected identity digest changed", output)
