"""Local, Elasticsearch-free projection of the search-field registry for help."""

from __future__ import annotations

import re

from bilbyui.services import search_registry

SYNTAX_HINT = "Search by `field:value`. Add `*` for a prefix. Combine terms with `AND`, `OR`, or `NOT`."
# Shown on the plain DB-backed surface (My Jobs), which only does a literal
# substring match on job name and description and honours no fielded syntax.
PLAIN_SYNTAX_HINT = "Search matches your job name and description."
# Shown on the gwflow surface (which has short aliases); empty elsewhere.
ALIAS_NOTE = (
    "Short names are provided for common fields. Their full field paths are "
    "also accepted and are shown in the full reference."
)
PLACEHOLDERS = {
    "gwflow": "Try sname:S2306*",
    "bilby": "Try job.name:GW150914*",
    "plain": "Try GW150914",
}
EXAMPLES = {
    "gwflow": [
        "sname:S2306*",
        "review_statuses:pass",
        "metadata.analyses.status:complete",
    ],
    "bilby": [
        "job.name:GW150914*",
        "params.waveform_approximant:IMRPhenomXPHM",
        "eventId.eventId:GW150914*",
    ],
    "plain": [],
}
_FIELD_TERM = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:\S")


def build_search_help(surface: str) -> dict:
    """Build the template context for a surface's search help (no ES/ORM)."""
    if surface == "plain":
        return {
            "syntax_hint": PLAIN_SYNTAX_HINT,
            "common": [],
            "groups": [],
            "typed_note": "",
            "alias_note": "",
            "placeholder": PLACEHOLDERS["plain"],
            "examples": EXAMPLES["plain"],
        }
    return {
        "syntax_hint": SYNTAX_HINT,
        "common": search_registry.common_fields(surface),
        "groups": search_registry.grouped_fields(surface),
        "typed_note": search_registry.typed_note(surface),
        "alias_note": ALIAS_NOTE if surface == "gwflow" else "",
        "placeholder": PLACEHOLDERS[surface],
        "examples": EXAMPLES[surface],
    }


def casing_hint_eligible(search: str, result_count: int) -> bool:
    """True only when a fielded advanced query returned zero results."""
    if not search or result_count != 0:
        return False
    return bool(_FIELD_TERM.search(search))
