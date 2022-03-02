from pathlib import Path

from django.test import TestCase
from django.utils import timezone
from django.conf import settings

from bilbyui.models import BilbyJob, Label, FileDownloadToken, BilbyJobUploadToken, SupportingFile
from bilbyui.views import update_bilby_job
from gw_bilby.jwt_tools import GWCloudUser


class TestBilbyJobModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name='Test Job',
            description='Test job description',
            private=False,
            ini_string='test-config=12345'
        )
        cls.job.save()

    def test_update_privacy(self):
        """
        Check that update_bilby_job view can update privacy of a job
        """
        self.assertEqual(self.job.private, False)

        user = GWCloudUser('bill')
        user.user_id = 1

        update_bilby_job(self.job.id, user, True, [])

        self.job.refresh_from_db()
        self.assertEqual(self.job.private, True)

    def test_update_labels(self):
        """
        Check that update_bilby_job view can update job labels
        """

        self.assertFalse(self.job.labels.exists())

        user = GWCloudUser('bill')
        user.user_id = 1

        update_bilby_job(self.job.id, user, False, ['Bad Run', 'Review Requested'])

        self.job.refresh_from_db()
        self.assertQuerysetEqual(
            self.job.labels.all(),
            list(map(repr, Label.objects.filter(name__in=['Bad Run', 'Review Requested']))),
            ordered=False
        )

    def test_as_json(self):
        params = self.job.as_json()

        self.assertEqual(params['name'], self.job.name)
        self.assertEqual(params['description'], self.job.description)
        self.assertEqual(params['ini_string'], self.job.ini_string)


class TestFileDownloadToken(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.job = BilbyJob.objects.create(
            user_id=1,
            name='Test Job',
            description='Test job description',
            private=False,
            ini_string='test-config=12345'
        )
        cls.job.save()

    def test_create(self):
        # Test that given a job, and a list of paths, the correct objects are created in the database
        # and the correct order of objects is returned

        paths = [
            '/awesome_path1/data.txt',
            '/awesome_path1/data1.txt',
            '/awesome_path1/data2.txt',
            '/awesome_path1/data3.txt',
            '/awesome_path/data.txt'
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
            '/awesome_path1/data.txt',
            '/awesome_path1/data1.txt',
            '/awesome_path1/data2.txt',
            '/awesome_path1/data3.txt',
            '/awesome_path/data.txt'
        ]

        FileDownloadToken.create(self.job, paths)
        after = timezone.now()

        FileDownloadToken.prune()

        self.assertEqual(FileDownloadToken.objects.all().count(), 5)

        # Check objects just inside the deletion time are not deleted
        for r in FileDownloadToken.objects.all():
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY-1)
            r.save()

        FileDownloadToken.prune()

        self.assertEqual(FileDownloadToken.objects.all().count(), 5)

        # Check objects just outside the deletion time are deleted
        for r in FileDownloadToken.objects.all():
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY+1)
            r.save()

        FileDownloadToken.prune()

        self.assertEqual(FileDownloadToken.objects.all().count(), 0)

    def test_get_paths(self):
        # Test that getting paths with valid tokens returns a list of paths in order
        paths = [
            '/awesome_path1/data.txt',
            '/awesome_path1/data1.txt',
            '/awesome_path1/data2.txt',
            '/awesome_path1/data3.txt',
            '/awesome_path/data.txt'
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
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY-1)
            r.save()

        result = FileDownloadToken.get_paths(self.job, tokens)

        for i, tk in enumerate(fd_tokens):
            self.assertEqual(result[i], tk.path)

        # Set one object outside the expiry window
        r = FileDownloadToken.objects.all()[2]
        r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY+1)
        r.save()

        result = FileDownloadToken.get_paths(self.job, tokens)

        for i, tk in enumerate(fd_tokens):
            if i == 2:
                self.assertEqual(result[i], None)
            else:
                self.assertEqual(result[i], tk.path)

        # Check objects just outside the deletion time are deleted
        for r in FileDownloadToken.objects.all():
            r.created = after - timezone.timedelta(seconds=settings.FILE_DOWNLOAD_TOKEN_EXPIRY+1)
            r.save()

        result = FileDownloadToken.get_paths(self.job, tokens)
        self.assertEqual(result, [None]*5)

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
        r.created = after - timezone.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY-1)
        r.save()

        BilbyJobUploadToken.prune()

        self.assertEqual(BilbyJobUploadToken.objects.all().count(), 1)

        # Check objects just outside the deletion time are deleted
        r.created = after - timezone.timedelta(seconds=settings.BILBY_JOB_UPLOAD_TOKEN_EXPIRY+1)
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


