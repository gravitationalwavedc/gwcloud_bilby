"""Local, Elasticsearch-free projection of the search-field registry for help."""

from __future__ import annotations

import re

from bilbyui.services import search_registry

SYNTAX_HINT = "Search by field with field:value. Add * for a prefix."
PLACEHOLDERS = {
    "gwflow": "Try sname:S2306*",
    "bilby": "Try job.name:GW150914*",
}
EXAMPLES = {
    "gwflow": [
        "sname:S2306*",
        "review_statuses:pass",
        "metadata.gracedb.events.network_snr:>10",
    ],
    "bilby": [
        "job.name:GW150914*",
        "params.waveform_approximant:IMRPhenomXPHM",
        "eventId.eventId:GW150914*",
    ],
}
_FIELD_TERM = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:\S")


def build_search_help(surface: str) -> dict:
    """Build the template context for a surface's search help (no ES/ORM)."""
    return {
        "syntax_hint": SYNTAX_HINT,
        "common": search_registry.common_fields(surface),
        "groups": search_registry.grouped_fields(surface),
        "typed_note": search_registry.typed_note(surface),
        "placeholder": PLACEHOLDERS[surface],
        "examples": EXAMPLES[surface],
    }


def casing_hint_eligible(search: str, result_count: int) -> bool:
    """True only when a fielded advanced query returned zero results."""
    if not search or result_count != 0:
        return False
    return bool(_FIELD_TERM.search(search))
