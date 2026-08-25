_VALID_TIME_RANGES = ("all", "1d", "1w", "1m", "1y")


def _normalize_time_range(time_range):
    if time_range not in _VALID_TIME_RANGES:
        return "all"
    return time_range
