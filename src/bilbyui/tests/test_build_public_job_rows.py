from django.test import override_settings

from bilbyui.constants import BilbyJobType
from bilbyui.models import BilbyJob, EventID, Label
from bilbyui.status import JobStatus
from bilbyui.tests.test_utils import create_test_ini_string, generate_elastic_doc
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _build_public_job_rows

TEST_USER = {"name": "buffy summers", "id": 1}


def _make_record(job):
    return {"_id": str(job.id), "_source": generate_elastic_doc(job, TEST_USER)}


def _result(records, jobs, job_controller_jobs=None, page_size=20):
    return {
        "records": records,
        "page_size": page_size,
        "job_controller_jobs": job_controller_jobs or {},
        "jobs": jobs,
    }


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestBuildPublicJobRows(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user(id=1, name="buffy summers", primary_email="buffy@test.com")

    def _create_job(self, **kwargs):
        defaults = {
            "user_id": self.user.id,
            "name": "Test job",
            "description": "Test description",
            "job_controller_id": 1001,
            "private": False,
            "ini_string": create_test_ini_string({"detectors": "['H1']", "label": "Test job"}),
        }
        defaults.update(kwargs)
        return BilbyJob.objects.create(**defaults)

    def test_empty_and_missing_jobs(self):
        self.assertEqual(_build_public_job_rows(_result([], {})), [])
        job = self._create_job()
        self.assertEqual(_build_public_job_rows(_result([_make_record(job)], {})), [])

    def test_malformed_record_missing_user_and_job_keys(self):
        job = self._create_job()
        record = {"_id": str(job.id), "_source": {}}
        rows = _build_public_job_rows(_result([record], {job.id: job}))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user"], "")
        self.assertEqual(rows[0]["name"], "")
        self.assertEqual(rows[0]["description"], "")

    def test_row_building_skips_missing_or_non_dict_source(self):
        job = self._create_job()

        records = [
            {"_id": str(job.id)},
            {"_id": str(job.id), "_source": "not-a-dict"},
            {"_id": str(job.id), "_source": generate_elastic_doc(job, TEST_USER)},
        ]
        rows = _build_public_job_rows(_result(records, {job.id: job}))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Test job")
        self.assertEqual(rows[0]["user"], "buffy summers")

    def test_record_with_null_user_and_job_sections(self):
        job = self._create_job()
        record = {"_id": str(job.id), "_source": {"user": None, "job": None}}
        rows = _build_public_job_rows(_result([record], {job.id: job}))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user"], "")
        self.assertEqual(rows[0]["name"], "")
        self.assertEqual(rows[0]["description"], "")

    def test_normal_job_statuses(self):
        with_controller = self._create_job(job_type=BilbyJobType.NORMAL)
        without_controller = self._create_job(
            name="No controller", job_controller_id=1002, job_type=BilbyJobType.NORMAL
        )
        controller_jobs = {
            with_controller.id: {"history": [{"state": JobStatus.COMPLETED, "timestamp": "2020-01-01 00:00:00 UTC"}]},
        }
        jobs = {with_controller.id: with_controller, without_controller.id: without_controller}
        records = [_make_record(with_controller), _make_record(without_controller)]

        rows = _build_public_job_rows(_result(records, jobs, job_controller_jobs=controller_jobs))

        self.assertEqual(rows[0]["status_name"], "Completed")
        self.assertEqual(rows[0]["status_badge_class"], "primary")
        self.assertEqual(rows[0]["user"], "buffy summers")
        self.assertEqual(rows[1]["status_name"], "Unknown")
        self.assertEqual(rows[1]["status_badge_class"], "dark")

    def test_normal_job_with_empty_history(self):
        job = self._create_job(job_type=BilbyJobType.NORMAL)
        controller_jobs = {job.id: {"history": []}}
        rows = _build_public_job_rows(_result([_make_record(job)], {job.id: job}, job_controller_jobs=controller_jobs))

        self.assertEqual(rows[0]["status_name"], "Unknown")
        self.assertEqual(rows[0]["status_badge_class"], "dark")

    def test_normal_job_with_missing_history_key(self):
        job = self._create_job(job_type=BilbyJobType.NORMAL)
        controller_jobs = {job.id: {}}
        rows = _build_public_job_rows(_result([_make_record(job)], {job.id: job}, job_controller_jobs=controller_jobs))

        self.assertEqual(rows[0]["status_name"], "Unknown")
        self.assertEqual(rows[0]["status_badge_class"], "dark")

    def test_normal_job_uses_latest_history_entry(self):
        job = self._create_job(job_type=BilbyJobType.NORMAL)
        controller_jobs = {
            job.id: {
                "history": [
                    {"state": JobStatus.RUNNING, "timestamp": "2020-01-01 00:00:00 UTC"},
                    {"state": JobStatus.COMPLETED, "timestamp": "2020-01-02 00:00:00 UTC"},
                ]
            },
        }
        rows = _build_public_job_rows(_result([_make_record(job)], {job.id: job}, job_controller_jobs=controller_jobs))

        self.assertEqual(rows[0]["status_name"], "Completed")
        self.assertEqual(rows[0]["status_badge_class"], "primary")

    def test_uploaded_and_external_job_status(self):
        for job_type in (BilbyJobType.UPLOADED, BilbyJobType.EXTERNAL):
            with self.subTest(job_type=job_type):
                job = self._create_job(job_type=job_type, name=f"Job {job_type}")
                rows = _build_public_job_rows(_result([_make_record(job)], {job.id: job}))
                self.assertEqual(rows[0]["status_name"], "Completed")
                self.assertEqual(rows[0]["status_badge_class"], "primary")

    def test_unknown_job_type_and_running_badge(self):
        unknown = self._create_job(job_type=99)
        running = self._create_job(name="Running", job_controller_id=1003, job_type=BilbyJobType.NORMAL)
        controller_jobs = {
            running.id: {"history": [{"state": JobStatus.RUNNING, "timestamp": "2020-01-01 00:00:00 UTC"}]}
        }
        jobs = {unknown.id: unknown, running.id: running}
        records = [_make_record(unknown), _make_record(running)]

        rows = _build_public_job_rows(_result(records, jobs, job_controller_jobs=controller_jobs))

        self.assertEqual(rows[0]["status_name"], "Unknown")
        self.assertEqual(rows[1]["status_name"], "Running")
        self.assertEqual(rows[1]["status_badge_class"], "info")

    def test_page_size_and_null_description(self):
        jobs = [self._create_job(name=f"Job {i}", job_controller_id=2000 + i) for i in range(3)]
        jobs[2].description = None
        jobs[2].save()
        rows = _build_public_job_rows(_result([_make_record(j) for j in jobs], {j.id: j for j in jobs}, page_size=2))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "Job 0")
        self.assertEqual(rows[1]["name"], "Job 1")

    def test_event_ids_and_labels(self):
        event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        label = Label.objects.create(name="Production Run", description="production")
        job = self._create_job(event_id=event_id, job_type=BilbyJobType.UPLOADED, description=None)
        job.labels.add(label)

        rows = _build_public_job_rows(_result([_make_record(job)], {job.id: job}))

        self.assertEqual(rows[0]["description"], "")
        self.assertEqual(rows[0]["event_id_values"], ["GW123456_123456", "S123456a", "GW123456"])
        self.assertEqual(list(rows[0]["labels"]), [label])
