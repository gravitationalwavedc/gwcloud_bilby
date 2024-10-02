import json
import uuid
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from bilbyui.models import BilbyJob, Label, FileDownloadToken, BilbyJobUploadToken, SupportingFile, EventID
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import update_bilby_job
from gw_bilby.jwt_tools import GWCloudUser


class TestBilbyJobModel(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name="Test_Job",
            description="Test job description",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.job.save()

        cls.event_id = EventID.objects.create(
            event_id="GW123456_123456",
            trigger_id="S123456a",
            nickname="GW123456",
            is_ligo_event=False,
            gps_time=1126259462.391,
        )

    def test_update_privacy(self):
        """
        Check that update_bilby_job view can update privacy of a job
        """
        self.assertEqual(self.job.private, False)

        user = GWCloudUser("bill")
        user.user_id = 1

        update_bilby_job(self.job.id, user, True, [])

        self.job.refresh_from_db()
        self.assertEqual(self.job.private, True)

    def test_update_event_id(self):
        """
        Check that update_bilby_job view can update the event ID of a job
        """
        # A user who doesn't own the job shouldn't be able to change the event id
        self.assertEqual(self.job.event_id, None)

        user = GWCloudUser("bill")
        user.user_id = self.job.user_id + 1

        with self.assertRaises(Exception):
            update_bilby_job(self.job.id, user, event_id=self.event_id.event_id)

        self.job.refresh_from_db()
        self.assertEqual(self.job.event_id, None)

        # If the user owns the job, they should be able to set the event id
        user.user_id = self.job.user_id

        update_bilby_job(self.job.id, user, event_id=self.event_id.event_id)

        self.job.refresh_from_db()
        self.assertEqual(self.job.event_id, self.event_id)

        # If the user is in PERMITTED_EVENT_CREATION_USER_IDS, they should be able to update someone else's job's event
        # id
        self.job.event_id = None
        self.job.save()

        user.user_id = self.job.user_id + 1

        with override_settings(PERMITTED_EVENT_CREATION_USER_IDS=[user.user_id]):
            update_bilby_job(self.job.id, user, event_id=self.event_id.event_id)

        self.job.refresh_from_db()
        self.assertEqual(self.job.event_id, self.event_id)

    def test_update_name(self):
        """
        Check that update_bilby_job view can update the name of a job
        """
        self.assertEqual(self.job.name, "Test_Job")

        user = GWCloudUser("bill")
        user.user_id = 1

        update_bilby_job(self.job.id, user, name="new_job")

        self.job.refresh_from_db()
        self.assertEqual(self.job.name, "new_job")

    def test_update_description(self):
        """
        Check that update_bilby_job view can update the description of a job
        """
        self.assertEqual(self.job.description, "Test job description")

        user = GWCloudUser("bill")
        user.user_id = 1

        update_bilby_job(self.job.id, user, description="new description")

        self.job.refresh_from_db()
        self.assertEqual(self.job.description, "new description")

    def test_update_labels(self):
        """
        Check that update_bilby_job view can update job labels
        """

        self.assertFalse(self.job.labels.exists())

        user = GWCloudUser("bill")
        user.user_id = 1

        update_bilby_job(self.job.id, user, False, ["Bad Run", "Review Requested"])

        self.job.refresh_from_db()

        self.assertQuerySetEqual(
            self.job.labels.all(),
            Label.objects.filter(name__in=["Bad Run", "Review Requested"]),
            ordered=False,
        )

    def test_as_dict_no_supporting_files(self):
        params = self.job.as_dict()

        self.assertEqual(params["name"], self.job.name)
        self.assertEqual(params["description"], self.job.description)
        self.assertEqual(params["ini_string"], self.job.ini_string)
        self.assertEqual(params["supporting_files"], [])

    def test_as_dict_supporting_files(self):
        supporting_file = SupportingFile.objects.create(
            job=self.job, file_type=SupportingFile.PRIOR, key=None, file_name="test.prior"
        )

        params = self.job.as_dict()

        # Make sure the params can be encoded as json
        json.dumps(params)

        self.assertEqual(params["name"], self.job.name)
        self.assertEqual(params["description"], self.job.description)
        self.assertEqual(params["ini_string"], self.job.ini_string)
        self.assertDictEqual(
            params["supporting_files"][0],
            {
                "type": supporting_file.file_type,
                "key": supporting_file.key,
                "file_name": supporting_file.file_name,
                "token": str(supporting_file.download_token),
            },
        )

        supporting_file2 = SupportingFile.objects.create(
            job=self.job, file_type=SupportingFile.CALIBRATION, key="V1", file_name="test.calib"
        )

        params = self.job.as_dict()
        json.dumps(params)

        self.assertEqual(params["name"], self.job.name)
        self.assertEqual(params["description"], self.job.description)
        self.assertEqual(params["ini_string"], self.job.ini_string)
        self.assertDictEqual(
            params["supporting_files"][0],
            {
                "type": supporting_file.file_type,
                "key": supporting_file.key,
                "file_name": supporting_file.file_name,
                "token": str(supporting_file.download_token),
            },
        )
        self.assertDictEqual(
            params["supporting_files"][1],
            {
                "type": supporting_file2.file_type,
                "key": supporting_file2.key,
                "file_name": supporting_file2.file_name,
                "token": str(supporting_file2.download_token),
            },
        )


class TestFileDownloadToken(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name="Test Job",
            description="Test job description",
            private=False,
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )
        cls.job.save()

    def test_create(self):
        # Test that given a job, and a list of paths, the correct objects are created in the database
        # and the correct order of objects is returned

        paths = [
            "/awesome_path1/data.txt",
            "/awesome_path1/data1.txt",
            "/awesome_path1/data2.txt",
            "/awesome_path1/data3.txt",
            "/awesome_path/data.txt",
        ]

        before = timezone.now()
        result = FileDownloadToken.create(self.job, paths)
        after = timezone.now()

        for i, p in enumerate(paths):
            self.assertEqual(result[i].path, p)
            self.assertEqual(result[i].job, self.job)
            self.assertTrue(result[i].token)
            self.assertTrue(before < result[i].created < after)

        for p in paths:
            result = FileDownloadToken.objects.get(job=self.job, path=p)
            self.assertEqual(result.path, p)
            self.assertEqual(result.job, self.job)
            self.assertTrue(result.token)
            self.assertTrue(before < result.created < after)

    def test_prune(self):
        # Test that FileDownloadToken objects older than settings.FILE_DOWNLOAD_TOKEN_EXPIRY are correctly removed from
        # the database

        # Test that objects created now are not removed
        paths = [
            "/awesome_path1/data.txt",
            "/awesome_path1/data1.txt",
            "/awesome_path1/data2.txt",
            "/awesome_path1/data3.txt",
            "/awesome_path/data.txt",
        ]

        FileDownloadToken.create(self.job, paths)
        after = timezone.now()

        FileDownloadToken.prune()

        self.assertEqual(FileDownloadToken.objects.all().count(), 5)

        # Check objects just inside the deletion time are not deleted
        for r in FileDownloadToken.objects.all():
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY - 1)
            r.save()

        FileDownloadToken.prune()

        self.assertEqual(FileDownloadToken.objects.all().count(), 5)

        # Check objects just outside the deletion time are deleted
        for r in FileDownloadToken.objects.all():
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY + 1)
            r.save()

        FileDownloadToken.prune()

        self.assertEqual(FileDownloadToken.objects.all().count(), 0)

    def test_get_paths(self):
        # Test that getting paths with valid tokens returns a list of paths in order
        paths = [
            "/awesome_path1/data.txt",
            "/awesome_path1/data1.txt",
            "/awesome_path1/data2.txt",
            "/awesome_path1/data3.txt",
            "/awesome_path/data.txt",
        ]

        fd_tokens = FileDownloadToken.create(self.job, paths)
        after = timezone.now()

        tokens = [tk.token for tk in fd_tokens]
        result = FileDownloadToken.get_paths(self.job, tokens)

        for i, tk in enumerate(fd_tokens):
            self.assertEqual(result[i], tk.path)

        # Check reverse order
        fd_tokens.reverse()
        tokens = [tk.token for tk in fd_tokens]
        result = FileDownloadToken.get_paths(self.job, tokens)

        for i, tk in enumerate(fd_tokens):
            self.assertEqual(result[i], tk.path)

        # Check that prune works as expected
        # Check objects just inside the deletion time are not deleted
        for r in FileDownloadToken.objects.all():
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY - 1)
            r.save()

        result = FileDownloadToken.get_paths(self.job, tokens)

        for i, tk in enumerate(fd_tokens):
            self.assertEqual(result[i], tk.path)

        # Set one object outside the expiry window
        r = FileDownloadToken.objects.all()[2]
        r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY + 1)
        r.save()

        result = FileDownloadToken.get_paths(self.job, tokens)

        for i, tk in enumerate(fd_tokens):
            if i == 2:
                self.assertEqual(result[i], None)
            else:
                self.assertEqual(result[i], tk.path)

        # Check objects just outside the deletion time are deleted
        for r in FileDownloadToken.objects.all():
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY + 1)
            r.save()

        result = FileDownloadToken.get_paths(self.job, tokens)
        self.assertEqual(result, [None] * 5)

        # No records should exist in the database anymore
        self.assertFalse(FileDownloadToken.objects.all().exists())


