import contextlib
import logging
import os
from pathlib import Path

import requests
from django.conf import settings

from bilbyui.constants import BilbyJobType
from bilbyui.utils.jobs.submit_job import _make_job_controller_request
from bilbyui.utils.misc import check_request_leak

logger = logging.getLogger(__name__)


def _make_file_entry(real_file_name, is_dir, job_dir):
    """
    Constructs a file entry dict for the given path, or None if the path
    cannot be stat'ed (e.g. a broken symlink).
    """
    with contextlib.suppress(FileNotFoundError):
        # Happens when trying to stat a symlink
        return {
            # Report the path relative to the working directory
            "path": f"/{real_file_name.relative_to(job_dir)}",
            "isDir": is_dir,
            "fileSize": real_file_name.stat().st_size,
        }
    return None


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
        job_dir = str(Path(job.get_upload_directory()).resolve())

        # Get the absolute path to the requested path
        dir_path = str(Path(job_dir, path).resolve())

        # Verify that:-
        # * this file really sits under the working directory
        # * the path exists
        # * the path is a directory
        dir_path_obj = Path(dir_path)
        if not dir_path_obj.is_relative_to(job_dir) or not dir_path_obj.exists() or not dir_path_obj.is_dir():
            return False, "Files do not exist"

        # Get the list of files requested
        file_list = []
        if recursive:
            # This is a recursive search
            for root, dirnames, filenames in os.walk(dir_path):
                # Iterate over the directories
                for item in dirnames:
                    entry = _make_file_entry(Path(root, item), True, job_dir)
                    if entry is not None:
                        file_list.append(entry)

                for item in filenames:
                    entry = _make_file_entry(Path(root, item), False, job_dir)
                    if entry is not None:
                        file_list.append(entry)
        else:
            # Not a recursive search
            for item in dir_path_obj.iterdir():
                entry = _make_file_entry(item, item.is_dir(), job_dir)
                if entry is not None:
                    file_list.append(entry)

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
        if not isinstance(result, dict) or not isinstance(result.get("files"), list):
            logger.error("Error getting job file list: malformed response from job controller")
            return False, "Error getting job file list"
        return True, result["files"]
    except requests.RequestException as e:
        logger.error("Error getting job file list: %s", e, exc_info=True)
        return False, "Error getting job file list"
