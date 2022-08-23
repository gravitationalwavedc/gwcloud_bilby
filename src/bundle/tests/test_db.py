import os
import shutil
from pathlib import Path
import random
import string

import settings
from db import get_unique_job_id, update_job, get_job_by_id, get_all_jobs
from scheduler.scheduler import EScheduler
from scheduler.status import JobStatus
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch, Mock
import multiprocessing


class TestCacheDir(TestCase):
    def test_cache_dir(self):
        from db import CACHE_FOLDER
        self.assertEqual(str(Path(__file__).resolve().parent.parent / '.cache'), CACHE_FOLDER)


def generate_random_job_details(job_id=None):
    return {
        'job_id': job_id or get_unique_job_id(),
        'details': {
            'data': ''.join((random.choice(string.ascii_lowercase) for _ in range(random.randint(10, 100))))
        }
    }


def call_unique_job_id(_):
    return get_unique_job_id()


def call_get_all_jobs(_):
    job = generate_random_job_details()
    update_job(job)
    return get_all_jobs(), job


def call_get_job_by_id(_):
    job = generate_random_job_details()
    update_job(job)
    return get_job_by_id(job['job_id']), job


@patch('db.CACHE_FOLDER', '.cache.test')
class TestStatus(TestCase):
    def setUp(self):
        self.clean_cache()
        self.manager = multiprocessing.Manager()
        self.return_list = self.manager.list()

    def tearDown(self):
        self.clean_cache()

    def clean_cache(self):
        shutil.rmtree('.cache.test', ignore_errors=True)

    def test_get_unique_job_id(self):
        BATCH_SIZE = 1000
        with multiprocessing.Pool(4) as p:
            result = list(p.imap(call_unique_job_id, range(BATCH_SIZE)))

        result.sort()
        self.assertEqual(len(result), BATCH_SIZE)
        for index in range(BATCH_SIZE):
            # Add one since the first unique job id will always be 1
            self.assertEqual(result[index], index+1)

    def test_get_all_jobs(self):
        BATCH_SIZE = 1000
        with multiprocessing.Pool(4) as p:
            result = list(p.imap(call_get_all_jobs, range(BATCH_SIZE)))

        self.assertEqual(len(result), BATCH_SIZE)
        for index in range(BATCH_SIZE):
            item = list(filter(lambda x: x['job_id'] == result[index][1]['job_id'], result[index][0]))
            self.assertEqual(len(item), 1)
            self.assertDictEqual(item[0], result[index][1])

    def test_get_job_by_id(self):
        BATCH_SIZE = 1000
        with multiprocessing.Pool(4) as p:
            result = list(p.imap(call_get_job_by_id, range(BATCH_SIZE)))

        self.assertEqual(len(result), BATCH_SIZE)
        for index in range(BATCH_SIZE):
            self.assertDictEqual(result[index][0], result[index][1])

    def update_job(self):
        BATCH_SIZE = 1000
        with multiprocessing.Pool(4) as p:
            result = list(p.imap(call_update_job, range(BATCH_SIZE)))

        self.assertEqual(len(result), BATCH_SIZE)
        for index in range(BATCH_SIZE):
            self.assertDictEqual(result[index][0], result[index][1])

    def delete_job(self):
        pass