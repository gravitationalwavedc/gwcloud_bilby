import math

import numpy as np


def max_finite_time(values) -> float | None:
    maximum = None

    for value in values:
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue

        finite_value = float(value)
        if math.isfinite(finite_value) and (maximum is None or finite_value > maximum):
            maximum = finite_value

    return maximum
