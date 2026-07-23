class JobStatus:
    # A job that is currently in draft state - it is not yet submitted
    DRAFT = 0
    # A job is pending if it is currently waiting for a cluster to submit the job to
    # (ie, all available clusters are offline)
    PENDING = 10
    # A job is submitting if the job has been submitted but is waiting for the client to acknowledge it has received
    # the job submission command
    SUBMITTING = 20
    # A job is submitted if it is submitted on a cluster
    SUBMITTED = 30
    # A job is queued if it is in the queue on the cluster it is to run on
    QUEUED = 40
    # A job is running if it is currently running on the cluster it is to run on
    RUNNING = 50
    # A job is cancelling if the job has been cancelled but is waiting for the client to acknowledge it has received
    # the job cancellation command
    CANCELLING = 60
    # A job is cancelled if it was queued or running and was then cancelled
    CANCELLED = 70
    # A job is deleting if the job has been deleted but is waiting for the client to acknowledge it has received
    # the job deletion command
    DELETING = 80
    # A job is deleted when its data has been cleaned up and only it lives on the UI database for future clone,
    # reference, etc.
    DELETED = 90
    # A job is in error if it crashed at any point during its execution
    ERROR = 400
    # A job that has exceeded its wall time
    WALL_TIME_EXCEEDED = 401
    # A job that crashed because it ran out of memory
    OUT_OF_MEMORY = 402
    # A job is completed if it is finished running on the cluster without error
    COMPLETED = 500

    @staticmethod
    def display_name(status):
        if status == JobStatus.DRAFT:
            return "Draft"
        if status == JobStatus.PENDING:
            return "Pending"
        if status == JobStatus.SUBMITTING:
            return "Submitting"
        if status == JobStatus.SUBMITTED:
            return "Submitted"
        if status == JobStatus.QUEUED:
            return "Queued"
        if status == JobStatus.RUNNING:
            return "Running"
        if status == JobStatus.CANCELLING:
            return "Cancelling"
        if status == JobStatus.CANCELLED:
            return "Cancelled"
        if status == JobStatus.DELETING:
            return "Deleting"
        if status == JobStatus.DELETED:
            return "Deleted"
        if status == JobStatus.ERROR:
            return "Error"
        if status == JobStatus.WALL_TIME_EXCEEDED:
            return "Wall Time Exceeded"
        if status == JobStatus.OUT_OF_MEMORY:
            return "Out of Memory"
        if status == JobStatus.COMPLETED:
            return "Completed"
        return "Unknown"
