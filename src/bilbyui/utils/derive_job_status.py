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

    if not history or not isinstance(history, list):
        return JobStatus.DRAFT, "Unknown", None

    def parse_timestamp(entry):
        timestamp = entry.get("timestamp")
        if not isinstance(timestamp, str):
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f UTC", "%Y-%m-%d %H:%M:%S UTC"):
            try:
                return datetime.datetime.strptime(timestamp, fmt)
            except ValueError:
                continue
        return None

    valid_entries = []
    for entry in history:
        if isinstance(entry, dict) and "state" in entry:
            timestamp = parse_timestamp(entry)
            if timestamp is not None:
                valid_entries.append((entry, timestamp))
    if not valid_entries:
        return JobStatus.DRAFT, "Unknown", None

    latest, timestamp = max(valid_entries, key=lambda item: item[1])
    state = latest["state"]
    display_name = JobStatus.display_name(state)
    logger.debug("Derived job status: state=%s, display_name=%s, timestamp=%s", state, display_name, timestamp)
    return (state, display_name, timestamp)
