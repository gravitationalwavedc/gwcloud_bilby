import json
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import astropy.cosmology
import astropy.units as u
import numpy as np
from astropy.cosmology import Cosmology, FlatLambdaCDM, LambdaCDM
from django.test import override_settings

from bilbyui.models import BilbyJob, EventID, IniKeyValue, _safe_json_loads
from bilbyui.tests.test_utils import compare_ini_kvs, create_test_ini_string
from bilbyui.tests.testcases import BilbyTestCase
from bilbyui.utils.parse_ini_file import _safe_serialise, parse_ini_file, safe_json_dumps

# Reference to the real implementation so a patched safe_json_dumps can still
# delegate to it for non-failing values in failure-isolation tests.
_real_safe_json_dumps = safe_json_dumps


def _explode_for_object(value):
    """Raise for bare ``object()`` instances, delegate otherwise."""
    if type(value) is object:
        raise RuntimeError("boom")
    return _real_safe_json_dumps(value)


class _BrokenStr:
    """An object whose ``str()`` raises, to exercise the guarded fallback."""

    def __str__(self):
        raise RuntimeError("cannot stringify")


def _reconstruct_cosmology(envelope):
    """
    Reconstruct an astropy Cosmology from a stored gwcloud envelope.

    This is representation-level reconstruction used only to prove the
    envelope is sufficient for astropy's ``from_format``; the production
    path does not import any class from stored data.
    """
    parameters = {}
    for key, value in envelope["parameters"].items():
        if isinstance(value, dict) and value.get("__gwcloud_type__") == "astropy.quantity":
            parameters[key] = value["value"] * u.Unit(value["unit"])
        else:
            parameters[key] = value
    mapping = {
        "cosmology": getattr(astropy.cosmology, envelope["astropy_class"]),
        "name": envelope["name"],
        "meta": envelope["meta"],
        **parameters,
    }
    return Cosmology.from_format(mapping, format="mapping")


class TestParseIniFile(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.job = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="test job",
            description="test job",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_empty_ini(self):
        # A job with an empty ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        compare_ini_kvs(self, self.job, "detectors=['H1']")

    def test_invalid_keys(self):
        # A job with no ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        compare_ini_kvs(
            self,
            self.job,
            """
                        detectors=['H1']
                        not-a-real-key=not-a-real-value
                        something-else=whatever""",
        )

    def test_valid_keys(self):
        self.job.ini_string = """
detectors=['H1']
pn-phase-order=12345
n-parallel=5432
label=my-awesome-job"""
        self.job.save()

        # A job with no ini file should not raise an exception
        parse_ini_file(self.job)

        # And should create all k/v's with default values
        compare_ini_kvs(self, self.job, self.job.ini_string)

        # Double check that the k/v's were correctly created
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="pn_phase_order", value="12345", processed=False).count(), 1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="pn_phase_order", value="12345", processed=True).count(), 1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="n_parallel", value="5432", processed=False).count(), 1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="label", value='"my-awesome-job"', processed=False).count(), 1
        )
        self.assertEqual(
            IniKeyValue.objects.filter(job=self.job, key="label", value='"my-awesome-job"', processed=True).count(), 1
        )


