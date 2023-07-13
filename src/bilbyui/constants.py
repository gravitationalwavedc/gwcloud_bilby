# Can NOT be an enum
class BilbyJobType:
    # If the job was created by either new job or new ini job
    NORMAL = 0
    # Job was created via a job upload
    UPLOADED = 1
    # Job was created via a gwosc job upload
    GWOSC = 2


BILBY_JOB_TYPE_CHOICES = (
    (BilbyJobType.NORMAL, "Normal Job"),
    (BilbyJobType.UPLOADED, "Uploaded Job"),
    (BilbyJobType.GWOSC, "GWOSC Job"),
)
