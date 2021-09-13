# The directory where jobs are stored
from scheduler.scheduler import EScheduler

job_directory = "/jobs/"

# Which scheduler to use
scheduler = EScheduler.SLURM

# Environment scheduler sources during runtime
scheduler_env = "/bundle/env.sh"

# The Condor accounting information
condor_accounting_group = "no.group"
condor_accounting_user = "no.one"

try:
    from local import *
except Exception:
    pass
