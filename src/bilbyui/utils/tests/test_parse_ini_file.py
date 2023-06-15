from bilbyui.models import BilbyJob, IniKeyValue
from bilbyui.tests.test_utils import compare_ini_kvs, create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.parse_ini_file import parse_ini_file


class TestParseIniFile(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name="test job",
            description="test job",
            ini_string=create_test_ini_string({'detectors': "['H1']"})
        )

    def test_empty_ini(self):
        # A job with an empty ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        compare_ini_kvs(self, self.job, "detectors=['H1']")

    def test_invalid_keys(self):
        # A job with no ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        compare_ini_kvs(self, self.job,
                        """
                        detectors=['H1']
                        not-a-real-key=not-a-real-value
                        something-else=whatever"""
                        )

    def test_valid_keys(self):
        self.job.ini_string = """
detectors=['H1']
pn-phase-order=12345
n-parallel=5432
label=my-awesome-job"""
        self.job.save()

        # A job with no ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        compare_ini_kvs(self, self.job, self.job.ini_string)

        # Double check that the k/v's were correctly created
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="pn_phase_order", value="12345", processed=False).count(),
            1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="pn_phase_order", value="12345", processed=True).count(),
            1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="n_parallel", value="5432", processed=False).count(),
            1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="label", value="\"my-awesome-job\"", processed=False).count(),
            1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="label", value="\"my-awesome-job\"", processed=True).count(),
            1
        )
