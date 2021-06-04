import json
from tempfile import NamedTemporaryFile

from bilby_pipe.parser import create_parser
from bilby_pipe.utils import parse_args


def bilby_ini_to_args(ini):
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


def parse_ini_file(job, ini_key_value_klass=None):
    """
    Parses the ini file from a job and generates a full set of ini key/value model instances

    :param job: The BilbyJob instance containing the ini_string content to parse
    :param ini_key_value_klass: Because this function can be called from a migration, we need to allow overriding
    the model to work with migration app models (See 0020_parse_ini_kv.py)
    :return: Nothing
    """

    from bilbyui.models import IniKeyValue

    # Clean up any existing k/v for this job
    (ini_key_value_klass or IniKeyValue).objects.filter(job=job).delete()

    # Get the args from the ini
    args = bilby_ini_to_args((job.ini_string or '').encode('utf-8'))

    # Iterate over the parsed ini configuration and store the key/value pairs in the database
    for idx, key in enumerate(vars(args)):
        val = getattr(args, key)
        (ini_key_value_klass or IniKeyValue).objects.create(job=job, key=key, value=json.dumps(val), index=idx)
