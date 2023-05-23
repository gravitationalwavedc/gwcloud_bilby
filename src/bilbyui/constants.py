# Can NOT be an enum
class BilbyJobType:
    # If the job was created by either new job or new ini job
    NORMAL_JOB = 0
    # Job was created via a job upload
    UPLOADED_JOB = 1
    # Job was created via a gwosc job upload
    GWOSC_JOB = 2


BILBY_JOB_TYPE_CHOICES = (
    (BilbyJobType.NORMAL_JOB, "Normal Job"),
    (BilbyJobType.UPLOADED_JOB, "Uploaded Job"),
    (BilbyJobType.GWOSC_JOB, "GWOSC Job")
)
