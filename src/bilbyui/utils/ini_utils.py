from tempfile import NamedTemporaryFile

from bilby_pipe.parser import create_parser
from bilby_pipe.utils import parse_args


def bilby_ini_string_to_args(ini):
    """
    Parses an ini string in to an argument Namespace

    :params ini: The ini string to parse
    :return: An ArgParser Namespace of the parsed arguments from the ini
    """

    # Create an bilby argument parser
    parser = create_parser()

    # Bilby pipe requires a real file in order to parse the ini file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        f.write(ini)

        # Make sure the data is written to the temporary file
        f.flush()

        # Read the data from the ini file
        args, unknown_args = parse_args([f.name], parser)

    # ini and verbose are not kept in the ini file, so remove them
    delattr(args, 'ini')
    delattr(args, 'verbose')

    return args


def bilby_args_to_ini_string(args):
    # Create an argument parser
    parser = create_parser()

    # Use a tempfile to write the args as an ini file, then read the ini content back from the ini file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        parser.write_to_file(f.name, args, overwrite=True)

        # Make sure the data is flushed
        f.flush()

        # Read the ini content
        return f.read().decode('utf-8')