class TestSupportingFile(TestCase):
    @classmethod
    def setUpTestData(cls):
        class TestUser:
            def __init__(self):
                self.is_ligo = False
                self.user_id = 1234

        cls.user = TestUser()

    def test_save_from_parsed(self):
        # Test that parsed supporting files are correctly entered in to the database
        job = BilbyJob.objects.create(user_id=self.user.user_id)

        parsed = {
            SupportingFile.PSD: [
                {
                    'H1': '/my/test/path/psd_h1.file',
                    'V1': '/my/test/path/psd_v1.file',
                }
            ],
            SupportingFile.GPS: '/another/test/path/gps.file'
        }

        supporting_file_tokens = SupportingFile.save_from_parsed(job, parsed)

        self.assertEqual(SupportingFile.objects.count(), 3)

        for token in supporting_file_tokens:
            self.assertTrue(
                SupportingFile.objects.filter(upload_token=token['token'], file_name=Path(token['file_path']).name).exists()
            )

    def test_pruning(self):
        # Test that BilbyJob's objects older than settings.UPLOAD_SUPPORTING_FILE_EXPIRY are correctly removed
        # from the database if there are any SupportingFile's that are not uploaded

        job = BilbyJob.objects.create(user_id=self.user.user_id)

        # Test that objects created now are not removed
        parsed = {
            SupportingFile.PSD: [
                {
                    'H1': '/my/test/path/psd_h1.file',
                    'V1': '/my/test/path/psd_v1.file',
                }
            ],
            SupportingFile.GPS: '/another/test/path/gps.file'
        }

        SupportingFile.save_from_parsed(job, parsed)

        after = timezone.now()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just inside the deletion time are not deleted
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY-1)
        job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just outside the deletion time are deleted
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY+1)
        job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 0)

        # Finally check that if all supporting files are uploaded, the job is not deleted
        job = BilbyJob.objects.create(user_id=self.user.user_id)
        SupportingFile.save_from_parsed(job, parsed)

        self.assertEqual(SupportingFile.objects.count(), 3)

        for sf in SupportingFile.objects.all():
            sf.upload_token = None
            sf.save()

        after = timezone.now()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just inside the deletion time are not deleted
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY - 1)
        job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

        # Check objects just outside the deletion time are not deleted if all supporting files are uploaded
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY + 1)
        job.save()

        BilbyJob.prune_supporting_files_jobs()

        self.assertEqual(BilbyJob.objects.all().count(), 1)

    def test_get_by_token(self):
        job = BilbyJob.objects.create(user_id=self.user.user_id)
        after = timezone.now()

        # Test that objects created now are not removed
        parsed = {
            SupportingFile.PSD: [
                {
                    'H1': '/my/test/path/psd_h1.file',
                    'V1': '/my/test/path/psd_v1.file',
                }
            ],
            SupportingFile.GPS: '/another/test/path/gps.file'
        }

        tokens = [t['token'] for t in SupportingFile.save_from_parsed(job, parsed)]

        for t in tokens:
            self.assertIsNotNone(SupportingFile.get_by_token(t))

        # Check objects just inside the deletion time are not deleted
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY - 1)
        job.save()

        for t in tokens:
            self.assertIsNotNone(SupportingFile.get_by_token(t))

        # Check objects just outside the deletion time are deleted
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY + 1)
        job.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_token(t))

        self.assertFalse(BilbyJob.objects.filter(id=job.id).exists())

        # Finally check that if all supporting files are uploaded, the job is not deleted
        job = BilbyJob.objects.create(user_id=self.user.user_id)
        after = timezone.now()

        tokens = [t['token'] for t in SupportingFile.save_from_parsed(job, parsed)]

        self.assertEqual(SupportingFile.objects.count(), 3)

        for sf in SupportingFile.objects.all():
            sf.upload_token = None
            sf.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_token(t))

        self.assertTrue(BilbyJob.objects.filter(id=job.id).exists())

        # Check objects just inside the deletion time are not deleted
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY - 1)
        job.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_token(t))

        self.assertTrue(BilbyJob.objects.filter(id=job.id).exists())

        # Check objects just outside the deletion time are not deleted if all supporting files are uploaded
        job.creation_time = after - timezone.timedelta(seconds=settings.UPLOAD_SUPPORTING_FILE_EXPIRY + 1)
        job.save()

        for t in tokens:
            self.assertIsNone(SupportingFile.get_by_token(t))

        self.assertTrue(BilbyJob.objects.filter(id=job.id).exists())
