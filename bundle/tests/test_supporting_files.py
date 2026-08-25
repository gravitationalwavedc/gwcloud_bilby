import secrets
import string
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.case import TestCase

import requests
import responses

from tests.utils import args_to_bilby_ini, cd


class TestSupportingFiles(TestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.content = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(128))

        self.ini_file_v1_l1 = (
            """detectors=[V1, L1]\n"""
            """trigger-time=11111111\n"""
            """channel-dict={H1:GWOSC, L1:GWOSC}\n"""
            """gaussian-noise=True\n"""
            """n-simulation=1"""
        )

        self.ini_file_v1 = (
            """detectors=[V1]\n"""
            """trigger-time=11111111\n"""
            """channel-dict={H1:GWOSC, L1:GWOSC}\n"""
            """gaussian-noise=True\n"""
            """n-simulation=1"""
        )

    def perform_ini_save_load_cycle(self, args):
        """
        Performs a full cycle of saving the ini file from the provided args, then loading and parsing the ini file
        """
        from bilby_pipe.data_generation import DataGenerationInput
        from core.submit import bilby_ini_to_args

        ini = args_to_bilby_ini(args)
        args = bilby_ini_to_args(ini.decode("utf-8"))

        args.idx = 1
        args.ini = None

        input_args = DataGenerationInput(args, [], create_data=False)
        input_args.create_data(args)

        return input_args

    def test_psd1(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=(Path(__file__).parent.resolve() / "data/psd.txt").read_bytes(),
            status=200,
        )

        supporting_files = [{"type": "psd", "key": "V1", "file_name": "test.psd", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(args.psd_dict, {"V1": "./supporting_files/psd/test.psd"})

    def test_psd2(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=(Path(__file__).parent.resolve() / "data/psd.txt").read_bytes(),
            status=200,
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=(Path(__file__).parent.resolve() / "data/psd.txt").read_bytes(),
            status=200,
        )

        supporting_files = [
            {"type": "psd", "key": "V1", "file_name": "v1.psd", "token": token},
            {"type": "psd", "key": "L1", "file_name": "l1.psd", "token": token2},
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.psd_dict, {"V1": "./supporting_files/psd/v1.psd", "L1": "./supporting_files/psd/l1.psd"}
            )

    def test_psd3(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=(Path(__file__).parent.resolve() / "data/psd.txt").read_bytes(),
            status=200,
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=(Path(__file__).parent.resolve() / "data/psd.txt").read_bytes(),
            status=200,
        )

        token3 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token3}",
            body=(Path(__file__).parent.resolve() / "data/psd.txt").read_bytes(),
            status=200,
        )

        supporting_files = [
            {"type": "psd", "key": "V1", "file_name": "v1.psd", "token": token},
            {"type": "psd", "key": "H1", "file_name": "h1.psd", "token": token2},
            {"type": "psd", "key": "L1", "file_name": "l1.psd", "token": token3},
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.psd_dict,
                {
                    "V1": "./supporting_files/psd/v1.psd",
                    "H1": "./supporting_files/psd/h1.psd",
                    "L1": "./supporting_files/psd/l1.psd",
                },
            )

    def test_cal1(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [{"type": "cal", "key": "V1", "file_name": "test.cal", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(args.spline_calibration_envelope_dict, {"V1": "./supporting_files/cal/test.cal"})

    def test_cal2(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [
            {"type": "cal", "key": "V1", "file_name": "v1.cal", "token": token},
            {"type": "cal", "key": "H1", "file_name": "h1.cal", "token": token2},
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.spline_calibration_envelope_dict,
                {"V1": "./supporting_files/cal/v1.cal", "H1": "./supporting_files/cal/h1.cal"},
            )

    def test_cal3(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        token3 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token3}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [
            {"type": "cal", "key": "V1", "file_name": "v1.cal", "token": token},
            {"type": "cal", "key": "H1", "file_name": "h1.cal", "token": token2},
            {"type": "cal", "key": "L1", "file_name": "l1.cal", "token": token3},
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.spline_calibration_envelope_dict,
                {
                    "V1": "./supporting_files/cal/v1.cal",
                    "H1": "./supporting_files/cal/h1.cal",
                    "L1": "./supporting_files/cal/l1.cal",
                },
            )

    def test_prior_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [{"type": "pri", "key": None, "file_name": "test.prior", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertEqual(args.prior_file, "./supporting_files/pri/test.prior")

    def test_timeslide_gps_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=(Path(__file__).parent.resolve() / "data/gps_file_for_timeslides.txt").read_bytes(),
            status=200,
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=(Path(__file__).parent.resolve() / "data/timeslides.txt").read_bytes(),
            status=200,
        )

        supporting_files = [
            {"type": "gps", "key": None, "file_name": "test.gps", "token": token},
            {"type": "tsl", "key": None, "file_name": "test.timeslide", "token": token2},
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertTrue(args.gps_file.endswith("supporting_files/gps/test.gps"))
            self.assertTrue(args.timeslide_file.endswith("supporting_files/tsl/test.timeslide"))

    def test_injection_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=(Path(__file__).parent.resolve() / "data/test_injection.json").read_bytes(),
            status=200,
        )

        supporting_files = [{"type": "inj", "key": None, "file_name": "test_injection.json", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertTrue(args.injection_file.endswith("supporting_files/inj/test_injection.json"))

    def test_numerical_relativity_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [{"type": "nmr", "key": None, "file_name": "test.nmr", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertEqual(args.numerical_relativity_file, "./supporting_files/nmr/test.nmr")

    def test_distance_marginalization_lookup_table(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [{"type": "dml", "key": None, "file_name": "test.dml", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1_l1)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                        Path(working_directory)
                        / "supporting_files"
                        / supporting_file["type"]
                        / supporting_file["file_name"]
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertEqual(args.distance_marginalization_lookup_table, "./supporting_files/dml/test.dml")

    def test_unknown_supporting_file_type(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [{"type": "unknown", "key": "V1", "file_name": "test.unknown", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1)
            prepare_supporting_files(args, supporting_files, working_directory)

            self.assertFalse(
                (Path(working_directory) / "supporting_files" / "unknown" / "test.unknown").is_file()
            )

    def test_supporting_file_missing_type(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        supporting_files = [{"key": "V1", "file_name": "test.psd", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1)
            prepare_supporting_files(args, supporting_files, working_directory)

            self.assertFalse(
                (Path(working_directory) / "supporting_files" / "psd" / "test.psd").is_file()
            )

    def test_unsafe_supporting_file_name(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode("utf-8"),
            status=200,
        )

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            supporting_files = [
                {"type": "psd", "key": "V1", "file_name": "../../evil.psd", "token": token},
                {"type": "psd", "key": "V1", "file_name": f"{working_directory}/evil.psd", "token": token},
            ]

            args = bilby_ini_to_args(self.ini_file_v1)
            prepare_supporting_files(args, supporting_files, working_directory)

            # Unsafe file names are skipped, so no file is written outside the supporting_files dir
            self.assertFalse((Path(working_directory) / "evil.psd").is_file())

    def test_supporting_file_download_failure(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body="Not Found",
            status=404,
        )

        supporting_files = [{"type": "psd", "key": "V1", "file_name": "test.psd", "token": token}]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file_v1)
            with self.assertRaises(requests.HTTPError):
                prepare_supporting_files(args, supporting_files, working_directory)

            self.assertFalse(
                (Path(working_directory) / "supporting_files" / "psd" / "test.psd").is_file()
            )
