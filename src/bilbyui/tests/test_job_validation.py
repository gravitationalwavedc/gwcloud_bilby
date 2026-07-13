from bilbyui.models import BilbyJob
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.job_validation import validate_job_name


class TestValidateJobName(BilbyTestCase):
    def test_rejects_too_short(self):
        with self.assertRaises(Exception) as ctx:
            validate_job_name("abc")
        self.assertEqual(str(ctx.exception), "Job name must be at least 5 characters long.")

    def test_rejects_too_long(self):
        max_len = BilbyJob._meta.get_field("name").max_length
        with self.assertRaises(Exception) as ctx:
            validate_job_name("a" * (max_len + 1))
        self.assertEqual(str(ctx.exception), f"Job name must be less than {max_len} characters long.")

    def test_rejects_invalid_characters(self):
        with self.assertRaises(Exception) as ctx:
            validate_job_name("valid name")
        self.assertEqual(str(ctx.exception), "Job name must not contain any spaces or special characters.")

    def test_accepts_valid_name(self):
        validate_job_name("my_valid-job1")
