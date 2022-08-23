import json
import multiprocessing
import random
import shutil
import string
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import diskcache

from db import get_next_unique_job_id, create_or_update_job, get_job_by_id, delete_job


class TestCacheDir(TestCase):
    def test_cache_dir(self):
        from db import CACHE_FOLDER, FLUFL_LOCK_FILE
        self.assertEqual(str(Path(__file__).resolve().parent.parent / '.cache'), CACHE_FOLDER)
        self.assertEqual(str(Path(CACHE_FOLDER) / '.db.lock'), FLUFL_LOCK_FILE)


def generate_random_job_details(job_id=None):
    return {
        'job_id': job_id or get_next_unique_job_id(),
        'details': {
            'data': ''.join((random.choice(string.ascii_lowercase) for _ in range(random.randint(10, 100))))
        }
    }


def call_unique_job_id(_):
    return get_next_unique_job_id()


def call_get_job_by_id(_):
    job = generate_random_job_details()
    create_or_update_job(job)
    return get_job_by_id(job['job_id']), job


def call_update_job(job_id):
    # +1 since job ids begin from 1, not 0
    job = generate_random_job_details(job_id+1)
    create_or_update_job(job)
    job = generate_random_job_details(job_id+1)
    create_or_update_job(job)
    return get_job_by_id(job['job_id']), job


def call_delete_job(_):
    job = generate_random_job_details()
    create_or_update_job(job)
    delete_job(job)
    return get_job_by_id(job['job_id'])


@patch('db.CACHE_FOLDER', '.cache.test')
@patch('db.FLUFL_LOCK_FILE', '.cache.test/.db.lock')
class TestStatus(TestCase):
    def setUp(self):
        self.clean_cache()
        self.manager = multiprocessing.Manager()
        self.return_list = self.manager.list()
        self.BATCH_SIZE = 100
        self.POOL_SIZE = 4

    def tearDown(self):
        self.clean_cache()

    def clean_cache(self):
        shutil.rmtree('.cache.test', ignore_errors=True)
        Path('.cache.test').mkdir(parents=True)

    def test_get_unique_job_id(self):
        with multiprocessing.Pool(self.POOL_SIZE) as p:
            result = list(p.imap(call_unique_job_id, range(self.BATCH_SIZE)))

        result.sort()
        self.assertEqual(len(result), self.BATCH_SIZE)
        for index in range(self.BATCH_SIZE):
            # Add one since the first unique job id will always be 1
            self.assertEqual(result[index], index+1)

        self.assertEqual(call_unique_job_id(None), self.BATCH_SIZE+1)

    def test_get_job_by_id(self):
        with multiprocessing.Pool(self.POOL_SIZE) as p:
            result = list(p.imap(call_get_job_by_id, range(self.BATCH_SIZE)))

        self.assertEqual(len(result), self.BATCH_SIZE)
        for index in range(self.BATCH_SIZE):
            self.assertDictEqual(result[index][0], result[index][1])

        result = call_get_job_by_id(None)

        self.assertDictEqual(result[0], result[1])

    def test_update_job(self):
        with multiprocessing.Pool(self.POOL_SIZE) as p:
            result = list(p.imap(call_update_job, range(self.BATCH_SIZE)))

        self.assertEqual(len(result), self.BATCH_SIZE)
        for index in range(self.BATCH_SIZE):
            self.assertDictEqual(result[index][0], result[index][1])

        result = call_update_job(1)

        self.assertDictEqual(result[0], result[1])

    def test_delete_job(self):
        with multiprocessing.Pool(self.POOL_SIZE) as p:
            result = list(p.imap(call_delete_job, range(self.BATCH_SIZE)))

        self.assertEqual(len(result), self.BATCH_SIZE)
        for index in range(self.BATCH_SIZE):
            self.assertEqual(result[index], None)

        cache = diskcache.Cache('.cache.test')
        self.assertEqual(json.loads(cache['jobs']), [])

        call_delete_job(None)

        self.assertEqual(json.loads(cache['jobs']), [])

        with self.assertRaises(Exception):
            job = generate_random_job_details()
            delete_job(job)
