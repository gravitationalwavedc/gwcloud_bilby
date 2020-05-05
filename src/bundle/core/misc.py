import os

from settings import job_directory


def working_directory(details, job_data):
    return os.path.join(job_directory + str(details['job_id']))
