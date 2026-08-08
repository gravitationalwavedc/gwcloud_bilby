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

    def parse_timestamp(entry):
        return datetime.datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S.%f UTC")

    latest = max(history, key=parse_timestamp)
    state = latest["state"]
    display_name = JobStatus.display_name(state)
    timestamp = parse_timestamp(latest)
    logger.info("Derived job status: state=%s, display_name=%s, timestamp=%s", state, display_name, timestamp)
    return (state, display_name, timestamp)
