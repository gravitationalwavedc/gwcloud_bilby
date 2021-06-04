import json

from bilbyui.models import IniKeyValue
from bilbyui.utils.parse_ini_file import bilby_ini_to_args


def parse_test_ini(ini):
    # Get the args from the ini
    args = bilby_ini_to_args(ini.encode('utf-8'))

    # Iterate over the parsed ini configuration and generate a result dict
    result = {}
    for idx, key in enumerate(vars(args)):
        result[key] = dict(value=getattr(args, key), index=idx)

    return result


def compare_ini_kvs(test, job, ini):
    args = parse_test_ini(ini)
    for k, v in args.items():
        test.assertTrue(
            IniKeyValue.objects.filter(
                job=job,
                key=k,
                value=json.dumps(v['value']),
                index=v['index']
            ).exists()
        )
