import secrets
import string
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.case import TestCase

import responses

from tests.utils import cd, args_to_bilby_ini
from utils.bilby_input import get_patched_bilby_input


class TestSupportingFiles(TestCase):
    def setUp(self):
        self.responses = responses.RequestsMock()
        self.responses.start()

        self.addCleanup(self.responses.stop)
        self.addCleanup(self.responses.reset)

        self.content = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(128))

        self.ini_file = """detectors=[V1, L1]\n""" \
                        """trigger-time=11111111\n""" \
                        """channel-dict={H1:GWOSC, L1:GWOSC}\n""" \
                        """gaussian-noise=True\n""" \
                        """n-simulation=1"""

    def perform_ini_save_load_cycle(self, args):
        """
        Performs a full cycle of saving the ini file from the provided args, then loading and parsing the ini file
        """
        from core.submit import bilby_ini_to_args
        from bilby_pipe.data_generation import DataGenerationInput

        ini = args_to_bilby_ini(args)
        args = bilby_ini_to_args(ini.decode('utf-8'))

        args.idx = 1
        args.ini = None

        input_args = get_patched_bilby_input(DataGenerationInput, args, [], create_data=False)
        input_args.create_data(args)

        return input_args

    def test_psd1(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=open(Path(__file__).parent.resolve() / 'data/psd.txt', 'rb').read(),
            status=200
        )

        supporting_files = [
            {
                'type': 'psd',
                'key': 'V1',
                'file_name': 'test.psd',
                'token': token
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(args.psd_dict, {'V1': './supporting_files/psd/test.psd'})

    def test_psd2(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=open(Path(__file__).parent.resolve() / 'data/psd.txt', 'rb').read(),
            status=200
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=open(Path(__file__).parent.resolve() / 'data/psd.txt', 'rb').read(),
            status=200
        )

        supporting_files = [
            {
                'type': 'psd',
                'key': 'V1',
                'file_name': 'v1.psd',
                'token': token
            },
            {
                'type': 'psd',
                'key': 'H1',
                'file_name': 'h1.psd',
                'token': token2
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.psd_dict,
                {
                    'V1': './supporting_files/psd/v1.psd',
                    'H1': './supporting_files/psd/h1.psd'
                }
            )

    def test_psd3(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=open(Path(__file__).parent.resolve() / 'data/psd.txt', 'rb').read(),
            status=200
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=open(Path(__file__).parent.resolve() / 'data/psd.txt', 'rb').read(),
            status=200
        )

        token3 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token3}",
            body=open(Path(__file__).parent.resolve() / 'data/psd.txt', 'rb').read(),
            status=200
        )

        supporting_files = [
            {
                'type': 'psd',
                'key': 'V1',
                'file_name': 'v1.psd',
                'token': token
            },
            {
                'type': 'psd',
                'key': 'H1',
                'file_name': 'h1.psd',
                'token': token2
            },
            {
                'type': 'psd',
                'key': 'L1',
                'file_name': 'l1.psd',
                'token': token3
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.psd_dict,
                {
                    'V1': './supporting_files/psd/v1.psd',
                    'H1': './supporting_files/psd/h1.psd',
                    'L1': './supporting_files/psd/l1.psd',
                }
            )

    def test_cal1(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode('utf-8'),
            status=200
        )

        supporting_files = [
            {
                'type': 'cal',
                'key': 'V1',
                'file_name': 'test.cal',
                'token': token
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(args.spline_calibration_envelope_dict, {'V1': './supporting_files/cal/test.cal'})

    def test_cal2(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode('utf-8'),
            status=200
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=self.content.encode('utf-8'),
            status=200
        )

        supporting_files = [
            {
                'type': 'cal',
                'key': 'V1',
                'file_name': 'v1.cal',
                'token': token
            },
            {
                'type': 'cal',
                'key': 'H1',
                'file_name': 'h1.cal',
                'token': token2
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.spline_calibration_envelope_dict,
                {
                    'V1': './supporting_files/cal/v1.cal',
                    'H1': './supporting_files/cal/h1.cal'
                }
            )

    def test_cal3(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode('utf-8'),
            status=200
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=self.content.encode('utf-8'),
            status=200
        )

        token3 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token3}",
            body=self.content.encode('utf-8'),
            status=200
        )

        supporting_files = [
            {
                'type': 'cal',
                'key': 'V1',
                'file_name': 'v1.cal',
                'token': token
            },
            {
                'type': 'cal',
                'key': 'H1',
                'file_name': 'h1.cal',
                'token': token2
            },
            {
                'type': 'cal',
                'key': 'L1',
                'file_name': 'l1.cal',
                'token': token3
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertDictEqual(
                args.spline_calibration_envelope_dict,
                {
                    'V1': './supporting_files/cal/v1.cal',
                    'H1': './supporting_files/cal/h1.cal',
                    'L1': './supporting_files/cal/l1.cal',
                }
            )

    def test_prior_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode('utf-8'),
            status=200
        )

        supporting_files = [
            {
                'type': 'pri',
                'key': None,
                'file_name': 'test.prior',
                'token': token
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertEqual(args.prior_file, './supporting_files/pri/test.prior')

    def test_timeslide_gps_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=open(Path(__file__).parent.resolve() / 'data/gps_file_for_timeslides.txt', 'rb').read(),
            status=200
        )

        token2 = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token2}",
            body=open(Path(__file__).parent.resolve() / 'data/timeslides.txt', 'rb').read(),
            status=200
        )

        supporting_files = [
            {
                'type': 'gps',
                'key': None,
                'file_name': 'test.gps',
                'token': token
            },
            {
                'type': 'tsl',
                'key': None,
                'file_name': 'test.timeslide',
                'token': token2
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertTrue(args.gps_file.endswith('supporting_files/gps/test.gps'))
            self.assertTrue(args.timeslide_file.endswith('supporting_files/tsl/test.timeslide'))

    def test_injection_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=open(Path(__file__).parent.resolve() / 'data/test_injection.json', 'rb').read(),
            status=200
        )

        supporting_files = [
            {
                'type': 'inj',
                'key': None,
                'file_name': 'test_injection.json',
                'token': token
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertTrue(args.injection_file.endswith('supporting_files/inj/test_injection.json'))

    def test_numerical_relativity_file(self):
        token = str(uuid.uuid4())
        self.responses.add(
            responses.GET,
            f"https://gwcloud.org.au/bilby/file_download/?fileId={token}",
            body=self.content.encode('utf-8'),
            status=200
        )

        supporting_files = [
            {
                'type': 'nmr',
                'key': None,
                'file_name': 'test.nmr',
                'token': token
            }
        ]

        from core.submit import bilby_ini_to_args, prepare_supporting_files

        with TemporaryDirectory() as working_directory, cd(working_directory):
            args = bilby_ini_to_args(self.ini_file)
            prepare_supporting_files(args, supporting_files, working_directory)

            for supporting_file in supporting_files:
                self.assertTrue(
                    (
                            Path(working_directory) /
                            'supporting_files' / supporting_file['type'] / supporting_file['file_name']
                    ).is_file()
                )

            args = self.perform_ini_save_load_cycle(args)

            self.assertEqual(args.numerical_relativity_file, './supporting_files/nmr/test.nmr')
