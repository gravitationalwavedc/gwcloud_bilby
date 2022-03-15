import htcondor
from pathlib import Path
from .scheduler import Scheduler
from .status import JobStatus


class CondorScheduler(Scheduler):
    """
    Condor scheduler
    """

    def submit(self, script, working_directory):
        """
        Submits a script using the provided working directory

        :param script: The path to the submit script
        :param working_directory: The path to the working directory
        :return: An integer identifier for the submitted job
        """

        print(f"Trying to submit {script} from {working_directory}")

        # Create the submit object from the dag and submit it
        # Retry up to 5 times before failing, condor submit is quite flakey at times
        for attempt in range(1, 6):
            try:
                submit = htcondor.Submit().from_dag(script, {'force': True})
                result = htcondor.Schedd().submit(submit, count=1)

                # Record the command and the output
                print(f"Success: condor submit succeeded, got ClusterId={result.cluster()}")

                # Return the condor ClusterId
                return result.cluster()
            except Exception as e:
                # Record the error occurred
                print(f"Error: condor submit failed, trying again {attempt}/5")
                print(e)

        print("Condor submit failed 5 times in a row, assuming something is wrong.")
        return None

    def status(self, job_id, details):
        """
        Get the status of a job by scheduler id

        :param job_id: The scheduler job id to check the status of
        :param details: The internal job details object
        :return: A tuple with JobStatus, additional info as a string. None if no job status could be obtained
        """

        p = Path(details['working_directory']) / details['submit_directory']

        print(f"Trying to get status of job with working directory {p}...")

        log_file = list(p.glob('*.submit.nodes.log'))

        if len(log_file) != 1:
            print(f"The number of .submit.nodes.log files was not 1 as expected, it was {len(log_file)}")
            return None, None

        log_file = log_file[0]

        # Parse the log event log with condor and get a reverse chronological list of events
        jel = htcondor.JobEventLog(str(log_file))
        events = list(jel.events(stop_after=0))
        events.reverse()

        # Find the most recent submit event and parse the log notes to find which job stage the submit
        # is for
        submit_event = list(filter(lambda x: x.type == htcondor.JobEventType.SUBMIT, events))[0]
        notes = submit_event['LogNotes']
        stage = list(filter(lambda x: x.startswith("DAG Node:"), notes.splitlines()))

        # There should be exactly one stage found, which is the name of the job dag for the submitted job
        if len(stage) != 1:
            print("No DAG Node could be found for the most recent job submission")
            return None, None

        stage = stage[0]

        # Get the most recent event and determine the job state
        latest_event = events[0]

        if latest_event.type == htcondor.JobEventType.SUBMIT:
            # The only time a job can be queued is when the most recent job that was submitted was the
            # generation stage, otherwise SUBMIT indicates the job is running
            if stage.endswith('_generation_arg_0'):
                return JobStatus.QUEUED, "Job is queued"
            else:
                return JobStatus.RUNNING, "Job is running"

        if latest_event.type == htcondor.JobEventType.EXECUTE:
            # EXECUTE is self explanitory.
            return JobStatus.RUNNING, "Job is running"

        # Bilby jobs may be evicted, which is ok. Bilby jobs which are evicted will resubmit via signal
        # and continue. Held/released jobs are also part of the internal eviction/resubmit process
        if latest_event.type in [
            htcondor.JobEventType.JOB_EVICTED,
            htcondor.JobEventType.JOB_HELD,
            htcondor.JobEventType.JOB_RELEASED
        ]:
            return JobStatus.RUNNING, "Job is running"

        # If the job has been aborted, it's probably been cancelled - mark it as such
        if latest_event.type == htcondor.JobEventType.JOB_ABORTED:
            return JobStatus.CANCELLED, "Job has been aborted"

        # The only remaining event type we can handle is JOB_TERMINATED, otherwise condor has done something weird
        if latest_event.type != htcondor.JobEventType.JOB_TERMINATED:
            print(f"Unexpected job event {latest_event.type}! for working directory {details['working_directory']}")
            return None, None

        # Iterate over all submit events in order and find all stages that have been run
        submitted_stages = {}
        for event in filter(lambda x: x.type == htcondor.JobEventType.SUBMIT, events):
            notes = event['LogNotes']
            submitted_stages[event.cluster] = list(filter(lambda x: x.startswith("DAG Node:"), notes.splitlines()))[0]

        plot_started = any(filter(lambda x: x.endswith('_plot_arg_0'), submitted_stages.values()))

        # Remove any stages that have finished, and verify their return codes
        for event in filter(lambda x: x.type == htcondor.JobEventType.JOB_TERMINATED, events):
            # Jobs that terminate normally and have a return value of 0 completed successfully, otherwise
            # some error has occurred
            if (event["TerminatedNormally"]):
                if event['ReturnValue'] != 0:
                    return JobStatus.ERROR, f"Job terminated with return value {latest_event['ReturnValue']}"
            else:
                # ???
                return JobStatus.ERROR, "Job terminated abnormally"

            del submitted_stages[event.cluster]

        # If all submitted stages have finished, and the plotting stage has been submitted, then the job has finished
        if not len(submitted_stages) and plot_started:
            return JobStatus.COMPLETED, "All job stages finished successfully"

        # Job is not yet complete
        return JobStatus.RUNNING, "Job is running"

    def cancel(self, job_id, details):
        """
        Cancel a running job

        :param job_id: The id of the job to cancel
        :param details: The internal db record for the job
        :return: True if the job was cancelled otherwise False
        """
        raise Exception("Not implemented")
