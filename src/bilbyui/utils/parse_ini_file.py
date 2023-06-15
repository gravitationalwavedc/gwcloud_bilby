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

    # Avoiding circular imports
    from bilbyui.models import IniKeyValue
    from bilbyui.views import bilby_ini_args_to_data_input

    # Clean up any existing k/v for this job
    (ini_key_value_klass or IniKeyValue).objects.filter(job=job).delete()

    # Get the args from the ini
    args = bilby_ini_string_to_args((job.ini_string or '').encode('utf-8'))

    if args.detectors is None:
        raise Exception("Detectors must be set")

    # Iterate over the parsed ini configuration and store the key/value pairs in the database
    items = []
    for idx, key in enumerate(vars(args)):
        val = getattr(args, key)

        items.append(
            (ini_key_value_klass or IniKeyValue)(
                job=job,
                key=key,
                value=json.dumps(val),
                index=idx,
                processed=False
            )
        )

    # Parse the args through DataGenerationInput to postprocess any values
    args.outdir = './'

    try:
        processed_args = bilby_ini_args_to_data_input(args)

        for idx, key in enumerate(vars(processed_args)):
            while key.startswith('_'):
                key = key[1:]

            try:
                val = getattr(processed_args, key)

                items.append(
                    (ini_key_value_klass or IniKeyValue)(
                        job=job,
                        key=key,
                        value=json.dumps(val),
                        index=idx,
                        processed=True
                    )
                )
            except Exception:
                pass

    except Exception as e:
        print(f"Bilby job error with job id {job.id}: {str(e)}")

    (ini_key_value_klass or IniKeyValue).objects.bulk_create(items)
