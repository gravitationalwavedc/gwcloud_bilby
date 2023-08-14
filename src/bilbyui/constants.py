# Can NOT be an enum
class BilbyJobType:
    # If the job was created by either new job or new ini job
    NORMAL = 0
    # Job was created via a job upload
    UPLOADED = 1
    # Job is a external result job
    EXTERNAL = 2


BILBY_JOB_TYPE_CHOICES = (
    (BilbyJobType.NORMAL, "Normal Job"),
    (BilbyJobType.UPLOADED, "Uploaded Job"),
    (BilbyJobType.EXTERNAL, "External Job"),
)
