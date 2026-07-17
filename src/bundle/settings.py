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

# Default working directory used when the job ID is not specified (e.g. for cluster file fetching)
default_working_directory = "/"

try:
    from local import *  # noqa: F401, F403
except Exception:
    pass
