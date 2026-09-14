"""Library-name normalisation for the cron package.

Mirrors ``bilbyui.utils.gwflow_version.normalise_libraries`` so that library
lists ingested by the cron match the Django side exactly. The cron package is
standalone and must not import the Django util, so this is a local copy.
"""


def normalise_libraries(raw):
    """Return a list of trimmed, non-blank, case-sensitively deduplicated
    library names, preserving first-seen portal order.

    Non-string values and whitespace-only strings are dropped. Values are
    stored trimmed (leading/trailing whitespace removed) and compared
    case-sensitively against the stored (trimmed) form.
    """
    if raw is None:
        return []

    seen = set()
    result = []
    for value in raw:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed:
            continue
        if trimmed in seen:
            continue
        seen.add(trimmed)
        result.append(trimmed)
    return result
