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

    # Order the histories by timestamp
    history_items = [
        {"timestamp": datetime.datetime.strptime(h["timestamp"], "%Y-%m-%d %H:%M:%S.%f UTC"), "data": h}
        for h in history
    ]

    history_items.sort(key=lambda x: x["timestamp"], reverse=True)

    if history_items:
        state = history_items[0]["data"]["state"]
        display_name = JobStatus.display_name(state)
        timestamp = history_items[0]["timestamp"]
        logger.info("Derived job status: state=%s, display_name=%s, timestamp=%s", state, display_name, timestamp)
        return (state, display_name, timestamp)

    return JobStatus.DRAFT, "Unknown", None
