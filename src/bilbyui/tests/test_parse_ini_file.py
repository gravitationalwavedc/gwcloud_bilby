import json
import unittest
from unittest import mock

import astropy.cosmology
import astropy.units as u
import numpy as np
from django.test import override_settings

from bilbyui.models import BilbyJob, IniKeyValue
from bilbyui.tests.test_utils import create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.parse_ini_file import (
    _STRING_FALLBACK_PLACEHOLDER,
    _degrade,
    _normalise,
    _safe_serialise,
    _serialise_cosmology,
    _type_name,
    parse_ini_file,
    safe_json_dumps,
)


@override_settings(IGNORE_ELASTIC_SEARCH=True)
class TestParseIniFileErrorBranches(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.job = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="test job",
            description="test job",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_missing_detectors_raises(self):
        # An ini that omits detectors should trigger the "Detectors must be set" branch
        self.job.ini_string = "label=no-detectors-job"

        with self.assertRaisesMessage(Exception, "Detectors must be set"):
            parse_ini_file(self.job)

    def test_data_input_exception_is_logged(self):
        # If bilby_ini_args_to_data_input raises, the error should be logged and swallowed
        self.job.ini_string = create_test_ini_string({"detectors": "['H1']"})

        with (
            mock.patch(
                "bilbyui.views.bilby_ini_args_to_data_input",
                side_effect=RuntimeError("boom"),
            ),
            self.assertLogs("bilbyui.utils.parse_ini_file", level="ERROR") as logs,
        ):
            parse_ini_file(self.job)

        self.assertIn("Error parsing INI file", "\n".join(logs.output))

        # Unprocessed k/v pairs are still persisted despite the data-input failure
        self.assertTrue(IniKeyValue.objects.filter(job=self.job, processed=False).exists())
        self.assertFalse(IniKeyValue.objects.filter(job=self.job, processed=True).exists())


class TestNormalise(BilbyTestCase):
    def test_none_str_bool_passthrough(self):
        for value in (None, "a string", True, False):
            self.assertEqual(_normalise(value), (value, True))

    def test_finite_numbers_passthrough(self):
        self.assertEqual(_normalise(42), (42, True))
        self.assertEqual(_normalise(3.14), (3.14, True))
        self.assertEqual(_normalise(0), (0, True))

    def test_non_finite_float_falls_back_to_string(self):
        for value in (float("inf"), float("-inf"), float("nan")):
            normalised, ok = _normalise(value)
            self.assertEqual(normalised, str(value))
            self.assertFalse(ok)

    def test_quantity_envelope(self):
        normalised, ok = _normalise(5.0 * u.s)
        self.assertTrue(ok)
        self.assertEqual(
            normalised,
            {"__gwcloud_type__": "astropy.quantity", "value": 5.0, "unit": "s"},
        )

    def test_ndarray_unwrapped(self):
        normalised, ok = _normalise(np.array([1.0, 2.0]))
        self.assertTrue(ok)
        self.assertEqual(normalised, [1.0, 2.0])

    def test_numpy_scalar_unwrapped(self):
        normalised, ok = _normalise(np.float64(1.5))
        self.assertTrue(ok)
        self.assertEqual(normalised, 1.5)

    def test_mapping_recursion_with_round_trip_propagation(self):
        normalised, ok = _normalise({"a": 1, "b": {"c": 2.0}})
        self.assertTrue(ok)
        self.assertEqual(normalised, {"a": 1, "b": {"c": 2.0}})

        # A nested non-finite float marks the whole result as non-round-trippable
        normalised, ok = _normalise({"a": float("inf")})
        self.assertFalse(ok)
        self.assertEqual(normalised, {"a": str(float("inf"))})

    def test_list_tuple_recursion_with_round_trip_propagation(self):
        normalised, ok = _normalise([1, (2, 3.0)])
        self.assertTrue(ok)
        self.assertEqual(normalised, [1, [2, 3.0]])

        normalised, ok = _normalise([float("nan")])
        self.assertFalse(ok)
        self.assertEqual(normalised, [str(float("nan"))])

    def test_unknown_object_degrades_to_string(self):
        normalised, ok = _normalise(object())
        self.assertIsInstance(normalised, str)
        self.assertFalse(ok)

    def test_unserialisable_object_uses_placeholder(self):
        class _Bad:
            def __str__(self):
                raise RuntimeError("boom")

        normalised, ok = _normalise(_Bad())
        self.assertEqual(normalised, _STRING_FALLBACK_PLACEHOLDER)
        self.assertFalse(ok)

    def test_quantity_with_non_finite_value_not_round_trippable(self):
        normalised, ok = _normalise(float("nan") * u.s)
        self.assertFalse(ok)
        self.assertEqual(normalised["value"], str(float("nan")))


class TestSafeJsonDumps(unittest.TestCase):
    def test_json_native_passthrough(self):
        # JSON-native values must round-trip byte-identical to json.dumps
        value = {"a": [1, 2.5, "x", True, None]}
        self.assertEqual(safe_json_dumps(value), json.dumps(value))

    def test_cosmology_envelope(self):
        # A Cosmology must be serialised into the structured envelope
        cosmo = astropy.cosmology.FlatLambdaCDM(H0=70, Om0=0.3)
        result = json.loads(safe_json_dumps(cosmo))
        self.assertEqual(result["__gwcloud_type__"], "astropy.cosmology")
        self.assertEqual(result["astropy_class"], "FlatLambdaCDM")
        self.assertTrue(result["round_trip"])

    def test_unknown_value_degrade_envelope(self):
        # An exotic value must be persisted through the degradation envelope
        class Exotic:
            pass

        result = json.loads(safe_json_dumps(Exotic()))
        self.assertEqual(result["__gwcloud_type__"], "python.string_fallback")
        self.assertFalse(result["round_trip"])


class TestSerialiseCosmology(unittest.TestCase):
    def test_returns_versioned_envelope(self):
        cosmo = astropy.cosmology.FlatLambdaCDM(H0=70, Om0=0.3)
        result = _serialise_cosmology(cosmo)
        self.assertEqual(result["__gwcloud_type__"], "astropy.cosmology")
        self.assertEqual(result["__gwcloud_schema__"], 1)
        self.assertEqual(result["astropy_class"], "FlatLambdaCDM")
        self.assertTrue(result["round_trip"])


class TestDegrade(unittest.TestCase):
    def test_returns_placeholder_envelope(self):
        class Exotic:
            pass

        result = _degrade(Exotic())
        self.assertEqual(result["__gwcloud_type__"], "python.string_fallback")
        self.assertEqual(result["value"], "<unserializable object>")
        self.assertFalse(result["round_trip"])
        self.assertEqual(result["python_type"], _type_name(Exotic()))


class TestTypeName(unittest.TestCase):
    def test_returns_fully_qualified_name(self):
        self.assertEqual(_type_name(1), "builtins.int")
        self.assertEqual(_type_name("x"), "builtins.str")
        self.assertEqual(_type_name(5 * u.km), "astropy.units.quantity.Quantity")


class TestSafeSerialise(unittest.TestCase):
    def test_serialises_json_native_value(self):
        self.assertEqual(_safe_serialise("key", {"a": 1}), json.dumps({"a": 1}))

    def test_fallback_on_serialisation_failure(self):
        # If safe_json_dumps itself raises, the argument still gets a fallback row
        class Exploding:
            def __repr__(self):
                raise RuntimeError("boom")

        with mock.patch(
            "bilbyui.utils.parse_ini_file.safe_json_dumps",
            side_effect=RuntimeError("boom"),
        ):
            result = json.loads(_safe_serialise("key", Exploding()))
        self.assertEqual(result["__gwcloud_type__"], "python.string_fallback")
        self.assertFalse(result["round_trip"])
