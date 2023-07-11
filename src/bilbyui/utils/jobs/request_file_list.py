import datetime
import json
import logging
import os

import jwt
import requests
from django.conf import settings

from bilbyui.constants import BilbyJobType
from bilbyui.utils.misc import check_request_leak


def request_file_list(job, path, recursive, user_id=None):
    """
    Requests the file list for a job

    :param job: The BilbyJob instance to get the status of
    :param user_id: On optional user id to make the request as
    :param path: The relative path to the job to fetch the file list for
    :param recursive: If the file list should be recursive or not
    """
    # Check if the job is uploaded, and fetch the files off local storage
    if job.job_type == BilbyJobType.UPLOADED:
        job_dir = job.get_upload_directory()

        # Get the absolute path to the requested path
        dir_path = os.path.abspath(os.path.join(job_dir, path))

        # Verify that:-
        # * this file really sits under the working directory
        # * the path exists
        # * the path is a directory
        if not dir_path.startswith(job_dir) or not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return False, "Files do not exist"

        # Get the list of files requested
        file_list = []
        if recursive:
            # This is a recursive searh
            for root, dirnames, filenames in os.walk(dir_path):
                # Iterate over the directories
                for item in dirnames:
                    # Construct the real path to this directory
                    real_file_name = os.path.join(root, item)
                    # Add the file entry
                    file_list.append(
                        {
                            # Remove the leading working directory
                            "path": real_file_name[len(job_dir):],
                            "isDir": True,
                            "fileSize": os.path.getsize(real_file_name),
                        }
                    )

                for item in filenames:
                    # Construct the real path to this file
                    real_file_name = os.path.join(root, item)
                    # Add the file entry
                    try:
                        file_list.append(
                            {
                                # Remove the leading working directory
                                "path": real_file_name[len(job_dir):],
                                "isDir": False,
                                "fileSize": os.path.getsize(real_file_name),
                            }
                        )
                    except FileNotFoundError:
                        # Happens when trying to stat a symlink
                        pass
        else:
            # Not a recursive search
            for item in os.listdir(dir_path):
                # Construct the real path to this file/directory
                real_file_name = os.path.join(dir_path, item)
                # Add the file entry
                file_list.append(
                    {
                        # Remove the leading slash
                        "path": real_file_name[len(job_dir):],
                        "isDir": os.path.isdir(real_file_name),
                        "fileSize": os.path.getsize(real_file_name),
                    }
                )

        return True, file_list

    # Make sure that the job was actually submitted (Might be in a draft state?)
    if not job.job_controller_id:
        return False, "Job not submitted"

    # Create the jwt token
    jwt_enc = jwt.encode(
        {"userId": user_id or job.user_id, "exp": datetime.datetime.now() + datetime.timedelta(days=30)},
        settings.JOB_CONTROLLER_JWT_SECRET,
        algorithm="HS256",
    )

    # Build the data object
    data = {"jobId": job.job_controller_id, "recursive": recursive, "path": path}

    try:
        # Initiate the request to the job controller
        check_request_leak()
        result = requests.request(
            "PATCH",
            f"{settings.GWCLOUD_JOB_CONTROLLER_API_URL}/file/",
            data=json.dumps(data),
            headers={"Authorization": jwt_enc},
        )

        # Check that the request was successful
        if result.status_code != 200:
            # todo: Spruce the exception handling up a bit
            # Oops
            msg = (
                f"Error getting job file list, got error code: "
                f"{result.status_code}\n\n{result.headers}\n\n{result.content}"
            )
            logging.error(msg)
            raise Exception(msg)

        # Parse the response from the job controller
        result = json.loads(result.content)

        return True, result["files"]
    except Exception:
        return False, "Error getting job file list"
