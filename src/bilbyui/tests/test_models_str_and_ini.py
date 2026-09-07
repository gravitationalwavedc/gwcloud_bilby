from unittest import mock

from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, IniKeyValue, Label
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase


class TestModelStrAndIniGuards(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.label = Label.objects.create(name="Test Label")
        cls.event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=1126259462.391,
        )
        cls.job = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="Test_Job",
            description="Test job description",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_label_str(self):
        self.assertEqual(str(self.label), "Label: Test Label")

    def test_event_id_str(self):
        self.assertEqual(str(self.event_id), "EventID: GW123456_123456")

    def test_bilby_job_str(self):
        self.assertEqual(str(self.job), "Bilby Job: Test_Job")

    def test_save_skips_ini_updates_when_empty(self):
        # A job with no ini_string should still save without error and should skip
        # the ini parsing / elastic search update steps.
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Empty_Ini_Job",
            description="Job without an ini string",
            private=False,
            ini_string="",
        )
        job.save()
        job.refresh_from_db()
        self.assertEqual(job.name, "Empty_Ini_Job")

    def test_elastic_search_update_returns_when_ignored(self):
        # With IGNORE_ELASTIC_SEARCH enabled elastic_search_update returns early before
        # touching elastic search.
        self.assertIsNone(self.job.elastic_search_update())

    def test_elastic_search_update_returns_when_empty_ini(self):
        # With elastic search enabled but no ini_string, elastic_search_update returns early
        # before connecting to elastic search.
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Empty_Ini_ES_Job",
            description="Job without an ini string",
            private=False,
            ini_string="",
        )
        with override_settings(IGNORE_ELASTIC_SEARCH=False):
            self.assertIsNone(job.elastic_search_update())

    def test_elastic_search_update_ignores_malformed_ini_value(self):
        # A malformed/legacy IniKeyValue JSON value must not crash elastic_search_update;
        # the offending key is indexed as None and the remaining keys are parsed normally.
        IniKeyValue.objects.create(
            job=self.job,
            key="corrupt",
            value="not-json{{",
            index=0,
            processed=False,
        )
        with override_settings(IGNORE_ELASTIC_SEARCH=False):
            with (
                mock.patch(
                    "bilbyui.models.request_lookup_users",
                    return_value=(True, [{"id": self.user.id, "name": "buffy summers"}]),
                ),
                mock.patch("elasticsearch.Elasticsearch.update") as update_mock,
                mock.patch("elasticsearch.Elasticsearch.index"),
            ):
                self.job.elastic_search_update()

        self.assertEqual(update_mock.call_count, 1)
        doc = update_mock.call_args.kwargs["doc"]
        self.assertIn("corrupt", doc["ini"])
        self.assertIsNone(doc["ini"]["corrupt"])


class TestLabelAndEventIdReindexSignals(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.label = Label.objects.create(name="Signal Label")
        cls.event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=1126259462.391,
        )

    def _create_job(self, name, event_id=None):
        return BilbyJob.objects.create(
            user_id=self.user.id,
            name=name,
            description="Job description",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
            event_id=event_id,
        )

    def test_label_save_reindexes_related_jobs(self):
        job = self._create_job("Label_Related_Job")
        job.labels.add(self.label)
        with mock.patch.object(BilbyJob, "elastic_search_update") as es_update:
            self.label.save()
        self.assertEqual(es_update.call_count, 1)

    def test_label_save_noop_without_jobs(self):
        orphan_label = Label.objects.create(name="Orphan Label")
        with mock.patch.object(BilbyJob, "elastic_search_update") as es_update:
            orphan_label.save()
        es_update.assert_not_called()

    def test_event_id_save_reindexes_related_jobs(self):
        self._create_job("Event_Related_Job", event_id=self.event_id)
        with mock.patch.object(BilbyJob, "elastic_search_update") as es_update:
            self.event_id.save()
        self.assertEqual(es_update.call_count, 1)

    def test_event_id_save_noop_without_jobs(self):
        orphan_event = EventID.objects.create(
            event_id="GW654321_654321",
            trigger_id="S654321a",
            nickname="GW654321",
            is_ligo_event=False,
            gps_time=1126259462.391,
        )
        with mock.patch.object(BilbyJob, "elastic_search_update") as es_update:
            orphan_event.save()
        es_update.assert_not_called()
