import json
from pathlib import Path

import diskcache


# Declared here so that it can be overridden in tests
CACHE_FOLDER = str(Path(__file__).resolve().parent / '.cache')

# Global constants
JOB_COUNTER_IDENTIFIER = 'job_counter'
JOBS_IDENTIFIER = 'jobs'


def get_next_unique_job_id():
    """
    Gets a new unique job id

    :return: The new job id
    """
    with diskcache.Cache(CACHE_FOLDER) as cache, cache.transact():
        cache.add(JOB_COUNTER_IDENTIFIER, 0)
        return cache.incr(JOB_COUNTER_IDENTIFIER)


def get_all_jobs():
    """
    Gets all job records for jobs in the database

    :return: An array of all current jobs in the database
    """
    with diskcache.Cache(CACHE_FOLDER) as cache, cache.transact():
        cache.add(JOBS_IDENTIFIER, json.dumps([]))
        return json.loads(cache[JOBS_IDENTIFIER])


def get_job_by_id(job_id):
    """
    Gets a job record if one exists for the provided id

    :param job_id: The id of the job to look up
    :return: The job details if the job was found otherwise None
    """
    with diskcache.Cache(CACHE_FOLDER) as cache, cache.transact():
        cache.add(JOBS_IDENTIFIER, json.dumps([]))
        jobs = json.loads(cache[JOBS_IDENTIFIER])
        for job in jobs:
            if job['job_id'] == job_id:
                return job

    return None


def create_or_update_job(new_job):
    """
    Updates a job record in the database if one already exists, otherwise inserts the job in to the database

    :param new_job: The job to update
    :return: None
    """
    with diskcache.Cache(CACHE_FOLDER) as cache, cache.transact():
        cache.add(JOBS_IDENTIFIER, json.dumps([]))
        jobs = json.loads(cache[JOBS_IDENTIFIER])

        # Iterate over the jobs in the database
        found = False
        for job in jobs:
            # Check if this job matches the job being updated
            if job['job_id'] == new_job['job_id']:
                # Found the job, update it
                found = True
                job.update(new_job)
                break

        # If no record was found, insert the job
        if not found:
            jobs.append(new_job)

        cache.set(JOBS_IDENTIFIER, json.dumps(jobs))


def delete_job(job):
    """
    Deletes a job record from the database

    Raises an exception if the job is not found in the database

    :param job: The job to delete
    :return: None
    """
    with diskcache.Cache(CACHE_FOLDER) as cache, cache.transact():
        cache.add(JOBS_IDENTIFIER, json.dumps([]))
        jobs = json.loads(cache[JOBS_IDENTIFIER])

        # Iterate over the jobs in the database
        found = False
        for idx in range(len(jobs)):
            # Check if this job matches the job being deleted
            if jobs[idx]['job_id'] == job['job_id']:
                # Found the job, delete it
                del jobs[idx]
                found = True
                break

        if not found:
            raise Exception(f"Job {job['job_id']} was not found in the database.")

        # Save the database
        cache.set(JOBS_IDENTIFIER, json.dumps(jobs))
