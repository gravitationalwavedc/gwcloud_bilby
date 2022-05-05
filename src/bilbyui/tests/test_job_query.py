from django.contrib.auth import get_user_model

from graphql_relay.node.node import to_global_id
from bilbyui.models import BilbyJob, Label, EventID
from bilbyui.tests.testcases import BilbyTestCase
from unittest import mock

from humps import camelize
from datetime import datetime

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
            "is_uploaded_job": False,
            "cluster": "TestCluster"
        }

        self.user = User.objects.create(username="buffy", first_name="buffy", last_name="summers")
        self.client.authenticate(self.user)
        self.label = Label.objects.create(name="Test", description="Test description")
        self.event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
        )
        self.job = BilbyJob.objects.create(**self.job_data)
        self.job.labels.set([self.label])
        self.job.event_id = self.event_id
        self.job.save()
        self.global_id = to_global_id("BilbyJobNode", self.job.id)

        self.job_data.update({"id": "QmlsYnlKb2JOb2RlOjE="})

    def job_request(self, *fields):
        field_str = "\n".join(fields)
        return self.client.execute(
            f"""
            query {{
                bilbyJob(id:"{self.global_id}"){{
                    {field_str}
                }}
            }}
            """
        )

    def request_lookup_users_mock(*args, **kwargs):
        user = User.objects.first()
        if user:
            return True, [{
                'userId': user.id,
                'username': user.username,
                'firstName': user.first_name,
                'lastName': user.last_name
            }]
        return False, []

    def derive_job_status_mock(*args, **kwargs):
        return 1, "Test Status", datetime.fromtimestamp(0)

    def test_bilby_job_query(self):
        """
        bilbyJob node query should allow querying of model fields"
        """

        response = self.job_request(
            *list(camelize(self.job_data).keys())
        )
        expected = {
            "bilbyJob": camelize(self.job_data)
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

    @mock.patch('bilbyui.schema.request_lookup_users', side_effect=request_lookup_users_mock)
    def test_bilby_job_user_query(self, request_lookup_users_mock):
        """
        bilbyJob node query should allow querying of user field"
        """
        response = self.job_request("user")
        expected = {
            "bilbyJob": {
                "user": "buffy summers"
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

        # If it returns no user
        User.objects.first().delete()
        response = self.job_request("user")
        expected = {
            "bilbyJob": {
                "user": "Unknown User"
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

    @mock.patch('bilbyui.schema.request_job_filter', return_value=(None, [{"history": None}]))
    @mock.patch('bilbyui.schema.derive_job_status', side_effect=derive_job_status_mock)
    def test_bilby_job_status_query(self, request_job_filter_mock, derive_job_status_mock):
        """
        bilbyJob node query should allow querying of job status field"
        """
        response = self.job_request("jobStatus {name \n number \n date}")
        expected = {
            "bilbyJob": {
                "jobStatus": {
                    "name": "Test Status",
                    "number": 1,
                    "date": datetime.fromtimestamp(0).strftime("%Y-%m-%d %H:%M:%S UTC")
                }
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

    def test_bilby_job_last_updated_query(self):
        """
        bilbyJob node query should allow querying of last updated field"
        """
        response = self.job_request("lastUpdated")
        expected = {
            "bilbyJob": {
                "lastUpdated": self.job.last_updated.strftime("%Y-%m-%d %H:%M:%S UTC")
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

    def test_bilby_job_labels_query(self):
        """
        bilbyJob node query should allow querying of labels field"
        """
        response = self.job_request("labels {name \n description}")
        expected = {
            "bilbyJob": {
                "labels": [
                    {
                        "name": self.label.name,
                        "description": self.label.description
                    }
                ]
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )

    def test_bilby_job_event_id_query(self):
        """
        bilbyJob node query should allow querying of labels field"
        """
        response = self.job_request("eventId {eventId \n triggerId \n nickname \n isLigoEvent}")
        expected = {
            "bilbyJob": {
                "eventId": {
                    "eventId": self.event_id.event_id,
                    "triggerId": self.event_id.trigger_id,
                    "nickname": self.event_id.nickname,
                    "isLigoEvent": self.event_id.is_ligo_event,
                }
            }
        }
        self.assertDictEqual(
            expected, response.data, "bilbyJob query returned unexpected data."
        )
