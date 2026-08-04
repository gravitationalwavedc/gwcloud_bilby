import datetime
import logging

from bilbyui.status import JobStatus

logger = logging.getLogger(__name__)


def derive_job_status(history):
    """
    Takes a job history returned from the job controller and turns it into a final status

    :param history: The job history object returned from the job controller
    :returns: A tuple of (state, display_name, timestamp) for the most recent job status
    """

    if not history:
        return JobStatus.DRAFT, "Unknown", None

    latest = max(history, key=lambda h: datetime.datetime.strptime(h["timestamp"], "%Y-%m-%d %H:%M:%S.%f UTC"))
    state = latest["state"]
    display_name = JobStatus.display_name(state)
    timestamp = datetime.datetime.strptime(latest["timestamp"], "%Y-%m-%d %H:%M:%S.%f UTC")
    logger.info("Derived job status: state=%s, display_name=%s, timestamp=%s", state, display_name, timestamp)
    return (state, display_name, timestamp)
