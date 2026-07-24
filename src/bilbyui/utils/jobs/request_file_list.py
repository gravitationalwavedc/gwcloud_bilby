import contextlib
import logging
import os
from pathlib import Path

from django.conf import settings

from bilbyui.constants import BilbyJobType
from bilbyui.utils.jobs.submit_job import _make_job_controller_request
from bilbyui.utils.misc import check_request_leak

logger = logging.getLogger(__name__)


def request_file_list(job, path, recursive, user_id=None):
    """
    Requests the file list for a job

    :param job: The BilbyJob instance whose files are listed
    :param user_id: An optional user id to make the request as
    :param path: The relative path to the job to fetch the file list for
    :param recursive: If the file list should be recursive or not
    """
    # Check if the job is uploaded, and fetch the files off local storage
    if job.job_type == BilbyJobType.UPLOADED:
        job_dir = job.get_upload_directory()

        # Get the absolute path to the requested path
        dir_path = str(Path(job_dir, path).resolve())

        # Verify that:-
        # * this file really sits under the working directory
        # * the path exists
        # * the path is a directory
        dir_path_obj = Path(dir_path)
        if (
            not (dir_path == job_dir or dir_path.startswith(job_dir + os.sep))
            or not dir_path_obj.exists()
            or not dir_path_obj.is_dir()
        ):
            return False, "Files do not exist"

        # Get the list of files requested
        file_list = []
        if recursive:
            # This is a recursive search
            for root, dirnames, filenames in os.walk(dir_path):
                # Iterate over the directories
                for item in dirnames:
                    # Construct the real path to this directory
                    real_file_name = Path(root, item)
                    # Add the file entry
                    file_list.append(
                        {
                            # Remove the leading working directory
                            "path": str(real_file_name)[len(job_dir) :],
                            "isDir": True,
                            "fileSize": real_file_name.stat().st_size,
                        }
                    )

                for item in filenames:
                    # Construct the real path to this file
                    real_file_name = Path(root, item)
                    # Add the file entry
                    with contextlib.suppress(FileNotFoundError):
                        # Happens when trying to stat a symlink
                        file_list.append(
                            {
                                # Remove the leading working directory
                                "path": str(real_file_name)[len(job_dir) :],
                                "isDir": False,
                                "fileSize": real_file_name.stat().st_size,
                            }
                        )
        else:
            # Not a recursive search
            for item in dir_path_obj.iterdir():
                # Construct the real path to this file/directory
                real_file_name = item
                # Add the file entry
                file_list.append(
                    {
                        # Remove the leading working directory
                        "path": str(real_file_name)[len(job_dir) :],
                        "isDir": real_file_name.is_dir(),
                        "fileSize": real_file_name.stat().st_size,
                    }
                )

        return True, file_list

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        return False, "Job not submitted"

    data = {"jobId": job.job_controller_id, "recursive": recursive, "path": path}

    try:
        check_request_leak()
        result = _make_job_controller_request(
            "PATCH",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            user_id or job.user_id,
            data=data,
        )
        return True, result["files"]
    except Exception as e:
        logger.error(f"Error getting job file list: {e}", exc_info=True)
        return False, "Error getting job file list"
