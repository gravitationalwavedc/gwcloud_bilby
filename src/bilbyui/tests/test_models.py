from django.test import TestCase
from django.utils import timezone
from django.conf import settings

from bilbyui.models import BilbyJob, Label, FileDownloadToken
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
