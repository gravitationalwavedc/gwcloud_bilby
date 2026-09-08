import json
import logging
import math
from collections.abc import Mapping

import astropy.cosmology
import astropy.units as u
import numpy as np
from django.db import transaction

from bilbyui.utils.ini_utils import bilby_ini_string_to_args

logger = logging.getLogger(__name__)

# Version of the gwcloud JSON envelope protocol used for non-native values.
_GWCLOUD_SCHEMA = 1

# Fixed placeholder used when str(value) itself raises during degradation.
_STRING_FALLBACK_PLACEHOLDER = "<unserializable object>"


def _type_name(value):
    """Fully-qualified name of a value's type, for logging (never the value itself)."""
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _normalise(value):
    """
    Recursively normalise a value into JSON-native types.

    Returns a ``(normalised, round_trip_ok)`` tuple. ``round_trip_ok`` is
    False when any nested value had to fall back to a string representation
    (i.e. it cannot be reconstructed from the stored form).

    Only concrete types are handled: mappings, lists/tuples, astropy
    Quantities, ndarrays, NumPy scalars, and JSON-native leaves. Anything
    else degrades to a string representation.
    """
    if value is None or isinstance(value, (str, bool)):
        return value, True
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value), False
        return value, True
    if isinstance(value, u.Quantity):
        normalised, ok = _normalise(value.value)
        return {
            "__gwcloud_type__": "astropy.quantity",
            "value": normalised,
            "unit": value.unit.to_string(),
        }, ok
    if isinstance(value, np.ndarray):
        return _normalise(value.tolist())
    if isinstance(value, np.generic):
        return _normalise(value.item())
    if isinstance(value, Mapping):
        out = {}
        ok = True
        for key, item in value.items():
            normalised, item_ok = _normalise(item)
            ok = ok and item_ok
            out[str(key)] = normalised
        return out, ok
    if isinstance(value, (list, tuple)):
        out = []
        ok = True
        for item in value:
            normalised, item_ok = _normalise(item)
            ok = ok and item_ok
            out.append(normalised)
        return out, ok
    try:
        return str(value), False
    except Exception:
        return _STRING_FALLBACK_PLACEHOLDER, False


def _serialise_cosmology(value):
    """
    Serialise an astropy Cosmology into a versioned, namespaced JSON envelope.

    The parameter set is derived from astropy's own ``to_format("mapping")``
    rather than a hard-coded per-class field list, so any supported
    cosmology class round-trips without code changes.
    """
    mapping = value.to_format("mapping")
    astropy_class = mapping.pop("cosmology")
    name = mapping.pop("name", None)
    meta = mapping.pop("meta", None)

    parameters, params_ok = _normalise(mapping)
    meta_normalised, meta_ok = _normalise(meta)

    return {
        "__gwcloud_type__": "astropy.cosmology",
        "__gwcloud_schema__": _GWCLOUD_SCHEMA,
        "astropy_class": astropy_class.__name__,
        "name": name,
        "parameters": parameters,
        "meta": meta_normalised,
        "round_trip": params_ok and meta_ok,
    }


def _degrade(value):
    """
    Build an explicit, non-round-trippable degradation envelope for an
    unknown exotic value rather than silently stringifying it.
    """
    try:
        value_str = str(value)
    except Exception:
        value_str = _STRING_FALLBACK_PLACEHOLDER
    return {
        "__gwcloud_type__": "python.string_fallback",
        "__gwcloud_schema__": _GWCLOUD_SCHEMA,
        "python_type": _type_name(value),
        "value": value_str,
        "round_trip": False,
    }


def safe_json_dumps(value):
    """
    Serialise ``value`` to a JSON string without raising on exotic types.

    JSON-serializable values are returned byte-identical to ``json.dumps``.
    astropy Cosmology instances are serialised into a structured envelope
    (see ``_serialise_cosmology``). Any other non-serializable value is
    persisted through an explicit degradation envelope (see ``_degrade``).
    """
    try:
        return json.dumps(value)
    except TypeError:
        if isinstance(value, astropy.cosmology.Cosmology):
            return json.dumps(_serialise_cosmology(value))
        return json.dumps(_degrade(value))


def _safe_serialise(key, value):
    """
    Serialise a single argument with per-argument error isolation.

    A failure serialising one value must not suppress the rest. The
    argument key and fully-qualified type are logged (never the value,
    which may contain sensitive information), and the failed argument
    still receives a fallback row.
    """
    try:
        return safe_json_dumps(value)
    except Exception:
        logger.exception("Failed to serialise argument %s of type %s", key, _type_name(value))
        return json.dumps(_degrade(value))


def parse_ini_file(job, ini_key_value_klass=None):
    """
    Parses the ini file from a job and generates a full set of ini key/value model instances

    :param job: The BilbyJob instance containing the ini_string content to parse
    :param ini_key_value_klass: Because this function can be called from a migration, we need to allow overriding
    the model to work with migration app models (See 0020_parse_ini_kv.py)
    :return: Nothing
    """

    # Avoiding circular imports
    from bilbyui.models import IniKeyValue
    from bilbyui.views import bilby_ini_args_to_data_input

    klass = ini_key_value_klass or IniKeyValue

    # Get the args from the ini
    args = bilby_ini_string_to_args((job.ini_string or "").encode("utf-8"))

    if args.detectors is None:
        raise ValueError("Detectors must be set")

    # Iterate over the parsed ini configuration and store the key/value pairs in the database
    items = []
    for idx, key in enumerate(vars(args)):
        val = getattr(args, key)

        items.append(klass(job=job, key=key, value=_safe_serialise(key, val), index=idx, processed=False))

    # Parse the args through DataGenerationInput to postprocess any values
    args.outdir = "./"

    try:
        processed_args = bilby_ini_args_to_data_input(args)

        for idx, key in enumerate(vars(processed_args)):
            stripped_key = key.lstrip("_")

            try:
                val = getattr(processed_args, stripped_key)

                items.append(
                    klass(
                        job=job,
                        key=stripped_key,
                        value=_safe_serialise(stripped_key, val),
                        index=idx,
                        processed=True,
                    )
                )
            except (AttributeError, TypeError):
                logger.exception("Error parsing INI file for job %s", job.id)

    except Exception:
        logger.exception("Error parsing INI file for job %s", job.id)

    # Replace existing k/v rows for this job atomically. All serialisation
    # happens above, before entering the transaction, so a serialisation
    # failure never leaves existing rows deleted and the transaction stays
    # limited to DB replacement.
    with transaction.atomic(using=klass.objects.db):
        klass.objects.filter(job=job).delete()
        klass.objects.bulk_create(items)