class TestSafeJsonDumps(BilbyTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()
        cls.job = BilbyJob.objects.create(
            user_id=cls.user.id,
            name="test job",
            description="test job",
            ini_string=create_test_ini_string({"detectors": "['H1']"}),
        )

    def test_matches_json_dumps_for_native_values(self):
        # Byte-identical output for every currently-serializable value.
        native_values = [
            None,
            True,
            False,
            0,
            1,
            -1,
            1.5,
            "hello",
            "",
            [1, 2, 3],
            {"a": 1, "b": [True, None]},
            [{"nested": {"deep": "value"}}],
        ]
        for value in native_values:
            self.assertEqual(safe_json_dumps(value), json.dumps(value))

    def test_regression_original_typeerror(self):
        # Reproduce the original bug: json.dumps cannot handle a cosmology.
        cosmology = FlatLambdaCDM(
            H0=67.9,
            Om0=0.3065,
            Tcmb0=2.725,
            Neff=3.04,
            m_nu=u.Quantity([0.0, 0.05, 0.1], u.eV),
            name="test",
        )
        with self.assertRaises(TypeError):
            json.dumps(cosmology)

        # The fix must not raise and must produce a structured envelope.
        envelope = json.loads(safe_json_dumps(cosmology))
        self.assertEqual(envelope["__gwcloud_type__"], "astropy.cosmology")

    def test_flatlambdacdm_unprocessed_loop(self):
        # Inject a cosmology into the unprocessed loop via a patched namespace.
        cosmology = FlatLambdaCDM(
            H0=67.9,
            Om0=0.3065,
            Tcmb0=2.725,
            Neff=3.04,
            Ob0=0.048,
            m_nu=u.Quantity([0.0, 0.0, 0.0], u.eV),
            name="test-cosmology",
        )
        with mock.patch(
            "bilbyui.utils.parse_ini_file.bilby_ini_string_to_args",
            return_value=SimpleNamespace(detectors=["H1"], cosmology=cosmology),
        ):
            parse_ini_file(self.job)

        row = IniKeyValue.objects.get(job=self.job, key="cosmology", processed=False)
        envelope = json.loads(row.value)
        self.assertEqual(envelope["__gwcloud_type__"], "astropy.cosmology")
        self.assertEqual(envelope["__gwcloud_schema__"], 1)
        self.assertEqual(envelope["astropy_class"], "FlatLambdaCDM")
        self.assertTrue(envelope["round_trip"])

        # Deterministic: re-serialising the same value yields the same bytes.
        self.assertEqual(row.value, safe_json_dumps(cosmology))

        # Representation-level reconstruction via astropy from_format.
        self.assertEqual(_reconstruct_cosmology(envelope), cosmology)

    def test_flatlambdacdm_processed_loop(self):
        # A real bilby ini produces a FlatLambdaCDM in the processed loop.
        parse_ini_file(self.job)

        row = IniKeyValue.objects.filter(job=self.job, key="cosmology", processed=True).first()
        self.assertIsNotNone(row)
        envelope = json.loads(row.value)
        self.assertEqual(envelope["__gwcloud_type__"], "astropy.cosmology")
        self.assertEqual(envelope["astropy_class"], "FlatLambdaCDM")
        self.assertTrue(envelope["round_trip"])

    def test_alternate_cosmology_round_trips(self):
        # A non-flat cosmology proves parameter discovery is not hard-coded.
        cosmology = LambdaCDM(H0=67.9, Om0=0.3065, Ode0=0.6935, name="test")
        envelope = json.loads(safe_json_dumps(cosmology))
        self.assertEqual(envelope["astropy_class"], "LambdaCDM")
        self.assertIn("Ode0", envelope["parameters"])
        self.assertTrue(envelope["round_trip"])
        self.assertEqual(_reconstruct_cosmology(envelope), cosmology)

    def test_array_quantity_retains_values_shape_units(self):
        cosmology = FlatLambdaCDM(
            H0=67.9,
            Om0=0.3065,
            Tcmb0=2.725,
            Neff=3.04,
            m_nu=u.Quantity([0.0, 0.05, 0.1], u.eV),
        )
        envelope = json.loads(safe_json_dumps(cosmology))
        m_nu = envelope["parameters"]["m_nu"]
        self.assertEqual(m_nu["__gwcloud_type__"], "astropy.quantity")
        self.assertEqual(m_nu["value"], [0.0, 0.05, 0.1])
        self.assertEqual(m_nu["unit"], "eV")
        reconstructed = _reconstruct_cosmology(envelope)
        self.assertTrue(np.allclose(reconstructed.m_nu.value, cosmology.m_nu.value))
        self.assertEqual(reconstructed.m_nu.unit, cosmology.m_nu.unit)

    def test_unknown_exotic_top_level_degrades(self):
        serialised = safe_json_dumps(object())
        envelope = json.loads(serialised)
        self.assertEqual(envelope["__gwcloud_type__"], "python.string_fallback")
        self.assertEqual(envelope["__gwcloud_schema__"], 1)
        self.assertEqual(envelope["python_type"], "builtins.object")
        self.assertEqual(envelope["value"], "<unserializable object>")
        self.assertFalse(envelope["round_trip"])
        # Degradation must be deterministic: two independently allocated
        # unsupported objects produce byte-identical persisted JSON (no
        # process-specific memory addresses in the stored value).
        self.assertEqual(serialised, safe_json_dumps(object()))

    def test_nested_meta_degradation_propagates(self):
        cosmology = FlatLambdaCDM(
            H0=67.9,
            Om0=0.3065,
            Tcmb0=2.725,
            Neff=3.04,
            m_nu=u.Quantity([0.0, 0.05, 0.1], u.eV),
            name="test",
        )
        cosmology.meta["exotic"] = object()
        envelope = json.loads(safe_json_dumps(cosmology))
        self.assertEqual(envelope["__gwcloud_type__"], "astropy.cosmology")
        self.assertFalse(envelope["round_trip"])
        # The nested exotic meta value degrades to a plain string and the
        # outer envelope's round_trip flag is set to false.
        self.assertIsInstance(envelope["meta"]["exotic"], str)

    def test_safe_serialise_failure_isolation(self):
        # A failure serialising one value must still produce a fallback row.
        result = _safe_serialise("bad_key", object())
        envelope = json.loads(result)
        self.assertEqual(envelope["__gwcloud_type__"], "python.string_fallback")
        self.assertFalse(envelope["round_trip"])

    def test_degrade_guards_broken_str(self):
        # If str(value) raises, the degradation envelope uses a placeholder.
        envelope = json.loads(safe_json_dumps(_BrokenStr()))
        self.assertEqual(envelope["__gwcloud_type__"], "python.string_fallback")
        self.assertEqual(envelope["value"], "<unserializable object>")
        self.assertFalse(envelope["round_trip"])

    def test_nested_normaliser_edge_cases(self):
        # Non-finite floats, NumPy scalars and broken-str values nested in
        # cosmology meta are normalised without raising.
        cosmology = FlatLambdaCDM(H0=67.9, Om0=0.3065, name="test")
        cosmology.meta["nan"] = float("nan")
        cosmology.meta["np_scalar"] = np.float32(1.5)
        cosmology.meta["broken"] = _BrokenStr()

        envelope = json.loads(safe_json_dumps(cosmology))
        self.assertEqual(envelope["__gwcloud_type__"], "astropy.cosmology")
        # Any nested fallback propagates round_trip to false.
        self.assertFalse(envelope["round_trip"])
        self.assertEqual(envelope["meta"]["nan"], "nan")
        self.assertEqual(envelope["meta"]["np_scalar"], 1.5)
        self.assertEqual(envelope["meta"]["broken"], "<unserializable object>")

    def test_non_json_native_values_degrade_to_string(self):
        # Complex numbers, bytes and datetimes are not JSON-native, so they
        # must degrade to a plain string representation with round_trip=False.
        cosmology = FlatLambdaCDM(H0=67.9, Om0=0.3065, name="test")
        cosmology.meta["complex"] = complex(1, 2)
        cosmology.meta["complex_array"] = np.array([1 + 2j, 3 + 4j])
        cosmology.meta["bytes"] = b"hello"
        cosmology.meta["datetime"] = datetime(2024, 1, 1)

        envelope = json.loads(safe_json_dumps(cosmology))
        self.assertEqual(envelope["__gwcloud_type__"], "astropy.cosmology")
        # Any nested fallback propagates round_trip to false.
        self.assertFalse(envelope["round_trip"])
        self.assertEqual(envelope["meta"]["complex"], "(1+2j)")
        self.assertEqual(envelope["meta"]["complex_array"], ["(1+2j)", "(3+4j)"])
        self.assertEqual(envelope["meta"]["bytes"], "b'hello'")
        self.assertEqual(envelope["meta"]["datetime"], "2024-01-01 00:00:00")

    def test_non_finite_float_is_not_round_trippable(self):
        # A non-finite float is stored as a string and therefore cannot be
        # reconstructed as a float, so round_trip must be false.
        cosmology = FlatLambdaCDM(H0=67.9, Om0=0.3065, name="test")
        cosmology.meta["nan"] = float("nan")
        envelope = json.loads(safe_json_dumps(cosmology))
        self.assertEqual(envelope["meta"]["nan"], "nan")
        self.assertFalse(envelope["round_trip"])

    def test_missing_detectors_raises(self):
        with mock.patch(
            "bilbyui.utils.parse_ini_file.bilby_ini_string_to_args",
            return_value=SimpleNamespace(detectors=None),
        ):
            with self.assertRaises(ValueError):
                parse_ini_file(self.job)

    def test_unprocessed_loop_failure_isolation(self):
        namespace = SimpleNamespace(detectors=["H1"], good_key="good-value", bad_key=object())
        with (
            mock.patch("bilbyui.utils.parse_ini_file.bilby_ini_string_to_args", return_value=namespace),
            mock.patch("bilbyui.utils.parse_ini_file.safe_json_dumps", side_effect=_explode_for_object),
        ):
            parse_ini_file(self.job)

        # The good argument still persists with its real value.
        self.assertTrue(
            IniKeyValue.objects.filter(job=self.job, key="good_key", value='"good-value"', processed=False).exists()
        )
        # The failed argument still receives a fallback row.
        bad = IniKeyValue.objects.get(job=self.job, key="bad_key", processed=False)
        envelope = json.loads(bad.value)
        self.assertEqual(envelope["__gwcloud_type__"], "python.string_fallback")
        self.assertFalse(envelope["round_trip"])

    def test_processed_loop_failure_isolation(self):
        unprocessed = SimpleNamespace(detectors=["H1"])
        processed = SimpleNamespace(good_key="good-value", bad_key=object())
        with (
            mock.patch("bilbyui.utils.parse_ini_file.bilby_ini_string_to_args", return_value=unprocessed),
            mock.patch("bilbyui.views.bilby_ini_args_to_data_input", return_value=processed),
            mock.patch("bilbyui.utils.parse_ini_file.safe_json_dumps", side_effect=_explode_for_object),
        ):
            parse_ini_file(self.job)

        self.assertTrue(
            IniKeyValue.objects.filter(job=self.job, key="good_key", value='"good-value"', processed=True).exists()
        )
        bad = IniKeyValue.objects.get(job=self.job, key="bad_key", processed=True)
        envelope = json.loads(bad.value)
        self.assertEqual(envelope["__gwcloud_type__"], "python.string_fallback")
        self.assertFalse(envelope["round_trip"])

    def test_existing_rows_survive_failed_replacement(self):
        parse_ini_file(self.job)
        before = IniKeyValue.objects.filter(job=self.job).count()
        self.assertGreater(before, 0)

        # A bulk_create failure inside the atomic block rolls back the delete,
        # so existing rows survive.
        with mock.patch.object(IniKeyValue.objects, "bulk_create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                parse_ini_file(self.job)

        self.assertEqual(IniKeyValue.objects.filter(job=self.job).count(), before)

    def test_repeated_parsing_replaces_rows(self):
        parse_ini_file(self.job)
        first = IniKeyValue.objects.filter(job=self.job).count()
        self.assertGreater(first, 0)

        parse_ini_file(self.job)
        second = IniKeyValue.objects.filter(job=self.job).count()
        self.assertEqual(first, second)

    def test_original_bilby_ini_syntax(self):
        # Use real bilby ini syntax (not only a mocked namespace).
        ini = create_test_ini_string({"detectors": "['H1']", "cosmology": "Planck15"})
        self.job.ini_string = ini
        self.job.save()

        parse_ini_file(self.job)

        compare_ini_kvs(self, self.job, ini)

    def test_rerun_rehydration(self):
        # Building the ES doc via _safe_json_loads returns the envelope dict
        # with no live Cosmology/Quantity/NumPy objects.
        cosmology = FlatLambdaCDM(
            H0=67.9,
            Om0=0.3065,
            Tcmb0=2.725,
            Neff=3.04,
            m_nu=u.Quantity([0.0, 0.05, 0.1], u.eV),
            name="test",
        )
        with mock.patch(
            "bilbyui.utils.parse_ini_file.bilby_ini_string_to_args",
            return_value=SimpleNamespace(detectors=["H1"], cosmology=cosmology),
        ):
            parse_ini_file(self.job)

        row = IniKeyValue.objects.get(job=self.job, key="cosmology", processed=False)
        loaded = _safe_json_loads(row.value)
        self.assertEqual(loaded["__gwcloud_type__"], "astropy.cosmology")
        self.assertEqual(type(loaded["parameters"]["H0"]), dict)
        self.assertEqual(type(loaded["parameters"]["Om0"]), float)
        self.assertEqual(type(loaded["parameters"]["m_nu"]["value"]), list)


class TestTriggerTimeWritePath(BilbyTestCase):
    _job_counter = 0

    @classmethod
    def setUpTestData(cls):
        cls.user = cls.create_user()

    def _job(self, ini_config=None):
        TestTriggerTimeWritePath._job_counter += 1
        return BilbyJob.objects.create(
            user_id=self.user.id,
            name=f"trigger-write-{TestTriggerTimeWritePath._job_counter}",
            description="trigger write",
            ini_string=create_test_ini_string(ini_config or {"detectors": "['H1']"}),
        )

    @override_settings(EMBARGO_START_TIME=100.0)
    def test_below_equal_above_threshold_stored_as_processed_float(self):
        for name, raw in (("below", "50.0"), ("equal", "100.0"), ("above", "150.0")):
            with self.subTest(name=name):
                job = self._job({"detectors": "['H1']", "trigger-time": raw})
                job.refresh_from_db()
                self.assertEqual(job.trigger_time, float(raw))

    def test_missing_processed_falls_back_to_raw(self):
        with mock.patch(
            "bilbyui.views.bilby_ini_args_to_data_input",
            side_effect=RuntimeError("boom"),
        ):
            job = self._job({"detectors": "['H1']", "trigger-time": "2.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 2.0)

    def test_both_missing_yields_null(self):
        job = self._job({"detectors": "['H1']"})
        job.refresh_from_db()
        self.assertIsNone(job.trigger_time)

    def test_processed_conversion_failure_yields_raw_or_null(self):
        # Raw value present -> normalized raw value is persisted.
        with mock.patch(
            "bilbyui.views.bilby_ini_args_to_data_input",
            side_effect=RuntimeError("boom"),
        ):
            job = self._job({"detectors": "['H1']", "trigger-time": "7.5"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 7.5)

        # Raw value absent -> NULL (never fabricated).
        with mock.patch(
            "bilbyui.views.bilby_ini_args_to_data_input",
            side_effect=RuntimeError("boom"),
        ):
            job = self._job({"detectors": "['H1']"})
        job.refresh_from_db()
        self.assertIsNone(job.trigger_time)

    def test_atomicity_failed_parse_does_not_commit_ini_or_trigger(self):
        job = self._job({"detectors": "['H1']", "trigger-time": "3.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 3.0)
        original_ini = job.ini_string

        job.ini_string = create_test_ini_string({"detectors": "['H1']", "trigger-time": "9.0"})
        with mock.patch(
            "bilbyui.utils.parse_ini_file.bilby_ini_string_to_args",
            return_value=SimpleNamespace(detectors=None),
        ):
            with self.assertRaises(ValueError):
                job.save()

        job.refresh_from_db()
        self.assertEqual(job.ini_string, original_ini)
        self.assertEqual(job.trigger_time, 3.0)

    def test_blank_ini_preserves_trigger_time(self):
        job = self._job({"detectors": "['H1']", "trigger-time": "4.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 4.0)

        job.ini_string = ""
        job.save()
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 4.0)

    def test_typed_write_does_not_reparse(self):
        job = self._job({"detectors": "['H1']", "trigger-time": "5.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 5.0)

        with mock.patch(
            "bilbyui.models.parse_ini_file",
            wraps=parse_ini_file,
        ) as parse_mock:
            BilbyJob.objects.filter(pk=job.pk).update(trigger_time=6.0)

        parse_mock.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 6.0)

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    @mock.patch("bilbyui.utils.reindex.reindex_jobs")
    def test_trigger_field_change_schedules_reindex_on_commit(self, reindex_jobs_mock):
        # Acceptance criterion #7: a trigger_time/event_id/gwflow_job change
        # schedules reindex_jobs([...], "bilby") via transaction.on_commit.
        job = self._job({"detectors": "['H1']", "trigger-time": "3.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 3.0)

        job.ini_string = create_test_ini_string({"detectors": "['H1']", "trigger-time": "9.0"})
        with self.captureOnCommitCallbacks(execute=True):
            job.save()

        reindex_jobs_mock.assert_called_once_with([job.pk], "bilby")
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 9.0)

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    @mock.patch("bilbyui.utils.reindex.reindex_jobs")
    def test_unchanged_trigger_fields_do_not_schedule_reindex(self, reindex_jobs_mock):
        # A plain save (no trigger-field change) must not schedule a redundant
        # reindex, even though parse_ini_file re-runs.
        job = self._job({"detectors": "['H1']", "trigger-time": "3.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 3.0)

        job.name = "renamed"
        with self.captureOnCommitCallbacks(execute=True):
            job.save()

        reindex_jobs_mock.assert_not_called()

    def test_migration_mode_skips_runtime_trigger_update(self):
        # When called from a historical migration (ini_key_value_klass is
        # supplied), the runtime typed update must be skipped: the
        # trigger_time column does not exist yet at migration 0020 (it
        # arrives in 0046), so the runtime model would emit SQL against a
        # table lacking the column.
        job = self._job({"detectors": "['H1']", "trigger-time": "3.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 3.0)

        with mock.patch.object(BilbyJob.objects, "filter") as filter_mock:
            parse_ini_file(job, IniKeyValue)

        filter_mock.assert_not_called()
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 3.0)

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    @mock.patch("bilbyui.utils.reindex.reindex_jobs")
    def test_blank_ini_trigger_change_schedules_reindex(self, reindex_jobs_mock):
        # Criterion #8: a trigger_time change on a blank-INI job must still
        # schedule reindex_jobs via transaction.on_commit.
        job = self._job({"detectors": "['H1']", "trigger-time": "3.0"})
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 3.0)

        job.ini_string = ""
        job.trigger_time = 9.0
        with self.captureOnCommitCallbacks(execute=True):
            job.save()

        reindex_jobs_mock.assert_called_once_with([job.pk], "bilby")
        job.refresh_from_db()
        self.assertEqual(job.trigger_time, 9.0)

    @override_settings(IGNORE_ELASTIC_SEARCH=True)
    @mock.patch("bilbyui.utils.reindex.reindex_jobs")
    def test_blank_ini_event_link_change_schedules_reindex(self, reindex_jobs_mock):
        # Criterion #8: an event link change on a blank-INI job must still
        # schedule reindex_jobs via transaction.on_commit.
        job = self._job({"detectors": "['H1']"})
        job.refresh_from_db()
        self.assertIsNone(job.trigger_time)

        event = EventID.objects.create(event_id="G123458")
        job.ini_string = ""
        job.event_id = event
        with self.captureOnCommitCallbacks(execute=True):
            job.save()

        reindex_jobs_mock.assert_called_once_with([job.pk], "bilby")
        job.refresh_from_db()
        self.assertEqual(job.event_id_id, event.id)
