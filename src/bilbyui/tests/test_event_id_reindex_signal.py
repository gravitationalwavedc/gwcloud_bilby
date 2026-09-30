from unittest import mock

from django.db import DEFAULT_DB_ALIAS, transaction

from bilbyui.models import EventID
from bilbyui.tests.testcases import BilbyTestCase


class TestEventIDReindexSignal(BilbyTestCase):
    @mock.patch("bilbyui.models.transaction.on_commit", wraps=transaction.on_commit)
    @mock.patch("bilbyui.models.BilbyJob.elastic_search_update")
    @mock.patch("bilbyui.utils.reindex.reindex_affected_event")
    def test_save_registers_one_callback_with_alias_and_reindexes_once_after_commit(
        self,
        reindex_affected_event_mock,
        elastic_search_update_mock,
        on_commit_mock,
    ):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            event = EventID.objects.create(event_id="G123456")
            reindex_affected_event_mock.assert_not_called()

        self.assertEqual(len(callbacks), 1)
        on_commit_mock.assert_called_once()
        self.assertEqual(on_commit_mock.call_args.kwargs["using"], DEFAULT_DB_ALIAS)
        reindex_affected_event_mock.assert_called_once_with(event.id)
        elastic_search_update_mock.assert_not_called()

    @mock.patch("elasticsearch.Elasticsearch.index")
    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.BilbyJob.elastic_search_update")
    @mock.patch("bilbyui.utils.reindex.reindex_affected_event")
    def test_rolled_back_save_does_not_reindex_or_write_elasticsearch(
        self,
        reindex_affected_event_mock,
        elastic_search_update_mock,
        elasticsearch_update_mock,
        elasticsearch_index_mock,
    ):
        with transaction.atomic():
            EventID.objects.create(event_id="G123457")
            transaction.set_rollback(True)

        reindex_affected_event_mock.assert_not_called()
        elastic_search_update_mock.assert_not_called()
        elasticsearch_update_mock.assert_not_called()
        elasticsearch_index_mock.assert_not_called()
