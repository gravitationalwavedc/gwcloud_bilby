from pathlib import Path

import settings
from scheduler.condor import CondorScheduler
from scheduler.scheduler import EScheduler
from scheduler.slurm import SlurmScheduler
from settings import job_directory


def working_directory(details, *args, **kwargs):
    str(Path(job_directory, str(details['job_id'])))


def get_scheduler():
    """
    Gets the scheduler class based on the scheduler from settings

    :return: The scheduler class
    """
    if settings.scheduler == EScheduler.SLURM:
        return SlurmScheduler()

    if settings.scheduler == EScheduler.CONDOR:
        return CondorScheduler()

    return None
