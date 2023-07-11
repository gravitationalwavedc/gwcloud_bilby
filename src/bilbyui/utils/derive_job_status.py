import datetime

from bilbyui.status import JobStatus


def derive_job_status(history):
    """
    Takes a job history returned from the job controller and turns it in to a final status

    :param history: The job history object returned from the job controller
    """

    history_items = []
    # Order the histories by timestamp
    for h in history:
        history_items.append(
            {"timestamp": datetime.datetime.strptime(h["timestamp"], "%Y-%m-%d %H:%M:%S.%f UTC"), "data": h}
        )

    history_items.sort(key=lambda x: x["timestamp"], reverse=True)

    if len(history_items):
        return (
            history_items[0]["data"]["state"],
            JobStatus.display_name(history_items[0]["data"]["state"]),
            history_items[0]["timestamp"],
        )

    return JobStatus.DRAFT, "Unknown", None
