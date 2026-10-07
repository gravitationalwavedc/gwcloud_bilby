import json
import math

import numpy as np


def normalize_trigger(raw) -> float | None:
    if isinstance(raw, bool):
        return None

    if isinstance(raw, (int, float)):
        candidate = raw
    elif isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None

        try:
            candidate = json.loads(stripped)
        except (json.JSONDecodeError, RecursionError):
            candidate = stripped

        if isinstance(candidate, bool) or not isinstance(candidate, (int, float, str)):
            return None
    else:
        return None

    try:
        numeric = float(candidate)
    except (TypeError, ValueError, OverflowError):
        return None

    return numeric if math.isfinite(numeric) else None


def max_finite_time(values) -> float | None:
    maximum = None

    for value in values:
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue

        try:
            finite_value = float(value)
        except OverflowError:
            continue
        if math.isfinite(finite_value) and (maximum is None or finite_value > maximum):
            maximum = finite_value

    return maximum