class TestBilbyJobUploadToken(TestCase):
    @classmethod
    def setUpTestData(cls):
        class TestUser:
            def __init__(self):
                self.is_ligo = False
                self.user_id = 1234

        cls.user = TestUser()

    def test_create(self):
        # Test that a token can correctly be created for uploading a bilby job

        before = timezone.now()
        result = BilbyJobUploadToken.create(self.user)
        after = timezone.now()

        self.assertEqual(result.user_id, self.user.user_id)
        self.assertEqual(result.is_ligo, self.user.is_ligo)
        self.assertTrue(result.token)
        self.assertTrue(before < result.created < after)

        self.assertEqual(BilbyJobUploadToken.objects.count(), 1)

        result = BilbyJobUploadToken.objects.last()
        self.assertEqual(result.user_id, self.user.user_id)
        self.assertEqual(result.is_ligo, self.user.is_ligo)
        self.assertTrue(result.token)
        self.assertTrue(before < result.created < after)

    def test_prune(self):
        # Test that BilbyJobUploadToken objects older than settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY are correctly removed
        # from the database

        # Test that objects created now are not removed
        BilbyJobUploadToken.create(self.user)
        after = timezone.now()

        BilbyJobUploadToken.prune()

        self.assertEqual(BilbyJobUploadToken.objects.all().count(), 1)

        # Check objects just inside the deletion time are not deleted
        r = BilbyJobUploadToken.objects.last()
        r.created = after - timezone.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY - 1)
        r.save()

        BilbyJobUploadToken.prune()

        self.assertEqual(BilbyJobUploadToken.objects.all().count(), 1)

        # Check objects just outside the deletion time are deleted
        r.created = after - timezone.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY + 1)
        r.save()

        BilbyJobUploadToken.prune()

        self.assertEqual(BilbyJobUploadToken.objects.all().count(), 0)

    def test_get_by_token(self):
        before = timezone.now()
        ju_token = BilbyJobUploadToken.create(self.user)
        after = timezone.now()

        token = ju_token.token

        result = BilbyJobUploadToken.get_by_token(token)

        self.assertEqual(result.user_id, self.user.user_id)
        self.assertEqual(result.is_ligo, self.user.is_ligo)
        self.assertTrue(result.token)
        self.assertTrue(before < result.created < after)

        # Check that prune works as expected
        # Check objects just inside the deletion time are not deleted
        r = BilbyJobUploadToken.objects.last()
        r.created = after - timezone.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY - 1)
        r.save()

        result = BilbyJobUploadToken.get_by_token(token)

        self.assertEqual(result.user_id, self.user.user_id)
        self.assertEqual(result.is_ligo, self.user.is_ligo)
        self.assertTrue(result.token)

        # Set the object outside the expiry window
        r = BilbyJobUploadToken.objects.last()
        r.created = after - timezone.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY + 1)
        r.save()

        result = BilbyJobUploadToken.get_by_token(token)

        self.assertEqual(result, None)

        # No records should exist in the database anymore
        self.assertFalse(BilbyJobUploadToken.objects.all().exists())


