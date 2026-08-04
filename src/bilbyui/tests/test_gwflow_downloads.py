import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from adacs_sso_plugin.constants import AUTHENTICATION_METHODS
from django.test import override_settings

from bilbyui.models import GWFlowFile, GWFlowJob
from bilbyui.tests.testcases import BilbyTestCase


class GWFlowDownloadTestCase(BilbyTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.create_user()
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def test_file_download_gwflow_file_success(self):
        """Test downloading a fully mirrored GWFlowFile for an authorized user."""
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job = GWFlowJob.objects.create(
                sname="S230601ag_success",
                user=self.user,
                ligo_only=False,
            )
            gwflow_file = GWFlowFile.objects.create(
                job=job,
                analysis_uid="",
                path="outdir/data.h5",
                file_name="data.h5",
                uploaded=True,
            )

            # Create file on disk at GWFLOW_FILE_UPLOAD_DIR / job.id / file.id
            job_file_dir = Path(self.temp_dir.name) / str(job.id)
            job_file_dir.mkdir(parents=True, exist_ok=True)
            file_disk_path = job_file_dir / str(gwflow_file.id)
            file_disk_path.write_bytes(b"binary file content")

            # Request download using download_token
            response = self.client.get(f"/file_download/?fileId={gwflow_file.download_token}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"binary file content")
            self.assertIn('filename="data.h5"', response.headers.get("Content-Disposition", ""))

    def test_file_download_gwflow_file_unuploaded_returns_404(self):
        """Test download fails with 404 when uploaded=False."""
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job = GWFlowJob.objects.create(
                sname="S230601ag_unuploaded",
                user=self.user,
                ligo_only=False,
            )
            gwflow_file = GWFlowFile.objects.create(
                job=job,
                analysis_uid="",
                path="outdir/data.h5",
                file_name="data.h5",
                uploaded=False,
            )

            job_file_dir = Path(self.temp_dir.name) / str(job.id)
            job_file_dir.mkdir(parents=True, exist_ok=True)
            file_disk_path = job_file_dir / str(gwflow_file.id)
            file_disk_path.write_bytes(b"some content")

            response = self.client.get(f"/file_download/?fileId={gwflow_file.download_token}")
            self.assertEqual(response.status_code, 404)

    def test_file_download_gwflow_file_missing_disk_file_returns_404(self):
        """Test download fails with 404 when uploaded=True but file is missing on disk."""
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job = GWFlowJob.objects.create(
                sname="S230601ag_missing_disk",
                user=self.user,
                ligo_only=False,
            )
            gwflow_file = GWFlowFile.objects.create(
                job=job,
                analysis_uid="",
                path="outdir/data.h5",
                file_name="data.h5",
                uploaded=True,
            )

            response = self.client.get(f"/file_download/?fileId={gwflow_file.download_token}")
            self.assertEqual(response.status_code, 404)

    def test_file_download_gwflow_file_ligo_only_visibility_matrix(self):
        """Test ligo_only visibility matrix across user authentication states."""
        with override_settings(GWFLOW_FILE_UPLOAD_DIR=self.temp_dir.name):
            job_ligo = GWFlowJob.objects.create(
                sname="S230601ag_ligo",
                user=self.user,
                ligo_only=True,
            )
            file_ligo = GWFlowFile.objects.create(
                job=job_ligo,
                analysis_uid="",
                path="outdir/ligo.h5",
                file_name="ligo.h5",
                uploaded=True,
            )
            ligo_dir = Path(self.temp_dir.name) / str(job_ligo.id)
            ligo_dir.mkdir(parents=True, exist_ok=True)
            (ligo_dir / str(file_ligo.id)).write_bytes(b"ligo data")

            job_public = GWFlowJob.objects.create(
                sname="S230601ag_public",
                user=self.user,
                ligo_only=False,
            )
            file_public = GWFlowFile.objects.create(
                job=job_public,
                analysis_uid="",
                path="outdir/public.h5",
                file_name="public.h5",
                uploaded=True,
            )
            public_dir = Path(self.temp_dir.name) / str(job_public.id)
            public_dir.mkdir(parents=True, exist_ok=True)
            (public_dir / str(file_public.id)).write_bytes(b"public data")

            # 1. Non-LIGO user (e.g. password auth default in create_user)
            non_ligo_user = self.create_user(id=10, authentication_method=AUTHENTICATION_METHODS["PASSWORD"])
            self.authenticate(user=non_ligo_user)

            # Non-LIGO user downloading ligo_only -> 404
            resp_ligo = self.client.get(f"/file_download/?fileId={file_ligo.download_token}")
            self.assertEqual(resp_ligo.status_code, 404)

            # Non-LIGO user downloading public -> 200
            resp_pub = self.client.get(f"/file_download/?fileId={file_public.download_token}")
            self.assertEqual(resp_pub.status_code, 200)

            # 2. LIGO authenticated user
            ligo_user = self.create_user(id=11, authentication_method=AUTHENTICATION_METHODS["LIGO_SHIBBOLETH"])
            self.authenticate(user=ligo_user)

            # LIGO user downloading ligo_only -> 200
            resp_ligo_ok = self.client.get(f"/file_download/?fileId={file_ligo.download_token}")
            self.assertEqual(resp_ligo_ok.status_code, 200)
            self.assertEqual(b"".join(resp_ligo_ok.streaming_content), b"ligo data")

            # LIGO user downloading public -> 200
            resp_pub_ok = self.client.get(f"/file_download/?fileId={file_public.download_token}")
            self.assertEqual(resp_pub_ok.status_code, 200)

            # 3. Anonymous unauthenticated user
            self.client.logout()
            resp_anon_ligo = self.client.get(f"/file_download/?fileId={file_ligo.download_token}")
            self.assertEqual(resp_anon_ligo.status_code, 404)

            resp_anon_pub = self.client.get(f"/file_download/?fileId={file_public.download_token}")
            self.assertEqual(resp_anon_pub.status_code, 200)

    def test_file_download_invalid_token_returns_404(self):
        """Test non-existent or invalid UUID token returns 404 fallthrough."""
        random_token = uuid.uuid4()
        response = self.client.get(f"/file_download/?fileId={random_token}")
        self.assertEqual(response.status_code, 404)

        invalid_token = "invalid-uuid-string"
        response = self.client.get(f"/file_download/?fileId={invalid_token}")
        self.assertEqual(response.status_code, 404)
