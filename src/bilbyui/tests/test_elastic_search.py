from unittest import mock

import elasticsearch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings

from bilbyui.tests.test_utils import create_test_ini_string, generate_elastic_doc
from bilbyui.tests.testcases import BilbyTestCase

User = get_user_model()


@override_settings(IGNORE_ELASTIC_SEARCH=False)
class TestElasticSearch(BilbyTestCase):
    def setUp(self):
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")

    def request_lookup_users_mock(*args, **kwargs):
        user = User.objects.first()
        if user:
            return True, [
                {"userId": user.id, "username": user.username, "firstName": user.first_name, "lastName": user.last_name}
            ]
        return False, []

    def request_elasticsearch_update_mock_raises(*args, **kwargs):
        raise elasticsearch.NotFoundError("Exists", None, None)

    @mock.patch("elasticsearch.Elasticsearch.update", side_effect=request_elasticsearch_update_mock_raises)
    @mock.patch("elasticsearch.Elasticsearch.index")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_create_document_basic(
        self, lookup_users_mock, elasticsearch_index_mock, elasticsearch_update_mock_raises
    ):
        """
        Test that if we create a job, the elastic search index function is called as expected.
        Also tests that if update raises a elasticsearch.NotFoundError exception, that index is called to insert the
        record in elastic search
        """
        from bilbyui.models import BilbyJob

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
        self.assertEqual(lookup_users_mock.mock_calls[0].args, ([1], 0))

        # Update should have been called once, which then raises elasticsearch.NotFoundError
        self.assertEqual(elasticsearch_update_mock_raises.call_count, 1)

        # Verify the document
        self.assertEqual(elasticsearch_index_mock.mock_calls[0].kwargs["index"], settings.ELASTIC_SEARCH_INDEX)
        self.assertEqual(elasticsearch_index_mock.mock_calls[0].kwargs["id"], job.id)

        # Make sure this test has no labels or an event id
        doc = generate_elastic_doc(job, self.user)

        self.assertEqual(doc["labels"], [])
        self.assertEqual(doc["eventId"], None)

        self.assertDictEqual(elasticsearch_index_mock.mock_calls[0].kwargs["document"], doc)

    @mock.patch("elasticsearch.Elasticsearch.update", side_effect=request_elasticsearch_update_mock_raises)
    @mock.patch("elasticsearch.Elasticsearch.index")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_create_document_complete(
        self, lookup_users_mock, elasticsearch_index_mock, elasticsearch_update_mock_raises
    ):
        """
        Test that if we create a job with event id and labels, that the elastic search index function
        is called as expected
        Also tests that if update raises a elasticsearch.NotFoundError exception, that index is called to insert the
        record in elastic search
        """
        from bilbyui.models import BilbyJob, EventID, Label

        label1 = Label.objects.create(name="label 1", description="my label 1", protected=True)
        label2 = Label.objects.create(name="label 2", description="my label 2", protected=False)

        event_id = EventID.create(
            "GW123456_123456", 12345678, trigger_id="S123456a", nickname="Test Nick", is_ligo_event=True
        )

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
        self.assertEqual(elasticsearch_index_mock.mock_calls[-1].kwargs["index"], settings.ELASTIC_SEARCH_INDEX)
        self.assertEqual(elasticsearch_index_mock.mock_calls[-1].kwargs["id"], job.id)

        # Make sure this test has no labels or an event id
        doc = generate_elastic_doc(job, self.user)

        self.assertNotEqual(doc["labels"], [])
        self.assertNotEqual(doc["eventId"], None)

        self.assertDictEqual(elasticsearch_index_mock.mock_calls[-1].kwargs["document"], doc)

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_update_document(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that update is called with the expected document
        """
        from bilbyui.models import BilbyJob

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
        self.assertEqual(lookup_users_mock.mock_calls[0].args, ([1], 0))

        # Update should have been called once
        self.assertEqual(elasticsearch_update_mock.call_count, 1)

        # Verify the document
        self.assertEqual(elasticsearch_update_mock.mock_calls[0].kwargs["index"], settings.ELASTIC_SEARCH_INDEX)
        self.assertEqual(elasticsearch_update_mock.mock_calls[0].kwargs["id"], job.id)

        # Make sure this test has no labels or an event id
        doc = generate_elastic_doc(job, self.user)

        self.assertEqual(doc["labels"], [])
        self.assertEqual(doc["eventId"], None)

        self.assertDictEqual(elasticsearch_update_mock.mock_calls[0].kwargs["doc"], doc)

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_event_id_update(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that if we update an event id associated with a job, that the job's elastic search update
        is triggered
        """
        from bilbyui.models import BilbyJob, EventID

        event_id = EventID.create(
            "GW123456_123456", 12345678, trigger_id="S123456a", nickname="Test Nick", is_ligo_event=True
        )

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
            elasticsearch_update_mock.mock_calls[-1].kwargs["doc"], generate_elastic_doc(job, self.user)
        )

    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_save_label_update(self, lookup_users_mock, elasticsearch_update_mock):
        """
        Test that if we update a label associated with a job, that the job's elastic search update
        is triggered
        """
        from bilbyui.models import BilbyJob, Label

        label1 = Label.objects.create(name="label 1", description="my label 1", protected=True)

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
            elasticsearch_update_mock.mock_calls[-1].kwargs["doc"], generate_elastic_doc(job, self.user)
        )

    @mock.patch("elasticsearch.Elasticsearch.delete")
    @mock.patch("elasticsearch.Elasticsearch.update")
    @mock.patch("bilbyui.models.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_job_delete_remove_document(self, request_lookup_users, elastic_search_update, elastic_search_delete):
        """
        Test that when a bilby job is deleted, the elastic search record is also deleted
        """
        from bilbyui.models import BilbyJob

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
            elastic_search_delete.mock_calls[0].kwargs, {"index": settings.ELASTIC_SEARCH_INDEX, "id": job_id}
        )