class TestSupportingFile(BilbyTestCase):
    @classmethod
    def setUp(self):
        class TestUser:
            def __init__(self):
                self.is_ligo = False
                self.user_id = 1234

        self.user = TestUser()

        self.parsed = {
            SupportingFile.PSD: [
                {
                    "H1": "/my/test/path/psd_h1.file",
                    "V1": "/my/test/path/psd_v1.file",
                }
            ],
            SupportingFile.GPS: "/another/test/path/gps.file",
        }

        self.job = BilbyJob.objects.create(
            user_id=self.user.user_id, ini_string=create_test_ini_string({"detectors": "['H1']"})
        )
        self.after = timezone.now()

    def test_save_from_parsed(self):
        # Test that parsed supporting files are correctly entered in to the database
        supporting_file_tokens = SupportingFile.save_from_parsed(self.job, self.parsed)

        self.assertEqual(SupportingFile.objects.count(), 3)

        for token in supporting_file_tokens:
            self.assertTrue(
                SupportingFile.objects.filter(
                    upload_token=token["token"], file_name=Path(token["file_path"]).name
                ).exists()
            )

    def test_pruning_jobs_with_non_uploaded_supporting_files(self):
        # Test that BilbyJob's objects older than settings.UPLOAD_SUPPORTING_FILE_EXPIRY are correctly removed
        # from the database if there are any SupportingFile's that are not uploaded

        # Test that objects created now are not removed
        SupportingFile.save_from_parsed(self.job, self.parsed)

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just inside the deletion time are not deleted
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY - 1)
        self.job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just outside the deletion time are deleted
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY + 1)
        self.job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 0)

    def test_pruning_jobs_with_all_uploaded_supporting_files(self):
        # Test that BilbyJob's objects older than settings.UPLOAD_SUPPORTING_FILE_EXPIRY are not removed
        # from the database if all SupportingFile's are uploaded

        # Check that if all supporting files are uploaded, the job is not deleted
        SupportingFile.save_from_parsed(self.job, self.parsed)

        self.assertEqual(SupportingFile.objects.count(), 3)

        for sf in SupportingFile.objects.all():
            sf.upload_token = None
            sf.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just inside the deletion time are not deleted
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY - 1)
        self.job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just outside the deletion time are not deleted if all supporting files are uploaded
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY + 1)
        self.job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

    def test_get_by_token_non_uploaded_files(self):
        # Tests that get_by_token correctly removes old BilbyJob instances that do not have all their
        # uploaded supporting files.

        # Test that objects created now are not removed
        tokens = [t["token"] for t in SupportingFile.save_from_parsed(self.job, self.parsed)]

        for t in tokens:
            self.assertIsNotNone(SupportingFile.get_by_upload_token(t))

        # Check objects just inside the deletion time are not deleted
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY - 1)
        self.job.save()

        for t in tokens:
            self.assertIsNotNone(SupportingFile.get_by_upload_token(t))

        # Check objects just outside the deletion time are deleted
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY + 1)
        self.job.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_upload_token(t))

        self.assertFalse(BilbyJob.objects.filter(id=self.job.id).exists())

    def test_get_by_token_all_uploaded_files(self):
        # Tests that get_by_token does not remove old BilbyJob instances that do have all their
        # uploaded supporting files.

        # Check that if all supporting files are uploaded, the job is not deleted
        tokens = [t["token"] for t in SupportingFile.save_from_parsed(self.job, self.parsed)]

        self.assertEqual(SupportingFile.objects.count(), 3)

        for sf in SupportingFile.objects.all():
            sf.upload_token = None
            sf.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_upload_token(t))

        self.assertTrue(BilbyJob.objects.filter(id=self.job.id).exists())

        # Check objects just inside the deletion time are not deleted
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY - 1)
        self.job.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_upload_token(t))

        self.assertTrue(BilbyJob.objects.filter(id=self.job.id).exists())

        # Check objects just outside the deletion time are not deleted if all supporting files are uploaded
        self.job.creation_time = self.after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY + 1)
        self.job.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_upload_token(t))

        self.assertTrue(BilbyJob.objects.filter(id=self.job.id).exists())

    def test_get_by_upload_token_invalid(self):
        # Test that a supporting file can't be fetched by an invalid token
        SupportingFile.save_from_parsed(self.job, self.parsed)
        self.assertIsNone(SupportingFile.get_by_upload_token(str(uuid.uuid4())))

    def test_get_by_download_token_invalid(self):
        # Test that a supporting file can't be fetched by an invalid token
        SupportingFile.save_from_parsed(self.job, self.parsed)
        self.assertIsNone(SupportingFile.get_by_download_token(str(uuid.uuid4())))

    def test_get_by_download_token(self):
        # Test that it's possible to get a SupportingFile object by the download token.
        SupportingFile.save_from_parsed(self.job, self.parsed)

        # Get the last inserted SupportingFile
        sf = SupportingFile.objects.last()

        # This file is not uploaded so get_by_download_token should return None
        self.assertIsNone(SupportingFile.get_by_download_token(sf.download_token))

        # Mark the supporting file as uploaded
        sf.upload_token = None
        sf.save()

        # Now the supporting file should be returned by get_by_download_token
        self.assertEqual(SupportingFile.get_by_download_token(sf.download_token).id, sf.id)
