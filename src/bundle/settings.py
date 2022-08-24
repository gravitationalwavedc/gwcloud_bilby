from scheduler.scheduler import EScheduler

# The directory where jobs are stored
job_directory = "/jobs/"

# Which scheduler to use
scheduler = EScheduler.SLURM

# Environment scheduler sources during runtime
scheduler_env = "/bundle/env.sh"

# The Condor accounting information
condor_accounting_group = "no.group"
condor_accounting_user = "no.one"

# If the database should use flufl for NFS locking
use_nfs_locking = False

try:
    from local import *
except Exception:
    pass
