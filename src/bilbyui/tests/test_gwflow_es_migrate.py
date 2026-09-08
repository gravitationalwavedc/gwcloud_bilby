from datetime import UTC, datetime
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.test import override_settings

from bilbyui.management.commands.gwflow_es_migrate import build_gwflow_es_mapping
from bilbyui.models import GWFlowJob
from bilbyui.services.gwflow import LIBRARIES_CACHE_KEY, REVIEW_STATUSES_CACHE_KEY
from bilbyui.tests.gwflow_es_fixtures import (
    FIXTURE_MATRIX,
    assert_defect_queries_assertable,
    assert_doc_matches_spec,
    build_canonical_fixtures,
)
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.gwflow_es import InvalidGWFlowMetadata

PAYLOAD = {"ParameterEstimation": {"results": [{"uid": "pe-1", "review_status": "approved"}]}}


def make_job(sname="S230601ag", history_id="hist-001", **kwargs):
    return GWFlowJob.objects.create(
        sname=sname,
        user_id=1,
        current_history_id=history_id,
        current_history_timestamp=datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC),
        **kwargs,
    )


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class GwflowEsMigrateCommandTestCase(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()

    def setUp(self):
        cache.clear()

    def _run(self, *args, **kwargs):
        out = StringIO()
        err = StringIO()
        with (
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.get_es_client") as m_es,
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.get_version") as m_ver,
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.build_gwflow_es_doc") as m_build,
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.helpers.bulk") as m_bulk,
        ):
            m_es.return_value = kwargs.pop("es", None) or mock.MagicMock()
            m_ver.side_effect = kwargs.pop("get_version_side_effect", None)
            m_ver.return_value = kwargs.pop("get_version_return", (PAYLOAD, "live"))
            m_build.side_effect = kwargs.pop("build_side_effect", None)
            m_build.return_value = kwargs.pop("build_return", {"_gwcloud": {}, "metadata": PAYLOAD})
            m_bulk.return_value = kwargs.pop("bulk_return", (1, []))
            try:
                exit_code = call_command("gwflow_es_migrate", *args, stdout=out, stderr=err, **kwargs)
            except CommandError as e:
                exit_code = e.returncode
        return exit_code, out.getvalue(), err.getvalue(), m_es, m_ver, m_build, m_bulk

    def test_delete_then_create_then_reimport_order(self):
        make_job()
        calls = []
        es = mock.MagicMock()
        es.indices.delete.side_effect = lambda **kw: calls.append("delete")
        es.indices.create.side_effect = lambda **kw: calls.append("create")
        es.count.return_value = {"count": 1}

        out = StringIO()
        with (
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.get_es_client", return_value=es),
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.get_version", return_value=(PAYLOAD, "live")),
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.build_gwflow_es_doc", return_value={"metadata": PAYLOAD}),
            mock.patch(
                "bilbyui.management.commands.gwflow_es_migrate.helpers.bulk",
                side_effect=lambda *a, **k: calls.append("bulk") or (1, []),
            ),
        ):
            exit_code = call_command("gwflow_es_migrate", stdout=out)

        self.assertEqual(exit_code, 0)
        self.assertEqual(calls, ["delete", "create", "bulk"])

    def test_mapping_payload_correct(self):
        make_job()
        es = mock.MagicMock()
        es.count.return_value = {"count": 1}

        _, _, _, m_es, _, _, _ = self._run(es=es)

        body = m_es.return_value.indices.create.call_args.kwargs["body"]
        mappings = body["mappings"]
        self.assertEqual(mappings["date_detection"], False)
        self.assertEqual(mappings["numeric_detection"], False)
        self.assertEqual(mappings["properties"]["_gwcloud"]["dynamic"], "strict")
        self.assertEqual(mappings["properties"]["metadata"]["dynamic"], True)
        self.assertEqual(mappings["properties"]["metadata"]["type"], "object")
        self.assertEqual(
            set(mappings["properties"]["_gwcloud"]["properties"].keys()),
            {
                "sname",
                "libraries",
                "isPruned",
                "ligoOnly",
                "lastUpdatedTime",
                "reviewStatuses",
                "eventTriggerId",
            },
        )
        template = mappings["dynamic_templates"][0]
        self.assertEqual(template["metadata_strings"]["match"], "metadata.*")
        self.assertEqual(template["metadata_strings"]["match_mapping_type"], "string")
        self.assertEqual(
            template["metadata_strings"]["mapping"]["fields"]["keyword"],
            {"type": "keyword", "ignore_above": 1024},
        )
        settings_body = body["settings"]
        self.assertEqual(settings_body["index.mapping.total_fields.limit"], 10000)
        self.assertEqual(settings_body["index.mapping.depth.limit"], 100)
        self.assertEqual(
            settings_body["index.query.default_field"],
            ["_gwcloud.sname", "_gwcloud.libraries", "_gwcloud.reviewStatuses", "_gwcloud.eventTriggerId"],
        )
        self.assertNotIn("index.mapping.nested_fields.limit", settings_body)

    def test_build_gwflow_es_mapping_no_nested_fields(self):
        body = build_gwflow_es_mapping()
        self.assertNotIn("index.mapping.nested_fields.limit", body["settings"])

    def test_refusal_on_portal_failure(self):
        make_job()
        es = mock.MagicMock()

        exit_code, out, _, m_es, _, _, _ = self._run(es=es, get_version_return=(None, "down"))

        self.assertEqual(exit_code, 1)
        self.assertIn("Refusing to proceed", out)
        m_es.return_value.indices.delete.assert_not_called()
        m_es.return_value.indices.create.assert_not_called()

    def test_refusal_on_invalid_metadata(self):
        make_job()
        es = mock.MagicMock()

        exit_code, out, _, m_es, _, _, _ = self._run(
            es=es, build_side_effect=InvalidGWFlowMetadata("bad metadata")
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Refusing to proceed", out)
        m_es.return_value.indices.delete.assert_not_called()
        m_es.return_value.indices.create.assert_not_called()

    def test_refusal_on_unexpected_build_error(self):
        make_job()
        es = mock.MagicMock()

        exit_code, out, _, m_es, _, _, _ = self._run(
            es=es, build_side_effect=RuntimeError("boom")
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Refusing to proceed", out)
        m_es.return_value.indices.delete.assert_not_called()
        m_es.return_value.indices.create.assert_not_called()

    def test_count_check_and_cache_invalidation_on_success(self):
        make_job()
        cache.set(LIBRARIES_CACHE_KEY, "x")
        cache.set(REVIEW_STATUSES_CACHE_KEY, "y")
        es = mock.MagicMock()
        es.count.return_value = {"count": 1}

        exit_code, out, _, _, _, _, _ = self._run(es=es)

        self.assertEqual(exit_code, 0)
        self.assertIn("Count check: source=1, target=1", out)
        self.assertIn("Invalidated filter-option cache keys", out)
        self.assertIsNone(cache.get(LIBRARIES_CACHE_KEY))
        self.assertIsNone(cache.get(REVIEW_STATUSES_CACHE_KEY))

    def test_count_mismatch_fails_without_cache_invalidation(self):
        make_job()
        cache.set(LIBRARIES_CACHE_KEY, "x")
        cache.set(REVIEW_STATUSES_CACHE_KEY, "y")
        es = mock.MagicMock()
        es.count.return_value = {"count": 0}

        exit_code, out, _, _, _, _, _ = self._run(es=es)

        self.assertEqual(exit_code, 1)
        self.assertIn("Count check: source=1, target=0", out)
        self.assertNotIn("Invalidated filter-option cache keys", out)
        self.assertEqual(cache.get(LIBRARIES_CACHE_KEY), "x")
        self.assertEqual(cache.get(REVIEW_STATUSES_CACHE_KEY), "y")

    def test_item_bulk_failure_reported(self):
        make_job()
        cache.set(LIBRARIES_CACHE_KEY, "x")
        es = mock.MagicMock()
        es.count.return_value = {"count": 1}
        errors = [{"index": {"status": 400, "error": {"reason": "boom"}, "_id": 1}}]

        exit_code, out, err, _, _, _, _ = self._run(es=es, bulk_return=(0, errors))

        self.assertEqual(exit_code, 1)
        self.assertIn("Bulk item failure", err)
        self.assertNotIn("Invalidated filter-option cache keys", out)
        self.assertEqual(cache.get(LIBRARIES_CACHE_KEY), "x")

    def test_dry_run_no_es_writes_no_cache_invalidation(self):
        make_job()
        cache.set(LIBRARIES_CACHE_KEY, "x")
        es = mock.MagicMock()

        exit_code, out, _, m_es, _, _, _ = self._run("--dry-run", es=es)

        self.assertEqual(exit_code, 0)
        self.assertIn("Dry run", out)
        m_es.return_value.indices.delete.assert_not_called()
        m_es.return_value.indices.create.assert_not_called()
        self.assertEqual(cache.get(LIBRARIES_CACHE_KEY), "x")

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    def test_ignore_elastic_search_noop(self):
        make_job()
        with mock.patch("bilbyui.management.commands.gwflow_es_migrate.get_es_client") as m_es:
            out = StringIO()
            exit_code = call_command("gwflow_es_migrate", stdout=out)
        self.assertEqual(exit_code, 0)
        m_es.assert_not_called()
        self.assertIn("no-op", out.getvalue())

    def test_full_migration_sequence_with_canonical_fixtures(self):
        """Integration-style test: delete -> create -> reimport -> count check
        -> cache invalidation, with reimported docs matching the canonical
        fixture matrix (real builder, mocked ES client)."""
        fixtures = build_canonical_fixtures(self.__class__)
        cache.set(LIBRARIES_CACHE_KEY, "x")
        cache.set(REVIEW_STATUSES_CACHE_KEY, "y")

        es = mock.MagicMock()
        es.count.return_value = {"count": len(fixtures)}
        call_order = []

        def fake_get_version(sname, history_id):
            for fx in fixtures.values():
                if fx["job"].sname == sname:
                    return fx["spec"]["metadata"], "live"
            raise AssertionError(f"unexpected sname {sname}")

        captured = {}

        def fake_bulk(es_client, actions, **kwargs):
            captured["actions"] = list(actions)
            call_order.append("bulk")
            return (len(actions), [])

        es.indices.delete.side_effect = lambda **kw: call_order.append("delete")
        es.indices.create.side_effect = lambda **kw: call_order.append("create")

        out = StringIO()
        with (
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.get_es_client", return_value=es),
            mock.patch(
                "bilbyui.management.commands.gwflow_es_migrate.get_version", side_effect=fake_get_version
            ),
            mock.patch("bilbyui.management.commands.gwflow_es_migrate.helpers.bulk", side_effect=fake_bulk),
        ):
            exit_code = call_command("gwflow_es_migrate", stdout=out)

        self.assertEqual(exit_code, 0)
        # Full sequence ordering: delete -> create -> reimport.
        self.assertEqual(call_order, ["delete", "create", "bulk"])
        # Count check + cache invalidation on success.
        self.assertIn(f"Count check: source={len(fixtures)}, target={len(fixtures)}", out.getvalue())
        self.assertIn("Invalidated filter-option cache keys", out.getvalue())
        self.assertIsNone(cache.get(LIBRARIES_CACHE_KEY))
        self.assertIsNone(cache.get(REVIEW_STATUSES_CACHE_KEY))

        # Reimported documents match the canonical fixture matrix.
        actions = captured["actions"]
        self.assertEqual(len(actions), len(fixtures))
        for action in actions:
            fx = fixtures[action["_id"]]
            self.assertEqual(action["_index"], settings.ELASTIC_SEARCH_GWFLOW_INDEX)
            assert_doc_matches_spec(self, action["_source"], fx["spec"])

    def test_reimported_docs_carry_defect_query_fields(self):
        """The reimported docs carry the fields the four defect queries (and
        the related exists/range/aggregation queries) depend on."""
        fixtures = build_canonical_fixtures(self.__class__)
        assert_defect_queries_assertable(self, fixtures)

    def test_fixture_matrix_matches_issue_spec(self):
        """The canonical fixture matrix has exactly the 5 documents from the
        issue, each with the expected visibility/pruned/libraries/status."""
        self.assertEqual(len(FIXTURE_MATRIX), 5)
        self.assertEqual([spec["id"] for spec in FIXTURE_MATRIX], [1, 2, 3, 4, 5])
        self.assertEqual(
            [spec["ligo_only"] for spec in FIXTURE_MATRIX],
            [False, False, True, False, False],
        )
        self.assertEqual(
            [spec["is_pruned"] for spec in FIXTURE_MATRIX],
            [False, False, False, True, False],
        )
