from unittest import mock

import elasticsearch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from bilbyui.models import BilbyJob, EventID, Label
from bilbyui.tests.test_utils import create_test_ini_string, generate_elastic_doc
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


def request_lookup_users_mock(*args, **kwargs):
    user = User.objects.first()
    if user:
        return True, [{"id": user.id, "name": "buffy summers"}]
    return False, []


def request_lookup_users_failure_mock(*args, **kwargs):
    return False, "Error looking up users: auth service unavailable"


def request_lookup_users_empty_mock(*args, **kwargs):
    return True, []


def request_lookup_users_non_dict_mock(*args, **kwargs):
    return True, ["malformed-user-record"]


def request_elasticsearch_update_mock_raises(*args, **kwargs):
    raise elasticsearch.NotFoundError("Exists", None, None)


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class TestElasticSearch(BilbyTestCase):
    def setUp(self):
        self.user = self.create_user()

    @mock.patch(
        "elasticsearch.Elasticsearch.update",
        side_effect=request_elasticsearch_update_mock_raises,
    )
    @mock.patch("elasticsearch.Elasticsearch.index")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_create_document_basic(
        self,
        lookup_users_mock,
        elasticsearch_index_mock,
        elasticsearch_update_mock_raises,
    ):
        """
        Test that if we create a job, the elastic search index function is called as expected.
        Also tests that if update raises a elasticsearch.NotFoundError exception, that index is called to insert the
        record in elastic search
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

        # request_lookup_users should have been called once with an array containing only the user id
        self.assertEqual(lookup_users_mock.call_count, 1)
        self.assertEqual(lookup_users_mock.mock_calls[0].args, ([1],))

        # Update should have been called once, which then raises elasticsearch.NotFoundError
        self.assertEqual(elasticsearch_update_mock_raises.call_count, 1)

        # Verify the document
        self.assertEqual(
            elasticsearch_index_mock.mock_calls[0].kwargs["index"],
            settings.ELASTIC_SEARCH_INDEX,
        )
        self.assertEqual(elasticsearch_index_mock.mock_calls[0].kwargs["id"], job.id)

        # Make sure this test has no labels or an event id
        doc = generate_elastic_doc(job, {"name": "buffy summers"})

        self.assertEqual(doc["labels"], [])
        self.assertIsNone(doc["eventId"])

        self.assertDictEqual(elasticsearch_index_mock.mock_calls[0].kwargs["document"], doc)

    @mock.patch(
        "elasticsearch.Elasticsearch.update",
        side_effect=request_elasticsearch_update_mock_raises,
    )
    @mock.patch("elasticsearch.Elasticsearch.index")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_create_document_complete(
        self,
        lookup_users_mock,
        elasticsearch_index_mock,
        elasticsearch_update_mock_raises,
    ):
        """
        Test that if we create a job with event id and labels, that the elastic search index function
        is called as expected
        Also tests that if update raises a elasticsearch.NotFoundError exception, that index is called to insert the
        record in elastic search
        """
        label1 = Label.objects.create(name="label 1", description="my label 1", protected=True)
        label2 = Label.objects.create(name="label 2", description="my label 2", protected=False)

        event_id = EventID.create(
            "GW123456_123456",
            12345678,
            trigger_id="S123456a",
            nickname="Test Nick",
            is_ligo_event=True,
        )

        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                event_id=event_id,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            job.labels.add(label1)
            job.labels.add(label2)

        # request_lookup_users should have been called three times
        self.assertEqual(lookup_users_mock.call_count, 3)

        # Update should have been called three times, which raises elasticsearch.NotFoundError
        self.assertEqual(elasticsearch_update_mock_raises.call_count, 3)

        # Verify the document
        self.assertEqual(
            elasticsearch_index_mock.mock_calls[-1].kwargs["index"],
            settings.ELASTIC_SEARCH_INDEX,
        )
        self.assertEqual(elasticsearch_index_mock.mock_calls[-1].kwargs["id"], job.id)

        # Make sure this test has no labels or an event id
        doc = generate_elastic_doc(job, {"name": "buffy summers"})

        self.assertNotEqual(doc["labels"], [])
        self.assertNotEqual(doc["eventId"], None)

        self.assertDictEqual(elasticsearch_index_mock.mock_calls[-1].kwargs["document"], doc)

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_failure_mock)
    def test_job_save_user_lookup_failure_skips_indexing(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that when the user lookup fails (auth service down), the job is still saved without
        raising a TypeError and no document is indexed in elastic search
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

        # request_lookup_users should have been called once with an array containing only the user id
        self.assertEqual(lookup_users_mock.call_count, 1)
        self.assertEqual(lookup_users_mock.mock_calls[0].args, ([1],))

        # No elastic search update/index call should have been made
        elasticsearch_update_mock.assert_not_called()

        self.assertIsNotNone(job.id)

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_non_dict_mock)
    def test_job_save_user_lookup_non_dict_skips_indexing(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that when the user lookup succeeds but returns a non-dict user record, the job is
        still saved without raising a TypeError and no document is indexed in elastic search
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

        # request_lookup_users should have been called once with an array containing only the user id
        self.assertEqual(lookup_users_mock.call_count, 1)
        self.assertEqual(lookup_users_mock.mock_calls[0].args, ([1],))

        # No elastic search update/index call should have been made
        elasticsearch_update_mock.assert_not_called()

        self.assertIsNotNone(job.id)

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_empty_mock)
    def test_job_save_user_lookup_empty_skips_indexing(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that when the user lookup succeeds but returns no matching users, the job is still
        saved without raising an IndexError and no document is indexed in elastic search
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

        # request_lookup_users should have been called once with an array containing only the user id
        self.assertEqual(lookup_users_mock.call_count, 1)
        self.assertEqual(lookup_users_mock.mock_calls[0].args, ([1],))

        # No elastic search update/index call should have been made
        elasticsearch_update_mock.assert_not_called()

        self.assertIsNotNone(job.id)

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_update_document(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that update is called with the expected document
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

        # request_lookup_users should have been called once with an array containing only the user id
        self.assertEqual(lookup_users_mock.call_count, 1)
        self.assertEqual(lookup_users_mock.mock_calls[0].args, ([1],))

        # Update should have been called once
        self.assertEqual(elasticsearch_update_mock.call_count, 1)

        # Verify the document
        self.assertEqual(
            elasticsearch_update_mock.mock_calls[0].kwargs["index"],
            settings.ELASTIC_SEARCH_INDEX,
        )
        self.assertEqual(elasticsearch_update_mock.mock_calls[0].kwargs["id"], job.id)

        # Make sure this test has no labels or an event id
        doc = generate_elastic_doc(job, {"name": "buffy summers"})

        self.assertEqual(doc["labels"], [])
        self.assertIsNone(doc["eventId"])

        self.assertDictEqual(elasticsearch_update_mock.mock_calls[0].kwargs["doc"], doc)

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_event_id_update(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that if we update an event id associated with a job, that the job's elastic search update
        is triggered
        """
        event_id = EventID.create(
            "GW123456_123456",
            12345678,
            trigger_id="S123456a",
            nickname="Test Nick",
            is_ligo_event=True,
        )

        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                event_id=event_id,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            event_id.is_ligo_event = False
            event_id.save()

        # Update should have been called twice, which then raises elasticsearch.NotFoundError
        self.assertEqual(elasticsearch_update_mock.call_count, 2)

        self.assertDictEqual(
            elasticsearch_update_mock.mock_calls[-1].kwargs["doc"],
            generate_elastic_doc(job, {"name": "buffy summers"}),
        )

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_label_update(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that if we update a label associated with a job, that the job's elastic search update
        is triggered
        """
        label1 = Label.objects.create(name="label 1", description="my label 1", protected=True)

        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            job.labels.add(label1)

            label1.name = "label 2"
            label1.save()

        # Update should have been called three times
        self.assertEqual(elasticsearch_update_mock.call_count, 3)

        self.assertDictEqual(
            elasticsearch_update_mock.mock_calls[-1].kwargs["doc"],
            generate_elastic_doc(job, {"name": "buffy summers"}),
        )

    @mock.patch("elasticsearch.Elasticsearch.delete")
    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_delete_remove_document(self, request_lookup_users, elastic_search_update, elastic_search_delete):
        """
        Test that when a bilby job is deleted, the elastic search record is also deleted
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            job_id = job.id

            job.delete()

        self.assertDictEqual(
            elastic_search_delete.mock_calls[0].kwargs,
            {"index": settings.ELASTIC_SEARCH_INDEX, "id": job_id},
        )

    @mock.patch(
        "elasticsearch.Elasticsearch.delete",
        side_effect=request_elasticsearch_update_mock_raises,
    )
    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_delete_missing_document_still_deletes(
        self, request_lookup_users, elastic_search_update, elastic_search_delete
    ):
        """
        Test that deleting a job whose elastic search document is missing (e.g. a legacy job that
        was never indexed) still deletes the job, without the pre_delete signal aborting on
        elasticsearch.NotFoundError
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            job_id = job.id

            job.delete()

        # The delete call should still have been attempted
        self.assertEqual(elastic_search_delete.call_count, 1)

        # The job should no longer exist in the database
        self.assertFalse(BilbyJob.objects.filter(id=job_id).exists())

    @mock.patch("elasticsearch.Elasticsearch.delete")
    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.BilbyJob.elastic_search_remove")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_bilby_job_delete_signal(
        self, mock_lookup_users, mock_remove, elastic_search_update, elastic_search_delete
    ):
        """
        Test that deleting a bilby job triggers the bilby_job_delete_signal pre_delete handler,
        which removes the job's elastic search record
        """
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            job_controller_id=2,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

        job.delete()

        mock_remove.assert_called_once()

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_es_mutation_runs_after_commit(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that the elastic search update is deferred until after the database commit, not run
        immediately inside the transaction
        """
        with self.captureOnCommitCallbacks(execute=True):
            BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            # Inside the transaction (before commit) the ES update must not have run yet
            elasticsearch_update_mock.assert_not_called()

        # After commit the ES update must have run
        elasticsearch_update_mock.assert_called_once()

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_rolled_back_save_performs_no_es_write(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that a rolled-back job save performs no elastic search write
        """
        with transaction.atomic():
            BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )
            transaction.set_rollback(True)

        elasticsearch_update_mock.assert_not_called()

    @mock.patch("elasticsearch.Elasticsearch.delete")
    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_rolled_back_deletion_preserves_es_document(
        self, lookup_users_mock, elastic_search_update, elastic_search_delete
    ):
        """
        Test that a rolled-back deletion performs no elastic search remove, so the document is
        preserved for the restored row
        """
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            job_controller_id=2,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        job_id = job.id

        with transaction.atomic():
            job.delete()
            transaction.set_rollback(True)

        # The delete was rolled back, so the job still exists
        self.assertTrue(BilbyJob.objects.filter(id=job_id).exists())

        # No elastic search remove should have been performed
        elastic_search_delete.assert_not_called()

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_label_post_save_commit_and_rollback(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that the Label post_save signal triggers an ES update on commit, and performs no ES
        write when the surrounding transaction rolls back
        """
        label1 = Label.objects.create(name="label 1", description="my label 1", protected=True)

        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )
            job.labels.add(label1)

            label1.name = "label 2"
            label1.save()

        # On commit the label post_save signal should have triggered an ES update
        self.assertGreaterEqual(elasticsearch_update_mock.call_count, 1)

        elasticsearch_update_mock.reset_mock()

        with transaction.atomic():
            label1.name = "label 3"
            label1.save()
            transaction.set_rollback(True)

        # On rollback no ES write should have been performed
        elasticsearch_update_mock.assert_not_called()

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_event_id_post_save_commit_and_rollback(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that the EventID post_save signal triggers an ES update on commit, and performs no ES
        write when the surrounding transaction rolls back
        """
        event_id = EventID.create(
            "GW123456_123456",
            12345678,
            trigger_id="S123456a",
            nickname="Test Nick",
            is_ligo_event=True,
        )

        with self.captureOnCommitCallbacks(execute=True):
            BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                event_id=event_id,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            event_id.is_ligo_event = False
            event_id.save()

        # On commit the event id post_save signal should have triggered an ES update
        self.assertGreaterEqual(elasticsearch_update_mock.call_count, 1)

        elasticsearch_update_mock.reset_mock()

        with transaction.atomic():
            event_id.is_ligo_event = True
            event_id.save()
            transaction.set_rollback(True)

        # On rollback no ES write should have been performed
        elasticsearch_update_mock.assert_not_called()

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_m2m_changed_commit_and_rollback(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that the m2m_changed signal triggers an ES update on commit, and performs no ES
        write when the surrounding transaction rolls back
        """
        label1 = Label.objects.create(name="label 1", description="my label 1", protected=True)

        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

            job.labels.add(label1)

        # On commit the m2m_changed signal should have triggered an ES update
        self.assertGreaterEqual(elasticsearch_update_mock.call_count, 1)

        elasticsearch_update_mock.reset_mock()

        with transaction.atomic():
            job.labels.add(label1)
            transaction.set_rollback(True)

        # On rollback no ES write should have been performed
        elasticsearch_update_mock.assert_not_called()

    @mock.patch(
        "elasticsearch.Elasticsearch.update",
        side_effect=elasticsearch.TransportError("boom"),
    )
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_post_commit_es_transport_failure_logged_and_suppressed(
        self, lookup_users_mock, elasticsearch_update_mock
    ):
        """
        Test that a post-commit elastic search transport failure is logged and suppressed, so the
        request still succeeds
        """
        with self.assertLogs("bilbyui.models", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                job = BilbyJob.objects.create(
                    user_id=self.user.id,
                    name="Test1",
                    description="first job",
                    job_controller_id=2,
                    private=False,
                    ini_string=create_test_ini_string({"detectors": "['H1']"}),
                )

        # The request still succeeds (no exception was raised)
        self.assertIsNotNone(job.id)

    @mock.patch(
        "elasticsearch.Elasticsearch.delete",
        side_effect=elasticsearch.TransportError("boom"),
    )
    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch("bilbyui.models.logger.exception")
    def test_delete_es_transport_failure_is_logged_and_suppressed(
        self, logger_exception_mock, lookup_users_mock, elasticsearch_update_mock, elasticsearch_delete_mock
    ):
        """
        Test that a post-commit elastic search delete transport failure is logged and suppressed,
        so the request still succeeds and the database deletion is preserved
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )

        job_id = job.id
        elasticsearch_delete_mock.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            job.delete()

        # The job should no longer exist in the database
        self.assertFalse(BilbyJob.objects.filter(id=job_id).exists())

        # The delete should have been attempted once and the transport failure logged and suppressed
        elasticsearch_delete_mock.assert_called_once()
        logger_exception_mock.assert_called_once()

    @mock.patch("elasticsearch.Elasticsearch.index")
    @mock.patch("elasticsearch.Elasticsearch.delete")
    @mock.patch("elasticsearch.Elasticsearch.update")
    def test_save_then_delete_preserves_callback_order(self, update_mock, delete_mock, index_mock):
        """
        Test that a save followed by a delete in the same transaction executes the delete callback
        and skips the stale update (the row is gone at commit time)
        """
        with self.captureOnCommitCallbacks(execute=True):
            job = BilbyJob.objects.create(
                user_id=self.user.id,
                name="Test1",
                description="first job",
                job_controller_id=2,
                private=False,
                ini_string=create_test_ini_string({"detectors": "['H1']"}),
            )
            job.delete()

        # The stale update callback must skip (row gone at commit) - no update or index write
        update_mock.assert_not_called()
        index_mock.assert_not_called()

        # The delete callback must run exactly once
        delete_mock.assert_called_once()


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class TestNonAtomicSaveSynchronous(TransactionTestCase):
    """
    Verifies that transaction.on_commit() executes immediately when there is no active
    transaction, so non-atomic saves still write to elastic search synchronously.
    """

    def setUp(self):
        self.user = User.objects.create_user(id=1, name="buffy summers", primary_email="slayer@gmail.com")
        self.user.emails = ["slayer@gmail.com"]
        self.user.authentication_methods = ["password"]
        self.user.save()

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_non_atomic_save_writes_synchronously(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that outside a transaction the elastic search update runs immediately (synchronously)
        """
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            description="first job",
            job_controller_id=2,
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

        # Without an active transaction the ES update must have run synchronously
        elasticsearch_update_mock.assert_called_once()
        self.assertIsNotNone(job.id)
