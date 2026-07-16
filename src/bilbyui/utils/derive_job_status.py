import datetime

from bilbyui.status import JobStatus


def derive_job_status(history):
    """
    Takes a job history returned from the job controller and turns it into a final status

    :param history: The job history object returned from the job controller
    """

    # Order the histories by timestamp
    history_items = [
        {"timestamp": datetime.datetime.strptime(h["timestamp"], "%Y-%m-%d %H:%M:%S.%f UTC"), "data": h}
        for h in history
    ]

    history_items.sort(key=lambda x: x["timestamp"], reverse=True)

    if history_items:
        return (
            history_items[0]["data"]["state"],
            JobStatus.display_name(history_items[0]["data"]["state"]),
            history_items[0]["timestamp"],
        )

    return JobStatus.DRAFT, "Unknown", None
