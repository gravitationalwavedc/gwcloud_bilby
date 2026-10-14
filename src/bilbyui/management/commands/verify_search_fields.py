"""Verify curated search fields against populated live Elasticsearch indices."""

from __future__ import annotations

from collections.abc import Mapping

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from bilbyui.management.commands.es_ingest import build_bilby_es_mapping
from bilbyui.management.commands.gwflow_es_migrate import (
    _DEFAULT_FIELD,
    GWFLOW_ALIASES,
)
from bilbyui.services.search_registry import SEARCH_FIELDS, SURFACES, is_denied
from bilbyui.utils.gwflow_es import get_es_client

EXIT_OK = 0
EXIT_FAILURES = 1

UNEXPECTED_CAMELCASE_ALIASES = frozenset(
    {
        "reviewStatuses",
        "eventTriggerId",
        "searchTriggerTime",
        "lastUpdatedTime",
        "isPruned",
    }
)

NUMERIC_TYPES = frozenset(
    {
        "byte",
        "short",
        "integer",
        "long",
        "half_float",
        "float",
        "double",
        "scaled_float",
        "unsigned_long",
    }
)

COMPATIBLE_TYPES = {
    "number": NUMERIC_TYPES,
    "date": frozenset({"date", "date_nanos"}) | NUMERIC_TYPES,
    "boolean": frozenset({"boolean"}),
    "term": frozenset(
        {
            "keyword",
            "constant_keyword",
            "wildcard",
            "text",
            "match_only_text",
            "ip",
            "version",
        }
    ),
    "text": frozenset({"text", "match_only_text", "keyword", "wildcard"}),
}


def _flatten_properties(
    properties: Mapping[str, object],
    prefix: str = "",
) -> dict[str, dict[str, object]]:
    """Flatten mapping properties into leaf/alias paths and metadata."""

    fields: dict[str, dict[str, object]] = {}
    for name, raw_definition in properties.items():
        if not isinstance(raw_definition, Mapping):
            continue
        definition = dict(raw_definition)
        path = f"{prefix}.{name}" if prefix else name
        child_properties = definition.get("properties")
        if isinstance(child_properties, Mapping):
            fields.update(_flatten_properties(child_properties, path))
        if definition.get("type") not in (None, "object", "nested") or not child_properties:
            fields[path] = definition
    return fields


def _mapping_body(response: Mapping[str, object], index: str) -> Mapping[str, object]:
    """Return the mappings object from an Elasticsearch get_mapping response."""

    index_data = response.get(index)
    if not isinstance(index_data, Mapping):
        if len(response) == 1:
            index_data = next(iter(response.values()))
        else:
            return {}
    if not isinstance(index_data, Mapping):
        return {}
    mappings = index_data.get("mappings", {})
    return mappings if isinstance(mappings, Mapping) else {}


def _default_fields(surface: str) -> tuple[str, ...]:
    if surface == "gwflow":
        return tuple(_DEFAULT_FIELD)
    mapping = build_bilby_es_mapping()
    return tuple(mapping["settings"]["index"]["query"]["default_field"])


def _dig(mapping, *keys):
    current = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _normalise_default_field(value) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(part) for part in value)
    return (str(value),)


def _live_default_fields(client, index) -> tuple[str, ...]:
    response = client.indices.get_settings(index=index)
    index_data = response.get(index) if isinstance(response, Mapping) else None
    if not isinstance(index_data, Mapping):
        # Mirror _mapping_body: a single-index response may be keyed by a
        # resolved concrete index name rather than the requested name.
        if isinstance(response, Mapping) and len(response) == 1:
            index_data = next(iter(response.values()))
        else:
            return ()
    if not isinstance(index_data, Mapping):
        return ()
    block = index_data.get("settings", {})
    value = _dig(block, "index", "query", "default_field")
    if value is None and isinstance(block, Mapping):
        value = block.get("index.query.default_field")
    return _normalise_default_field(value)


def _type_is_compatible(type_hint: str | None, live_type: object) -> bool:
    if not type_hint or not isinstance(live_type, str):
        return True
    expected = COMPATIBLE_TYPES.get(type_hint)
    return expected is None or live_type in expected


def _verify_registry_entries(registry_entries, live):
    """Return failures for documented fields missing or changing type."""

    failures = []
    for entry in registry_entries:
        field_path = str(entry["path"])
        definition = live.get(field_path)
        if definition is None:
            failures.append(f"documented field missing: {field_path}")
            continue
        live_type = definition.get("type")
        type_hint = entry.get("type_hint")
        if not _type_is_compatible(
            str(type_hint) if type_hint else None,
            live_type,
        ):
            failures.append(f"syntax-relevant type changed: {field_path} expects {type_hint}, live type is {live_type}")
    return failures


def _verify_gwflow_aliases(live):
    """Return failures for missing or incompatible GWFlow aliases."""

    failures = []
    for alias, target in GWFLOW_ALIASES.items():
        definition = live.get(alias)
        if definition is None:
            failures.append(f"required GWFlow alias missing: {alias} -> {target}")
        elif definition.get("type") != "alias":
            failures.append(f"required GWFlow alias is not an alias: {alias}")
        elif definition.get("path") != target:
            failures.append(f"GWFlow alias target changed: {alias} expected {target}, live {definition.get('path')}")
        elif target not in live:
            failures.append(f"GWFlow alias target missing: {alias} -> {target}")

    for alias in sorted(UNEXPECTED_CAMELCASE_ALIASES & live.keys()):
        if live[alias].get("type") == "alias":
            failures.append(f"unexpected bare camelCase compatibility alias: {alias}")
    return failures


def _triage_paths(surface, live, registry_paths):
    """Return unrecognised searchable fields for manual review."""

    recognised = registry_paths | set(_default_fields(surface))
    if surface == "gwflow":
        recognised |= set(GWFLOW_ALIASES)
    return sorted(
        field_path
        for field_path, definition in live.items()
        if field_path not in recognised
        and definition.get("type") not in {"object", "nested", "alias"}
        and not is_denied(field_path)
    )


class Command(BaseCommand):
    help = (
        "Compare the curated search registry, GWFlow aliases, and configured "
        "default fields with populated live Elasticsearch mappings."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--surface",
            choices=SURFACES,
            help="Verify one search surface; by default both are verified.",
        )

    def execute(self, *args, **options):
        self._exit_code = EXIT_OK
        super().execute(*args, **options)
        if self._exit_code != EXIT_OK:
            raise CommandError(
                f"verify_search_fields exited with code {self._exit_code}",
                returncode=self._exit_code,
            )
        return self._exit_code

    def handle(self, *args, **options):
        surfaces = (options["surface"],) if options.get("surface") else SURFACES
        client = get_es_client()
        total_failures = 0
        total_triage = 0

        for surface in surfaces:
            failures, triage = self._verify_surface(client, surface)
            total_failures += len(failures)
            total_triage += len(triage)

            self.stdout.write(f"[{surface}]")
            for message in failures:
                self.stdout.write(self.style.ERROR(f"FAIL {message}"))
            for path in triage:
                self.stdout.write(self.style.WARNING(f"TRIAGE eligible live field is not in the registry: {path}"))
            if not failures and not triage:
                self.stdout.write(self.style.SUCCESS("OK no search-field drift found"))
            elif not failures:
                self.stdout.write(self.style.SUCCESS(f"OK {len(triage)} triage item(s); no deployment-gate failures"))

        self.stdout.write(f"Summary: failures={total_failures}, triage={total_triage}")
        self._exit_code = EXIT_FAILURES if total_failures else EXIT_OK

    def _verify_surface(self, client, surface):
        index = settings.ELASTIC_SEARCH_GWFLOW_INDEX if surface == "gwflow" else settings.ELASTIC_SEARCH_INDEX
        response = client.indices.get_mapping(index=index)
        mappings = _mapping_body(response, index)
        properties = mappings.get("properties", {})
        live = _flatten_properties(properties) if isinstance(properties, Mapping) else {}

        registry_entries = [entry for entry in SEARCH_FIELDS if entry["surface"] == surface]
        registry_paths = {str(entry["path"]) for entry in registry_entries}
        failures = _verify_registry_entries(registry_entries, live)

        if surface == "gwflow":
            failures.extend(_verify_gwflow_aliases(live))

        for field_path in _default_fields(surface):
            if field_path not in live:
                failures.append(f"configured default_field missing: {field_path}")

        live_defaults = _live_default_fields(client, index)
        configured = _default_fields(surface)
        if set(live_defaults) != set(configured):
            failures.append(f"live default_field mismatch: expected {sorted(configured)}, live {sorted(live_defaults)}")

        return failures, _triage_paths(surface, live, registry_paths)
