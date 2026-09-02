from types import SimpleNamespace

from django.test import override_settings

from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import _iter_es_job_records


def _job(job_id):
    return SimpleNamespace(id=job_id)


def _record(job_id, source=None):
    record = {"_id": str(job_id)}
    if source is not None:
        record["_source"] = source
    return record


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestIterEsJobRecords(BilbyTestCase):
    def test_skips_record_when_id_not_in_jobs(self):
        jobs = {1: _job(1)}
        records = [_record(1, source={"user": "buffy"}), _record(999, source={"user": "buffy"})]

        self.assertEqual(list(_iter_es_job_records(records, jobs, page_size=10)), [(records[0], jobs[1])])

    def test_skips_record_without_dict_source(self):
        jobs = {1: _job(1)}
        records = [
            _record(1),
            _record(1, source="not-a-dict"),
            _record(1, source={"user": "buffy"}),
        ]

        self.assertEqual(list(_iter_es_job_records(records, jobs, page_size=10)), [(records[2], jobs[1])])

    def test_yields_valid_record_and_job(self):
        jobs = {1: _job(1), 2: _job(2)}
        records = [_record(1, source={"user": "buffy"}), _record(2, source={"user": "willow"})]

        self.assertEqual(
            list(_iter_es_job_records(records, jobs, page_size=10)),
            [(records[0], jobs[1]), (records[1], jobs[2])],
        )

    def test_page_size_slices_records(self):
        jobs = {i: _job(i) for i in range(1, 6)}
        records = [_record(i, source={"user": "buffy"}) for i in range(1, 6)]

        self.assertEqual(
            list(_iter_es_job_records(records, jobs, page_size=2)),
            [(records[0], jobs[1]), (records[1], jobs[2])],
        )
