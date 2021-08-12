# The directory where jobs are stored
job_directory = "/jobs/"

# Which scheduler to use
scheduler = "slurm"

# Environment scheduler sources during runtime
scheduler_env = "/bundle/env.sh"

try:
    from .local import *
except:
    pass
