import logging
from pathlib import Path

import settings
from scheduler.condor import CondorScheduler
from scheduler.scheduler import EScheduler
from scheduler.slurm import SlurmScheduler

logger = logging.getLogger(__name__)


def working_directory(details, *args, **kwargs):
    if isinstance(details, dict):
        return str(Path(settings.job_directory, str(details["job_id"])))

    return settings.default_working_directory


def get_scheduler():
    """
    Gets the scheduler class based on the scheduler from settings

    :return: The scheduler class
    """
    if settings.scheduler == EScheduler.SLURM:
        return SlurmScheduler()

    if settings.scheduler == EScheduler.CONDOR:
        return CondorScheduler()

    logger.warning("Unknown scheduler: %s", settings.scheduler)
    return None
