import logging
import subprocess
from typing import ClassVar

from .scheduler import Scheduler
from .status import JobStatus

logger = logging.getLogger(__name__)


class SlurmScheduler(Scheduler):
    """
    Slurm scheduler
    """

    SLURM_STATUS: ClassVar[dict[str, str]] = {
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
        command = f"cd {working_directory} && sbatch {script}"

        # Execute the sbatch command
        stdout = None
        try:
            stdout = subprocess.check_output(command, shell=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Record the command and the output
            logger.exception("Error: Command `%s` returned `%s`", command, stdout)
            return None

        # Record the command and the output
        logger.info("Success: Command `%s` returned `%s`", command, stdout)

        # Get the slurm id from the output
        # todo: Handle errors
        try:
            return int(stdout.strip().split()[-1])
        except (ValueError, IndexError):
            return None

    def status(self, job_id, _details):
        """
        Get the status of a job by scheduler id

        :param job_id: The scheduler job id to check the status of
        :param details: The internal job details object
        :return: A tuple with JobStatus, additional info as a string. None if no job status could be obtained
        """
        logger.debug("Trying to get status of job %s...", job_id)

        # Construct the command
        command = f"sacct -Pn -j {job_id} -o jobid,state%50"

        # Execute the sacct command for this job
        try:
            stdout = subprocess.check_output(command, shell=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            logger.warning(
                "Failed to get status for job %s: command `%s` failed", job_id, command
            )
            return None, None

        # Get the output
        logger.debug("Command `%s` returned `%s`", command, stdout)

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
            except (TypeError, ValueError, IndexError, UnicodeDecodeError):
                continue

        logger.debug("Got job status %s for job %s", _status, job_id)

        # Check that we got a status for this job
        if not _status:
            return None, None

        base_status = _status.split(" ")[0]

        # Fall back to the raw state string if it is not a known SLURM_STATUS key (e.g. transitional "CANCELLED+")
        status_info = self.SLURM_STATUS.get(base_status, base_status)

        # Check for general failure
        if base_status in [
            "BOOT_FAIL",
            "DEADLINE",
            "FAILED",
            "NODE_FAIL",
            "PREEMPTED",
            "REVOKED",
        ]:
            return JobStatus.ERROR, self.SLURM_STATUS[base_status]

        # Check for cancelled job
        if base_status.startswith("CANCELLED"):
            return JobStatus.CANCELLED, status_info

        # Check for out of memory
        if base_status == "OUT_OF_MEMORY":
            return JobStatus.OUT_OF_MEMORY, status_info

        # Check for wall time exceeded
        if base_status == "TIMEOUT":
            return JobStatus.WALL_TIME_EXCEEDED, status_info

        # Check for completed successfully
        if base_status == "COMPLETED":
            return JobStatus.COMPLETED, status_info

        # Check for job currently queued
        if base_status in ["PENDING", "REQUEUED", "RESIZING"]:
            return JobStatus.QUEUED, status_info

        # Check for job running
        if base_status in ["RUNNING", "SUSPENDED"]:
            return JobStatus.RUNNING, status_info

        logger.warning("Got unknown Slurm job state %s for job %s", _status, job_id)
        return None, None

    def cancel(self, job_id, _details):
        """
        Cancel a running job

        :param job_id: The id of the job to cancel
        :param details: The internal job details object
        :return: True if the job was cancelled otherwise False
        """
        logger.info("Trying to terminate job %s...", job_id)

        # Construct the command
        command = f"scancel {job_id}"

        # Cancel the job
        stdout = None
        try:
            stdout = subprocess.check_output(command, shell=True, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Record the command and the output
            logger.exception("Error: Command `%s` returned `%s`", command, stdout)
            return False

        # Get the output
        logger.info("Command `%s` returned `%s`", command, stdout)
        return True
