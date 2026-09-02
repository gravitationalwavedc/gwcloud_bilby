from types import SimpleNamespace

from bilbyui.models import SupportingFile
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.views import parse_supporting_files


class TestParseSupportingFiles(BilbyTestCase):
    def _call(self, parser=None, args=None, **kwargs):
        parser = parser if parser is not None else SimpleNamespace()
        args = args if args is not None else SimpleNamespace()
        defaults = {
            "prior_file": None,
            "gps_file": None,
            "timeslide_file": None,
            "injection_file": None,
            "psd_dict": None,
        }
        defaults.update(kwargs)
        return parse_supporting_files(parser, args, **defaults)

    def test_captures_prior_gps_timeslide_and_injection_files(self):
        result = self._call(
            prior_file="/custom/prior.json",
            gps_file="/tmp/gps.dat",
            timeslide_file="/tmp/timeslide.dat",
            injection_file="/tmp/injection.dat",
        )

        self.assertEqual(result[SupportingFile.PRIOR], "/custom/prior.json")
        self.assertEqual(result[SupportingFile.GPS], "/tmp/gps.dat")
        self.assertEqual(result[SupportingFile.TIME_SLIDE], "/tmp/timeslide.dat")
        self.assertEqual(result[SupportingFile.INJECTION], "/tmp/injection.dat")

    def test_psd_dict_converted_to_dict_of_files(self):
        args = SimpleNamespace(psd_dict=None)
        result = self._call(args=args, psd_dict="{'H1': '/tmp/psd', 'V1': '/tmp/psd2'}")

        self.assertEqual(
            result[SupportingFile.PSD],
            [{"H1": "/tmp/psd"}, {"V1": "/tmp/psd2"}],
        )
        self.assertIsNone(args.psd_dict)

    def test_single_file_string_config(self):
        parser = SimpleNamespace(spline_calibration_envelope_dict="/tmp/cal.dat")
        args = SimpleNamespace(spline_calibration_envelope_dict="/tmp/cal.dat")

        result = self._call(parser=parser, args=args)

        self.assertEqual(result[SupportingFile.CALIBRATION], "/tmp/cal.dat")
        self.assertIsNone(parser.spline_calibration_envelope_dict)
        self.assertIsNone(args.spline_calibration_envelope_dict)

    def test_dict_of_files_config(self):
        parser = SimpleNamespace(data_dict={"H1": "/tmp/data1", "V1": "/tmp/data2"})
        args = SimpleNamespace(data_dict={"H1": "/tmp/data1", "V1": "/tmp/data2"})

        result = self._call(parser=parser, args=args)

        self.assertEqual(
            result[SupportingFile.DATA],
            [{"H1": "/tmp/data1"}, {"V1": "/tmp/data2"}],
        )
        self.assertIsNone(parser.data_dict)
        self.assertIsNone(args.data_dict)

    def test_default_distance_marginalization_table_skipped(self):
        parser = SimpleNamespace(distance_marginalization_lookup_table="outdir/.4s_distance_marginalization_lookup.npz")
        args = SimpleNamespace(distance_marginalization_lookup_table="outdir/.4s_distance_marginalization_lookup.npz")

        result = self._call(parser=parser, args=args)

        self.assertNotIn(SupportingFile.DISTANCE_MARGINALIZATION_LOOKUP_TABLE, result)

    def test_none_configs_skipped(self):
        result = self._call()

        self.assertEqual(result, {})
