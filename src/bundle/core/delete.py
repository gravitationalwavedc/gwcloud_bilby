import shutil

from core.misc import working_directory


def delete(details, job_data):
    # Make sure that the job is canceled


    # Get the working directory
    wk_dir = working_directory(details, job_data)

    # Make sure that the directory is deleted if it exists
    try:
        shutil.rmtree(working_directory)
    except:
        pass
