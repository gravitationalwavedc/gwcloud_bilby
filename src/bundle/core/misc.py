import os

import settings
from scheduler.slurm import SlurmScheduler
from settings import job_directory


def working_directory(details, *args, **kwargs):
    return os.path.join(job_directory + str(details['job_id']))


def get_scheduler():
    """
    Gets the scheduler class based on the scheduler from settings

    :return: The scheduler class
    """
    if settings.scheduler == "slurm":
        return SlurmScheduler()

    return None
