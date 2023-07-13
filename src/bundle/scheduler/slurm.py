import subprocess

from .scheduler import Scheduler
from .status import JobStatus


class SlurmScheduler(Scheduler):
    """
    Slurm scheduler
    """

    SLURM_STATUS = {
        "BOOT_FAIL": "Job terminated due to launch failure, typically due to a hardware failure (e.g. unable to boot "
        "the node or block and the job can not be requeued).",
        "CANCELLED": "Job was explicitly cancelled by the user or system administrator. The job may or may not have "
        "been initiated.",
        "COMPLETED": "Job has terminated all processes on all nodes with an exit code of zero.",
        "DEADLINE": "Job terminated on deadline.",
        "FAILED": "Job terminated with non-zero exit code or other failure condition.",
        "NODE_FAIL": "Job terminated due to failure of one or more allocated nodes.",
        "OUT_OF_MEMORY": "Job experienced out of memory error.",
        "PENDING": "Job is awaiting resource allocation.",
        "PREEMPTED": "Job terminated due to preemption.",
        "RUNNING": "Job currently has an allocation.",
        "REQUEUED": "Job was requeued.",
        "RESIZING": "Job is about to change size.",
        "REVOKED": "Sibling was removed from cluster due to other cluster starting the job.",
        "SUSPENDED": "Job has an allocation, but execution has been suspended and CPUs have been released for "
        "other jobs.",
        "TIMEOUT": "Job terminated upon reaching its time limit.",
    }

    def submit(self, script, working_directory):
        """
        Submits a script using the provided working directory

        :param script: The path to the submit script
        :param working_directory: The path to the working directory
        :return: An integer identifier for the submitted job
        """

        # Construct the sbatch command
        command = "cd {} && sbatch {}".format(working_directory, script)

        # Execute the sbatch command
        stdout = None
        try:
            stdout = subprocess.check_output(command, shell=True)
        except Exception:
            # Record the command and the output
            print("Error: Command `{}` returned `{}`".format(command, stdout))
            return None

        # Record the command and the output
        print("Success: Command `{}` returned `{}`".format(command, stdout))

        # Get the slurm id from the output
        # todo: Handle errors
        try:
            return int(stdout.strip().split()[-1])
        except Exception:
            return None

    def status(self, job_id, details):
        """
        Get the status of a job by scheduler id

        :param job_id: The scheduler job id to check the status of
        :param details: The internal job details object
        :return: A tuple with JobStatus, additional info as a string. None if no job status could be obtained
        """
        print("Trying to get status of job {}...".format(job_id))

        # Construct the command
        command = "sacct -Pn -j {} -o jobid,state%50".format(job_id)

        # Execute the sacct command for this job
        stdout = subprocess.check_output(command, shell=True)

        # todo: Handle errors
        # Get the output
        print("Command `{}` returned `{}`".format(command, stdout))

        _status = None
        # Iterate over the lines
        for line in stdout.splitlines():
            # Split the line by |
            bits = line.split(b"|")
            # Check that the first bit of the line can be converted to an int (Catches line's containing .batch)
            try:
                if int(bits[0]) == int(job_id):
                    _status = bits[1].decode("utf-8")
                    break
            except Exception:
                continue

        print("Got job status {} for job {}".format(_status, job_id))

        # Check that we got a status for this job
        if not _status:
            return None, None

        # Check for general failure
        if _status in ["BOOT_FAIL", "CANCELLED", "DEADLINE", "FAILED", "NODE_FAIL", "PREEMPTED", "REVOKED"]:
            return JobStatus.ERROR, SlurmScheduler.SLURM_STATUS[_status.split(" ")[0]]

        # Check for cancelled job
        if _status.startswith("CANCELLED"):
            return JobStatus.CANCELLED, SlurmScheduler.SLURM_STATUS[_status.split(" ")[0]]

        # Check for out of memory
        if _status == "OUT_OF_MEMORY":
            return JobStatus.OUT_OF_MEMORY, SlurmScheduler.SLURM_STATUS[_status.split(" ")[0]]

        # Check for wall time exceeded
        if _status == "TIMEOUT":
            return JobStatus.WALL_TIME_EXCEEDED, SlurmScheduler.SLURM_STATUS[_status.split(" ")[0]]

        # Check for completed successfully
        if _status == "COMPLETED":
            return JobStatus.COMPLETED, SlurmScheduler.SLURM_STATUS[_status.split(" ")[0]]

        # Check for job currently queued
        if _status in ["PENDING", "REQUEUED", "RESIZING"]:
            return JobStatus.QUEUED, SlurmScheduler.SLURM_STATUS[_status.split(" ")[0]]

        # Check for job running
        if _status in ["RUNNING", "SUSPENDED"]:
            return JobStatus.RUNNING, SlurmScheduler.SLURM_STATUS[_status.split(" ")[0]]

        print("Got unknown Slurm job state {} for job {}".format(_status, job_id))
        return None, None

    def cancel(self, job_id, details):
        """
        Cancel a running job

        :param job_id: The id of the job to cancel
        :param details: The internal job details object
        :return: True if the job was cancelled otherwise False
        """
        print("Trying to terminate job {}...".format(job_id))

        # Construct the command
        command = "scancel {}".format(job_id)

        # Cancel the job
        stdout = subprocess.check_output(command, shell=True)

        # todo: Handle errors
        # Get the output
        print("Command `{}` returned `{}`".format(command, stdout))
