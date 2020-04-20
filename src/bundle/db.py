import os

import filelock
import pickle

# Create the Lock
lock = filelock.FileLock(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'db.lock'))
database_filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'db.pickle')


def _read_db():
    """
    Read the pickle and return the database

    :return: The read database, or an empty dict
    """
    try:
        with open(database_filename, 'rb') as f:
            return pickle.load(f)
    except:
        return {}


def _write_db(db):
    """
    Writes the database file as a pickle

    :param db: The dict to write to the database file
    :return: Nothing
    """
    with open(database_filename, 'wb') as f:
        pickle.dump(db, f)


def get_unique_job_id():
    """
    Gets a new unique job id

    :return: The new job id
    """
    # Acquire the lock
    with lock:
        # Read the database
        db = _read_db()

        # Increment the job counter
        if 'job_counter' not in db:
            db['job_counter'] = 1
        else:
            db['job_counter'] += 1

        # Save the new job counter
        _write_db(db)

        # Return the new job counter
        return db['job_counter']


def get_all_jobs():
    """
    Gets all job records for jobs in the database

    :return: An array of all current jobs in the database
    """
    # Acquire the lock
    with lock:
        # Read the database
        db = _read_db()

        # Make sure the database has a jobs entry already
        if 'jobs' not in db:
            # Create a new job array
            db['jobs'] = []

        # Return the jobs
        return db['jobs']


def get_job_by_id(job_id):
    """
    Gets a job record if one exists for the provided id

    :param job_id: The id of the job to look up
    :return: The job details if the job was found otherwise None
    """
    # Acquire the lock
    with lock:
        # Read the database
        db = _read_db()

        # Check if the job exists in the database
        if 'jobs' in db:
            for job in db['jobs']:
                if job['job_id'] == job_id:
                    # Found the job, return it
                    return job

        # No job matching the criteria was in the database
        return None


def update_job(new_job):
    """
    Updates a job record in the database if one already exists, otherwise inserts the job in to the database

    :param new_job: The job to update
    :return: None
    """
    # Acquire the lock
    with lock:
        # Read the database
        db = _read_db()

        # Make sure the database has a jobs entry already
        if 'jobs' not in db:
            # Create a new job array
            db['jobs'] = []

        # Iterate over the jobs in the database
        found = False
        for job in db['jobs']:
            # Check if this job matches the job being updated
            if job['job_id'] == new_job['job_id']:
                # Found the job, update it
                found = True
                job.update(new_job)

        # If no record was found, insert the job
        if not found:
            db['jobs'].append(new_job)

        # Save the database
        _write_db(db)


def delete_job(job):
    """
    Deletes a job record from the database

    :param job: The job to delete
    :return: None
    """
    # Acquire the lock
    with lock:
        # Read the database
        db = _read_db()

        # Make sure the database has a jobs entry already
        if 'jobs' not in db:
            return

        # Iterate over the jobs in the database
        for idx in range(len(db['jobs'])):
            # Check if this job matches the job being deleted
            if db['jobs'][idx]['job_id'] == job['job_id']:
                # Found the job, delete it
                del db['jobs'][idx]
                break

        # Save the database
        _write_db(db)

