import json

from bilbyui.utils.ini_utils import bilby_ini_string_to_args


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
    args = bilby_ini_string_to_args((job.ini_string or '').encode('utf-8'))

    # Iterate over the parsed ini configuration and store the key/value pairs in the database
    for idx, key in enumerate(vars(args)):
        val = getattr(args, key)
        (ini_key_value_klass or IniKeyValue).objects.create(job=job, key=key, value=json.dumps(val), index=idx)
