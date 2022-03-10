import contextlib
import os
from tempfile import NamedTemporaryFile

from bilby_pipe.parser import create_parser


def args_to_bilby_ini(args):
    """
    Generates an ini string from the provided args

    :params args: The args to add to the ini string
    :return: A string containing the ini file content
    """

    # Create a bilby argument parser
    parser = create_parser()

    # Bilby pipe requires a real file in order to parse the ini file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        parser.write_to_file(f.name, args, overwrite=True)

        # Make sure the data is flushed
        f.flush()

        # Read the ini file from the file
        ini_string = f.read()

    return ini_string


@contextlib.contextmanager
def cd(path):
    cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(cwd)
