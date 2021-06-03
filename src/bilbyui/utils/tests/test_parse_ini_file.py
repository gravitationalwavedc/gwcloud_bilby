import json
from tempfile import NamedTemporaryFile

from bilby_pipe.parser import create_parser
from bilby_pipe.utils import parse_args
from django.test import TestCase

from bilbyui.models import BilbyJob, IniKeyValue
from bilbyui.utils.parse_ini_file import parse_ini_file


def parse_test_ini(ini):
    parser = create_parser()

    # Bilby pipe requires a real file in order to parse the ini file
    with NamedTemporaryFile() as f:
        # Write the temporary ini file
        f.write(ini.encode('utf-8'))

        # Make sure the data is flushed to the ini file
        f.flush()

        # Read the data from the ini file
        args, unknown_args = parse_args([f.name], parser)

    # ini and verbose are not kept in the ini file, so remove them
    delattr(args, 'ini')
    delattr(args, 'verbose')

    # Iterate over the parsed ini configuration and generate a result dict
    result = {}
    for idx, key in enumerate(vars(args)):
        result[key] = dict(value=getattr(args, key), index=idx)

    return result


class TestParseIniFile(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name="test job",
            description="test job"
        )

    def compare_ini_kvs(self, ini):
        args = parse_test_ini(ini)
        for k, v in args.items():
            self.assertTrue(
                IniKeyValue.objects.filter(
                    job=self.job,
                    key=k,
                    value=json.dumps(v['value']),
                    index=v['index']
                ).exists()
            )

    def test_empty_ini(self):
        # A job with no ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        self.compare_ini_kvs('')

    def test_invalid_keys(self):
        # A job with no ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        self.compare_ini_kvs(
            """
            not-a-real-key=not-a-real-value
            something-else=whatever"""
        )

    def test_valid_keys(self):
        self.job.ini_string = """
pn-phase-order=12345
n-parallel=5432
label=my-awesome-job"""
        self.job.save()

        # A job with no ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        self.compare_ini_kvs(self.job.ini_string)

        # Double check that the k/v's were correctly created
        self.assertEqual(IniKeyValue.objects.filter(job=self.job, key="pn_phase_order", value="12345").count(), 1)
        self.assertEqual(IniKeyValue.objects.filter(job=self.job, key="n_parallel", value="5432").count(), 1)
        self.assertEqual(IniKeyValue.objects.filter(job=self.job, key="label", value="\"my-awesome-job\"").count(), 1)

        self.job.ini_string = None
        self.job.save()
