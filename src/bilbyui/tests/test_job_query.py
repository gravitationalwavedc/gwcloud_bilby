from django.contrib.auth import get_user_model

from graphql_relay.node.node import to_global_id
from bilbyui.models import BilbyJob, Label, EventID
from bilbyui.tests.test_utils import silence_errors, create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from unittest import mock

from humps import camelize
from datetime import datetime
from adacs_sso_plugin.constants import AUTHENTICATION_METHODS

User = get_user_model()


class TestBilbyJobQueries(BilbyTestCase):
    def setUp(self):
        self.job_data = {
            "name": "TestName",
            "user_id": 1,
            "description": "Test description",
            "private": False,
            "ini_string": "detectors=['H1']",
            "job_controller_id": 1,
            "is_ligo_job": False,
            "job_type": 0,
            "cluster": "TestCluster",
        }

        # Normally we don't have any User objects
        # But this test uses the presence or absense of User.objects[0] for various things
        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.authenticate()
        self.label = Label.objects.create(name="Test", description="Test description")
        self.event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=12345678.1234,
        )
        self.job = BilbyJob.objects.create(**self.job_data)
        self.job.labels.set([self.label])
        self.job.event_id = self.event_id
        self.job.save()
        self.global_id = to_global_id("BilbyJobNode", self.job.id)

        self.job_data.update({"id": "QmlsYnlKb2JOb2RlOjE="})

    def job_request(self, *fields):
        field_str = "\n".join(fields)
        return self.query(f"""
            query {{
                bilbyJob(id:"{self.global_id}"){{
                    {field_str}
                }}
            }}
            """)

    def request_lookup_users_mock(*args, **kwargs):
        user = User.objects.first()
        if user:
            return True, [{"id": user.id, "name": "buffy summers"}]
        return False, []

    def derive_job_status_mock(*args, **kwargs):
        return 1, "Test Status", datetime.fromtimestamp(0)

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_query(self, *args):
        """
        bilbyJob node query should allow querying of model fields"
        """

        response = self.job_request(*list(camelize(self.job_data).keys()))
        expected = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_user_query(self, *args):
        """
        bilbyJob node query should allow querying of user field"
        """
        response = self.job_request("user")
        expected = {"bilbyJob": {"user": "buffy summers"}}
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

        # If it returns no user
        User.objects.first().delete()
        response = self.job_request("user")
        expected = {"bilbyJob": {"user": "Unknown User"}}
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch(
        "bilbyui.schema.request_job_filter",
        return_value=(None, [{"id": 1, "history": None}]),
    )
    @mock.patch("bilbyui.schema.derive_job_status", side_effect=derive_job_status_mock)
    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    def test_bilby_job_status_query(self, *args):
        """
        bilbyJob node query should allow querying of job status field"
        """
        response = self.job_request("jobStatus {name \n number \n date}")
        expected = {
            "bilbyJob": {
                "jobStatus": {
                    "name": "Test Status",
                    "number": 1,
                    "date": datetime.fromtimestamp(0).strftime("%Y-%m-%d %H:%M:%S UTC"),
                }
            }
        }
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_last_updated_query(self, *args):
        """
        bilbyJob node query should allow querying of last updated field"
        """
        response = self.job_request("lastUpdated")
        expected = {"bilbyJob": {"lastUpdated": self.job.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")}}
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_labels_query(self, *args):
        """
        bilbyJob node query should allow querying of labels field"
        """
        response = self.job_request("labels {name \n description}")
        expected = {"bilbyJob": {"labels": [{"name": self.label.name, "description": self.label.description}]}}
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_event_id_query(self, *args):
        """
        bilbyJob node query should allow querying of labels field"
        """
        response = self.job_request("eventId {eventId \n triggerId \n nickname \n isLigoEvent \n gpsTime}")
        expected = {
            "bilbyJob": {
                "eventId": {
                    "eventId": self.event_id.event_id,
                    "triggerId": self.event_id.trigger_id,
                    "nickname": self.event_id.nickname,
                    "isLigoEvent": self.event_id.is_ligo_event,
                    "gpsTime": self.event_id.gps_time,
                }
            }
        }
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_supporting_files_dont_exist(self, *args):
        self.job_data["name"] = "another test job"
        self.job_data["ini_string"] = open("bilbyui/tests/regression_data/psd_dict_ini.ini").read()
        del self.job_data["id"]
        self.job = BilbyJob.objects.create(**self.job_data)

        global_id = to_global_id("BilbyJobNode", self.job.id)
        query = f"""
            query {{
                bilbyJob(id:"{global_id}"){{
                    id
                    name
                    userId
                    description
                    jobControllerId
                    private
                    lastUpdated
                    params {{
                        details {{
                            name
                            description
                            private
                        }}
                    }}
                }}
            }}
        """

        response = self.query(query)

        self.assertEqual(response.errors, None)

        expected = {
            "bilbyJob": {
                "id": "QmlsYnlKb2JOb2RlOjI=",
                "name": "another test job",
                "userId": 1,
                "description": "Test description",
                "jobControllerId": 1,
                "private": False,
                "lastUpdated": self.job.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "params": {
                    "details": {
                        "name": "another test job",
                        "description": "Test description",
                        "private": False,
                    }
                },
            }
        }
        self.assertDictEqual(expected, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_query_anonymous_user(self, *args):
        """
        bilbyJob node query should return a single job as expected for an anonymous user"
        """
        request_data = list(camelize(self.job_data).keys())
        expected_one = {"bilbyJob": camelize(self.job_data)}
        expected_none = {"bilbyJob": None}

        # Clear any logged in user
        self.deauthenticate()

        # Anonymous user can only see public jobs
        response = self.job_request(*request_data)
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        self.job.private = True
        self.job.save()

        response = self.job_request(*request_data)
        self.assertDictEqual(expected_none, response.data, "bilbyJob query returned unexpected data.")

        # Anonymous user can't see ligo jobs
        self.job.private = False
        self.job.is_ligo_job = True
        self.job.save()

        response = self.job_request(*request_data)
        self.assertDictEqual(expected_none, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_query_non_ligo_user(self, *args):
        """
        bilbyJob node query should return a single job as expected for a user who is not a ligo user"
        """
        self.authenticate()

        request_data = list(camelize(self.job_data).keys())
        expected_none = {"bilbyJob": None}

        # Non ligo users should be able to see their own private jobs
        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        self.job_data["private"] = True
        self.job.private = True
        self.job.save()

        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        # Shouldn't be able to see jobs that we don't own that are private
        self.job_data["private"] = False
        self.job_data["user_id"] = self.user.id + 1
        self.job.private = False
        self.job.user_id = self.user.id + 1
        self.job.save()

        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        self.job_data["private"] = True
        self.job_data["user_id"] = self.user.id + 1
        self.job.private = True
        self.job.user_id = self.user.id + 1
        self.job.save()

        response = self.job_request(*request_data)
        self.assertDictEqual(expected_none, response.data, "bilbyJob query returned unexpected data.")

        # Non ligo users should not be able to see ligo jobs
        self.job.private = False
        self.job.is_ligo_job = True
        self.job.user_id = self.user.id
        self.job.save()

        response = self.job_request(*request_data)
        self.assertDictEqual(expected_none, response.data, "bilbyJob query returned unexpected data.")

    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_job_query_ligo_user(self, *args):
        """
        bilbyJob node query should return a single job as expected for a user who is a ligo user"
        """
        self.authenticate(authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])

        request_data = list(camelize(self.job_data).keys())
        expected_none = {"bilbyJob": None}

        # Ligo users should be able to see their own private jobs
        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        self.job_data["private"] = True
        self.job.private = True
        self.job.save()

        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        # Shouldn't be able to see jobs that we don't own that are private
        self.job_data["private"] = False
        self.job_data["user_id"] = self.user.id + 1
        self.job.private = False
        self.job.user_id = self.user.id + 1
        self.job.save()

        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        self.job_data["private"] = True
        self.job_data["user_id"] = self.user.id + 1
        self.job.private = True
        self.job.user_id = self.user.id + 1
        self.job.save()

        response = self.job_request(*request_data)
        self.assertDictEqual(expected_none, response.data, "bilbyJob query returned unexpected data.")

        # ligo users should be able to see public ligo jobs from other users
        self.job_data["private"] = False
        self.job_data["is_ligo_job"] = True
        self.job.private = False
        self.job.is_ligo_job = True
        self.job.save()

        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

        # ligo users should be able to see private ligo jobs from themselves
        self.job_data["private"] = True
        self.job_data["user_id"] = self.user.id
        self.job.private = True
        self.job.user_id = self.user.id
        self.job.save()

        response = self.job_request(*request_data)
        expected_one = {"bilbyJob": camelize(self.job_data)}
        self.assertDictEqual(expected_one, response.data, "bilbyJob query returned unexpected data.")

    @silence_errors
    @mock.patch("bilbyui.schema.request_lookup_users", side_effect=request_lookup_users_mock)
    @mock.patch(
        "bilbyui.schema.request_job_filter",
        side_effect=lambda *args, **kwargs: (True, []),
    )
    def test_bilby_jobs_query(self, request_job_filter_mock, *args):
        """
        bilbyJobs query should return a list of personal jobs for an authenticated user.
        """
        job = BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test1",
            job_controller_id=2,
            is_ligo_job=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="Test2",
            job_controller_id=1,
            description="A test job",
            is_ligo_job=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        BilbyJob.objects.create(
            user_id=self.user.id,
            name="aaafirst",
            job_controller_id=None,
            description="A test job",
            is_ligo_job=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

        # This job shouldn't appear in the list because it belongs to another user.
        BilbyJob.objects.create(
            user_id=4,
            name="Test3",
            job_controller_id=4,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

        query = """
                query {
                    bilbyJobs {
                        edges {
                            node {
                                userId
                                name
                                description
                            }
                        }
                    }
                }
            """

        # Check fails without authenticated user
        self.deauthenticate()
        response = self.query(query)
        self.assertResponseHasErrors(response, "Query returned no errors even though user was not authenticated")

        # Try again with authenticated user
        self.authenticate()
        response = self.query(query)
        expected = {
            "bilbyJobs": {
                "edges": [
                    {
                        "node": {
                            "userId": 1,
                            "name": "aaafirst",
                            "description": "A test job",
                        }
                    },
                    {
                        "node": {
                            "userId": 1,
                            "name": "Test2",
                            "description": "A test job",
                        }
                    },
                    {"node": {"userId": 1, "name": "Test1", "description": None}},
                    {
                        "node": {
                            "userId": 1,
                            "name": "TestName",
                            "description": "Test description",
                        }
                    },
                ]
            }
        }
        self.assertDictEqual(response.data, expected, "bilbyJobs query returned unexpected data.")

        # Update the first test job and check that the order changes correctly
        job.description = "Test job description"
        job.save()

        response = self.query(query)
        expected = {
            "bilbyJobs": {
                "edges": [
                    {
                        "node": {
                            "userId": 1,
                            "name": "Test1",
                            "description": "Test job description",
                        }
                    },
                    {
                        "node": {
                            "userId": 1,
                            "name": "aaafirst",
                            "description": "A test job",
                        }
                    },
                    {
                        "node": {
                            "userId": 1,
                            "name": "Test2",
                            "description": "A test job",
                        }
                    },
                    {
                        "node": {
                            "userId": 1,
                            "name": "TestName",
                            "description": "Test description",
                        }
                    },
                ]
            }
        }
        self.assertDictEqual(response.data, expected, "bilbyJobs query returned unexpected data.")

        # Check that all ids provided to request_job_filter_mock were integers
        self.assertTrue(
            all(
                map(
                    lambda x: isinstance(x, int),
                    request_job_filter_mock.call_args[1]["ids"],
                )
            )
        )
