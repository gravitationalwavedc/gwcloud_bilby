from abc import ABC, abstractmethod


class Scheduler(ABC):
    @abstractmethod
    def submit(self, script, working_directory):
        """
        Submits a script using the provided working directory

        :param script: The path to the submit script
        :param working_directory: The path to the working directory
        :return: An integer identifier for the submitted job
        """
        pass

    @abstractmethod
    def status(self, job_id):
        """
        Get the status of a job by scheduler id

        :param job_id: The scheduler job id to check the status of
        :return: A tuple with JobStatus, additional info as a string. None if no job status could be obtained
        """
        pass

    @abstractmethod
    def cancel(self, job_id):
        """
        Cancel a running job by scheduler id

        :param job_id: The scheduler id of the job to cancel
        :return: True if the job was cancelled otherwise False
        """
        pass
