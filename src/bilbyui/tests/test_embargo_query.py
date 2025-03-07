from django.contrib.auth import get_user_model
from django.test import override_settings

from graphql_relay.node.node import to_global_id
from bilbyui.models import BilbyJob
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from unittest import mock
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS

from humps import camelize

User = get_user_model()


class TestBilbyJobQueries(BilbyTestCase):
    def setUp(self):
        self.real_job_data = {
            "name": "RealTestName",
            "user_id": 1,
            "ini_string": create_test_ini_string(
                {"trigger-time": 1.0, "n-simulation": 0, "detectors": "['H1']"}
            ),
        }
        self.real_job = BilbyJob.objects.create(**self.real_job_data)
        self.real_job_data.update(
            {"id": to_global_id("BilbyJobNode", self.real_job.id)}
        )

        self.simulated_job_data = {
            "name": "SimulatedTestName",
            "user_id": 1,
            "ini_string": create_test_ini_string(
                {"trigger-time": 2.0, "n-simulation": 1, "detectors": "['H1']"}
            ),
        }
        self.simulated_job = BilbyJob.objects.create(**self.simulated_job_data)
        self.simulated_job_data.update(
            {"id": to_global_id("BilbyJobNode", self.simulated_job.id)}
        )

        self.embargoed_job_data = {
            "name": "EmbargoedTestName",
            "user_id": 1,
            "ini_string": create_test_ini_string(
                {"trigger-time": 2.0, "n-simulation": 0, "detectors": "['H1']"}
            ),
        }
        self.embargoed_job = BilbyJob.objects.create(**self.embargoed_job_data)
        self.embargoed_job_data.update(
            {"id": to_global_id("BilbyJobNode", self.embargoed_job.id)}
        )

        self.job_data = [
            self.real_job_data,
            self.simulated_job_data,
            self.embargoed_job_data,
        ]

        # Normally we don't have any User objects
        # But this test uses the presence or absense of User.objects[0] for various things
        self.user = User.objects.create(
            username="buffy", first_name="buffy", last_name="summers"
        )

    def job_request(self, job_data):
        field_str = "\n".join(list(camelize(job_data).keys()))
        return self.query(
            f"""
            query {{
                bilbyJob(id:"{job_data["id"]}"){{
                    {field_str}
                }}
            }}
            """
        )

    def jobs_request(self):
        field_str = "\n".join(list(camelize(self.real_job_data).keys()))
        return self.query(
            f"""
            query {{
                bilbyJobs {{
                    edges {{
                        node {{
                            {field_str}
                        }}
                    }}
                }}
            }}
            """
        )

    def request_lookup_users_mock(*args, **kwargs):
        user = User.objects.first()
        if user:
            return True, [{"id": user.id, "name": "buffy summers"}]
        return False, []

    @override_settings(EMBARGO_START_TIME=1.5)
    @mock.patch(
        "bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock
    )
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_embargoed_user_embargo_single_query(self, *args):
        """
        Checks that non-ligo and anonymous users will not receive jobs subject to embargo
        """
        for _ in range(2):
            for data in self.job_data[:2]:
                response = self.job_request(data)
                expected = {"bilbyJob": camelize(data)}
                self.assertDictEqual(
                    expected, response.data, "bilbyJob query returned unexpected data."
                )
            response = self.job_request(self.embargoed_job_data)
            expected = {"bilbyJob": None}
            self.assertDictEqual(
                expected, response.data, "bilbyJob query returned unexpected data."
            )
            self.authenticate()

    @override_settings(EMBARGO_START_TIME=1.5)
    @mock.patch(
        "bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock
    )
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_ligo_user_embargo_single_query(self, *args):
        """
        checks that ligo users will receive all jobs
        """
        self.authenticate(
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]
        )
        for data in self.job_data:
            response = self.job_request(data)
            expected = {"bilbyJob": camelize(data)}
            self.assertDictEqual(
                expected, response.data, "bilbyJob query returned unexpected data."
            )

    @override_settings(EMBARGO_START_TIME=1.5)
    @mock.patch(
        "bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock
    )
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_embargoed_user_embargo_query(self, *args):
        """
        checks that non-ligo users will not receive embargoed jobs
        anonymous users are not checked because they are expected to receive nothing from user bilbyJobs query
        """
        self.authenticate()
        response = self.jobs_request()
        expected = {
            "bilbyJobs": {
                "edges": [{"node": camelize(data)} for data in self.job_data[1::-1]]
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

    @override_settings(EMBARGO_START_TIME=1.5)
    @mock.patch(
        "bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock
    )
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_ligo_user_embargo_query(self, *args):
        """
        checks that ligo users will receive all jobs
        """
        self.authenticate(
            authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"]
        )
        response = self.jobs_request()
        expected = {
            "bilbyJobs": {
                "edges": [{"node": camelize(data)} for data in self.job_data[::-1]]
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )
