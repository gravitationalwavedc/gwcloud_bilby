"""Fail-closed source and rendered HTMX declaration auditing."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve

KNOWN_ATTRIBUTES = frozenset(
    {
        "hx-boost",
        "hx-get",
        "hx-include",
        "hx-indicator",
        "hx-post",
        "hx-push-url",
        "hx-select",
        "hx-swap",
        "hx-swap-oob",
        "hx-sync",
        "hx-target",
        "hx-trigger",
    }
)
REQUEST_ATTRIBUTES = frozenset({"hx-get", "hx-post"})
REQUESTLESS_REASONS = {
    "hx-boost": "Inherited navigation enhancement; descendants own the routes.",
    "hx-include": "Request parameter composition, derived from its requesting element.",
    "hx-indicator": "Loading indicator selector, derived from its requesting element.",
    "hx-on:*": "Client event handler; it does not declare a server endpoint.",
    "hx-push-url": "History behaviour, derived from its requesting element.",
    "hx-select": "Response selection behaviour, derived from its requesting element.",
    "hx-swap": "Swap behaviour, reconciled with its requesting element.",
    "hx-swap-oob": "Out-of-band response marker; it does not initiate a request.",
    "hx-sync": "Request synchronisation policy, derived from its requesting element.",
    "hx-target": "Target behaviour, reconciled with its requesting element.",
    "hx-trigger": "Request trigger policy, derived from its requesting element.",
}
_URL_TAG_RE = re.compile(
    r"""{%\s*url\s+(?:(?P<quote>['"])(?P<quoted>[^'"]+)(?P=quote)|(?P<dynamic>[A-Za-z_][A-Za-z0-9_.]*))(?:\s+.*?)?%}""",
    re.DOTALL,
)
_TEMPLATE_TAG_RE = re.compile(r"{%\s*(include|for|if)\b.*?%}", re.DOTALL)
_DYNAMIC_ID_RE = re.compile(r"(?<=\w)[-_]?\d+(?=$|[-_])")
_SOURCE_ATTRIBUTE_RE = re.compile(
    r"""(?P<name>hx-[A-Za-z0-9_-]+(?::[A-Za-z0-9_:-]+)?)"""
    r"""(?:\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote))?""",
    re.DOTALL,
)
_IGNORED_SOURCE_RE = re.compile(
    r"{#.*?#}|<!--.*?-->|<script\b[^>]*>.*?</script\s*>|<style\b[^>]*>.*?</style\s*>",
    re.IGNORECASE | re.DOTALL,
)
_START_TAG_RE = re.compile(r"<[A-Za-z][^<>]*>", re.DOTALL)
_HREF_ATTRIBUTE_RE = re.compile(
    r"""href\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)


class AuditError(AssertionError):
    """One or more declarations are outside the bounded audit contract."""


@dataclass(frozen=True)
class SourceDeclaration:
    path: str
    line: int
    name: str
    value: str
    url_name: str | None
    url_names: tuple[str, ...] = ()
    context: tuple[str, ...] = ()
    dynamic: bool = False
    element: int = 0
    boost_url_names: tuple[str, ...] = ()

    @property
    def location(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class RenderedDeclaration:
    route: str
    name: str
    value: str
    tag: str
    root: str
    ancestry: tuple[str, ...]
    ordinal: int
    effective_boost: bool = False

    @property
    def shape(self) -> tuple[str, str, str, str, tuple[str, ...]]:
        """Stable identity that excludes database-derived IDs."""
        return (
            self.route,
            self.name,
            normalise_value(self.value),
            self.root,
            self.ancestry,
        )


@dataclass(frozen=True)
class Exemption:
    name: str
    reason: str


def _canonical_name(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("hx-on:"):
        return lowered
    return lowered


def _valid_name(name: str) -> bool:
    return name in KNOWN_ATTRIBUTES or (name.startswith("hx-on:") and bool(name.removeprefix("hx-on:").strip(":")))


def _context_at(source: str, offset: int) -> tuple[str, ...]:
    return tuple(match.group(0).strip() for match in _TEMPLATE_TAG_RE.finditer(source, 0, offset))


def _masked_source(source: str) -> str:
    """Blank ignored regions while preserving offsets and line numbers."""

    def blank(match):
        return "".join("\n" if character == "\n" else " " for character in match.group())

    return _IGNORED_SOURCE_RE.sub(blank, source)


def _url_names(value: str) -> tuple[str, ...]:
    """Return every statically named Django URL tag in declaration order."""
    return tuple(name for match in _URL_TAG_RE.finditer(value) if (name := match.group("quoted")) is not None)


def extract_source(source: str, path: str = "<template>") -> tuple[SourceDeclaration, ...]:
    """Extract HTMX attributes from actual markup start tags only."""
    declarations: list[SourceDeclaration] = []
    errors: list[str] = []
    masked = _masked_source(source)

    for element, tag_match in enumerate(_START_TAG_RE.finditer(masked)):
        tag_source = tag_match.group()
        href_match = _HREF_ATTRIBUTE_RE.search(tag_source)
        boost_url_names = _url_names(href_match.group("value")) if href_match else ()
        for match in _SOURCE_ATTRIBUTE_RE.finditer(tag_source):
            raw_name = match.group("name")
            name = _canonical_name(raw_name)
            absolute_offset = tag_match.start() + match.start()
            line = source.count("\n", 0, absolute_offset) + 1
            location = f"{path}:{line}"

            if not _valid_name(name):
                errors.append(f"{location}: unknown HTMX attribute {name!r}")
                continue

            quote = match.group("quote")
            value = match.group("value")
            if quote is None:
                if name == "hx-boost":
                    value = ""
                else:
                    errors.append(f"{location}: unsupported dynamic or unquoted syntax for {name}")
                    continue

            url_names = _url_names(value)
            dynamic = ("{{" in value or "{%" in value) and not url_names
            declarations.append(
                SourceDeclaration(
                    path=path,
                    line=line,
                    name=name,
                    value=value,
                    url_name=url_names[0] if len(url_names) == 1 else None,
                    url_names=url_names,
                    context=_context_at(masked, absolute_offset),
                    dynamic=dynamic,
                    element=element,
                    boost_url_names=boost_url_names if name == "hx-boost" else (),
                )
            )

    if errors:
        raise AuditError("HTMX source audit failed:\n- " + "\n- ".join(errors))
    return tuple(declarations)


def extract_templates(root: str | Path) -> tuple[SourceDeclaration, ...]:
    """Extract every declaration under a bounded template tree."""
    template_root = Path(root)
    declarations: list[SourceDeclaration] = []
    errors: list[str] = []
    for path in sorted(template_root.rglob("*.html")):
        try:
            declarations.extend(extract_source(path.read_text(), str(path)))
        except AuditError as error:
            errors.extend(str(error).splitlines()[1:])
    if errors:
        raise AuditError("HTMX source audit failed:\n" + "\n".join(errors))
    return tuple(declarations)


def normalise_value(value: str) -> str:
    """Normalise loop-produced numeric identity while preserving declaration shape."""
    path = urlsplit(value).path
    if path:
        parts = ["<id>" if part.isdigit() else _DYNAMIC_ID_RE.sub("<id>", part) for part in path.split("/")]
        value = "/".join(parts)
    return re.sub(r"\s+", " ", value.strip())


class RenderedAuditParser(HTMLParser):
    """Collect declarations with stable roots, ancestry and inherited boost."""

    VOID_ELEMENTS = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    )

    def __init__(self, route: str):
        super().__init__(convert_charrefs=True)
        self.route = route
        self.declarations: list[RenderedDeclaration] = []
        self._stack: list[tuple[str, str, bool]] = []
        self._siblings: list[Counter[str]] = [Counter()]

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        parent_counter = self._siblings[-1]
        parent_counter[tag] += 1
        ordinal = parent_counter[tag]
        declared_boost = attributes.get("hx-boost", "").lower() not in {"", "false"}
        inherited_boost = declared_boost or any(item[2] for item in self._stack)
        element_id = attributes.get("id")
        root = next(
            (item[1] for item in reversed(self._stack) if item[1] != "<document>"),
            "<document>",
        )
        if element_id:
            root = normalise_value(f"#{element_id}")
        ancestry = tuple(f"{item[0]}[{index + 1}]" for index, item in enumerate(self._stack))
        for name, value in attrs:
            lowered = name.lower()
            if lowered.startswith("hx-"):
                if not _valid_name(lowered):
                    raise AuditError(f"{self.route}: rendered unknown HTMX attribute {lowered!r}")
                self.declarations.append(
                    RenderedDeclaration(
                        route=self.route,
                        name=lowered,
                        value=value or "",
                        tag=tag,
                        root=root,
                        ancestry=ancestry,
                        ordinal=ordinal,
                        effective_boost=inherited_boost,
                    )
                )
        if inherited_boost and tag in {"a", "form"} and "hx-boost" not in attributes:
            self.declarations.append(
                RenderedDeclaration(
                    route=self.route,
                    name="hx-boost",
                    value="inherited",
                    tag=tag,
                    root=root,
                    ancestry=ancestry,
                    ordinal=ordinal,
                    effective_boost=True,
                )
            )
        if tag not in self.VOID_ELEMENTS:
            self._stack.append((tag, root, inherited_boost))
            self._siblings.append(Counter())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                del self._siblings[index + 1 :]
                return


def extract_rendered(content: bytes | str, route: str) -> tuple[RenderedDeclaration, ...]:
    """Parse a rendered Django response with the standard library parser."""
    parser = RenderedAuditParser(route)
    parser.feed(content.decode() if isinstance(content, bytes) else content)
    parser.close()
    return tuple(parser.declarations)


def rendered_shapes(
    declarations: tuple[RenderedDeclaration, ...] | list[RenderedDeclaration],
) -> Counter[tuple[str, str, str, str, tuple[str, ...]]]:
    """Return stable declaration shapes and loop cardinalities."""
    return Counter(declaration.shape for declaration in declarations)


def _registered_url_names(contracts) -> Counter[str]:
    """Index every URL name covered by each semantic contract."""
    names: Counter[str] = Counter()
    for contract in contracts:
        registered = getattr(contract, "url_names", ())
        if not registered:
            value = getattr(contract, "url_name", None)
            registered = (value,) if value else ()
        for name in registered:
            if name and not name.startswith("not_applicable("):
                names[name] += 1
    return names


def _contract_swap(contract) -> str:
    """Return a contract's normalised swap, defaulting to htmx's ``innerHTML``."""
    return normalise_value(getattr(contract, "swap", None) or "innerHTML")


def _resolve_rendered_url(value: str) -> str | None:
    path = urlsplit(value).path
    if not path or not path.startswith("/"):
        return None
    try:
        return resolve(path).view_name
    except Resolver404:
        return None


def reconcile(
    source: tuple[SourceDeclaration, ...] | list[SourceDeclaration],
    rendered: tuple[RenderedDeclaration, ...] | list[RenderedDeclaration],
    contracts,
    *,
    require_rendered: bool = True,
) -> tuple[Exemption, ...]:
    """Reconcile request declarations and explicitly exempt requestless attributes."""
    errors: list[str] = []
    exemptions: dict[str, Exemption] = {}
    registry_names = _registered_url_names(contracts)
    rendered_names = Counter(item.name for item in rendered)
    element_attributes = {
        (declaration.path, declaration.element, declaration.name): declaration for declaration in source
    }

    def contracts_for(url_name):
        return [
            contract
            for contract in contracts
            if url_name
            in (
                getattr(contract, "url_names", ())
                or ((getattr(contract, "url_name", None),) if getattr(contract, "url_name", None) else ())
            )
        ]

    def element_target_swap(path, element):
        """Return an element's static literal target/swap, mirroring htmx defaults."""
        target_declaration = element_attributes.get((path, element, "hx-target"))
        target_literal = None
        if target_declaration is not None:
            target = target_declaration.value
            if "{{" not in target and "{%" not in target and target.lstrip().startswith("#"):
                target_literal = normalise_value(target).removeprefix("#")

        swap_declaration = element_attributes.get((path, element, "hx-swap"))
        swap_value = swap_declaration.value if swap_declaration is not None else "innerHTML"
        swap_literal = None
        if "{{" not in swap_value and "{%" not in swap_value:
            swap_literal = normalise_value(swap_value)

        return target_declaration, target_literal, swap_declaration, swap_literal

    def check_static_target_swap(declaration, declared_url_name, matches):
        """Apply the registry target/swap matching rule for one resolved URL name."""
        target_declaration, target_literal, swap_declaration, swap_literal = element_target_swap(
            declaration.path, declaration.element
        )
        if target_literal is not None and swap_literal is not None:
            matching = [
                contract
                for contract in matches
                if getattr(contract, "region_id", None) == target_literal and _contract_swap(contract) == swap_literal
            ]
            if not matching:
                location = target_declaration.location if target_declaration is not None else declaration.location
                errors.append(
                    f"{location}: hx-target #{target_literal} with hx-swap "
                    f"{swap_literal!r} matches no registry contract for {declared_url_name!r}"
                )
            elif len(matching) > 1:
                errors.append(
                    f"{declaration.location}: {declared_url_name!r} #{target_literal} "
                    f"{swap_literal!r} matches {len(matching)} registry contracts; ambiguous"
                )
        elif swap_literal is not None:
            swap_matches = [contract for contract in matches if _contract_swap(contract) == swap_literal]
            if not swap_matches and len({_contract_swap(contract) for contract in matches}) == 1:
                location = swap_declaration.location if swap_declaration is not None else declaration.location
                errors.append(
                    f"{location}: effective hx-swap {swap_literal!r} disagrees with "
                    f"contract swap {_contract_swap(matches[0])!r}"
                )
            elif len(swap_matches) > 1:
                errors.append(
                    f"{declaration.location}: {declared_url_name!r} swap {swap_literal!r} "
                    f"matches {len(swap_matches)} registry contracts; ambiguous"
                )

    def reconcile_boost_navigation(declaration):
        """Reconcile a boosted anchor against contracts covering its static href.

        Boosted navigation to endpoints outside the registry is out of scope and
        therefore skipped rather than failed; dynamic hrefs are never resolved.
        """
        if declaration.dynamic or not declaration.boost_url_names:
            return
        target_declaration, target_literal, swap_declaration, swap_literal = element_target_swap(
            declaration.path, declaration.element
        )
        static_target = target_declaration is not None and target_literal is not None
        static_swap = swap_declaration is not None and swap_literal is not None
        if not (static_target or static_swap):
            return
        for boost_url_name in declaration.boost_url_names:
            matches = contracts_for(boost_url_name)
            if not matches:
                continue
            check_static_target_swap(declaration, boost_url_name, matches)

    for declaration in source:
        if declaration.name not in REQUEST_ATTRIBUTES:
            key = "hx-on:*" if declaration.name.startswith("hx-on:") else declaration.name
            reason = REQUESTLESS_REASONS.get(key)
            if reason is None:
                errors.append(f"{declaration.location}: no bounded exemption for {declaration.name}")
            else:
                exemptions[key] = Exemption(key, reason)
            if declaration.name == "hx-boost":
                reconcile_boost_navigation(declaration)
            if require_rendered and rendered_names[declaration.name] == 0:
                errors.append(f"{declaration.location}: declaration absent from rendered fixtures: {declaration.name}")
            continue

        if declaration.dynamic:
            continue
        declared_url_names = declaration.url_names or ((declaration.url_name,) if declaration.url_name else ())
        if not declared_url_names:
            errors.append(f"{declaration.location}: unresolved URL for {declaration.name}")
        for declared_url_name in declared_url_names:
            matches = contracts_for(declared_url_name)
            if not matches:
                errors.append(f"{declaration.location}: {declared_url_name!r} resolves to 0 registry entries")
                continue
            check_static_target_swap(declaration, declared_url_name, matches)
        if require_rendered and rendered_names[declaration.name] == 0:
            errors.append(f"{declaration.location}: request declaration absent from rendered fixtures")

    for observation in rendered:
        if observation.name not in REQUEST_ATTRIBUTES:
            continue
        url_name = _resolve_rendered_url(observation.value)
        if url_name is None:
            errors.append(f"{observation.route}: unresolved rendered URL {observation.value!r} for {observation.name}")
        elif registry_names[url_name] == 0:
            errors.append(f"{observation.route}: rendered URL {observation.value!r} maps to 0 registry entries")

    if errors:
        raise AuditError("HTMX declaration reconciliation failed:\n- " + "\n- ".join(errors))
    return tuple(exemptions[name] for name in sorted(exemptions))
