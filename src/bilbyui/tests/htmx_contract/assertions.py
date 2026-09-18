"""Server-side assertions for semantic HTMX response contracts."""

from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.urls import resolve

from .registry import ASYNC_MARKERS, REGISTRY, EndpointContract, resolve_contract

# Placeholder live regions that announce a later client-side result (a copy
# confirmation) or a request in flight (an htmx indicator). They are not a
# settled server-state announcement, so they are outside the announcement budget.
NON_ANNOUNCING_CLASSES = frozenset({"htmx-indicator", "tech-value-status"})


class FragmentCollector(HTMLParser):
    """Collect IDs, roles, state markers, OOB roots and selector primitives."""

    VOID_ELEMENTS = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.start_tags: list[tuple[str, dict[str, str | None]]] = []
        self.ancestors: list[tuple[tuple[str, dict[str, str | None]], ...]] = []
        self._stack: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.start_tags.append((tag, attributes))
        self.ancestors.append(tuple(self._stack))
        if tag not in self.VOID_ELEMENTS:
            self._stack.append((tag, attributes))

    def handle_endtag(self, tag):
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                return

    @property
    def ids(self) -> list[str]:
        return [element_id for _, attrs in self.start_tags if (element_id := attrs.get("id")) is not None]

    @property
    def announcements(self) -> list[dict[str, str | None]]:
        return [
            attrs
            for _, attrs in self.start_tags
            if attrs.get("role") in {"status", "alert"}
            and not (NON_ANNOUNCING_CLASSES & set((attrs.get("class") or "").split()))
        ]

    def marker_count(self, class_name: str, role: str) -> int:
        """Count real async-state elements matching their class and live-region role."""
        return sum(
            class_name in (attrs.get("class") or "").split() and attrs.get("role") == role
            for _, attrs in self.start_tags
        )

    @property
    def oob(self) -> list[dict[str, str | None]]:
        return [attrs for _, attrs in self.start_tags if "hx-swap-oob" in attrs]

    def select(self, selector: str) -> list[dict[str, str | None]]:
        """Match elements against a bounded selector supporting class, attribute,
        tag and single-level descendant combinators (as the registry declares)."""
        matched = []
        for index, (tag, attrs) in enumerate(self.start_tags):
            if any(
                self._matches_compound(compound.strip(), tag, attrs, self.ancestors[index])
                for compound in selector.split(",")
            ):
                matched.append(attrs)
        return matched

    @classmethod
    def _matches_compound(cls, compound, tag, attrs, ancestors) -> bool:
        parts = compound.split()
        if not parts or not cls._matches_simple(parts[-1], tag, attrs):
            return False
        remaining = list(ancestors)
        for part in reversed(parts[:-1]):
            while remaining:
                ancestor_tag, ancestor_attrs = remaining.pop()
                if cls._matches_simple(part, ancestor_tag, ancestor_attrs):
                    break
            else:
                return False
        return True

    @staticmethod
    def _matches_simple(token, tag, attrs) -> bool:
        remainder = token
        attribute_filters: list[tuple[str, str | None]] = []
        while "[" in remainder:
            remainder, _, rest = remainder.partition("[")
            raw, _, remainder = rest.partition("]")
            name, _, value = raw.partition("=")
            attribute_filters.append((name.strip(), value.strip().strip("'\"")))
        class_filters = [c for c in remainder.split(".")[1:] if c]
        tag_filter = remainder.split(".")[0]
        if tag_filter and tag_filter != tag:
            return False
        if any(class_name not in (attrs.get("class") or "").split() for class_name in class_filters):
            return False
        for name, value in attribute_filters:
            if name not in attrs:
                return False
            if value and attrs.get(name) != value:
                return False
        return True

    def selector_count(self, selector: str) -> int:
        if selector.startswith("#"):
            wanted = selector[1:].split(" ", 1)[0]
            return self.ids.count(wanted)
        if selector.startswith("."):
            wanted = selector[1:]
            return sum(wanted in (attrs.get("class") or "").split() for _, attrs in self.start_tags)
        if selector.startswith("[") and selector.endswith("]"):
            attribute = selector[1:-1].split("=", 1)[0]
            return sum(attribute in attrs for _, attrs in self.start_tags)
        return sum(tag == selector for tag, _ in self.start_tags)


def parse_fragment(content: bytes | str) -> FragmentCollector:
    parser = FragmentCollector()
    parser.feed(content.decode() if isinstance(content, bytes) else content)
    parser.close()
    return parser


def assert_response_contract(test_case, contract: EndpointContract, response, *, state: str):
    """Validate one already-driven server response against an explicit contract."""
    test_case.assertIn(
        response.status_code,
        contract.accepted_statuses,
        f"{contract.name}: unexpected status {response.status_code}",
    )

    if contract.redirect is not None:
        if contract.redirect.kind == "hx":
            location = response.headers.get("HX-Redirect")
            test_case.assertTrue(location, f"{contract.name}: missing HX-Redirect")
        else:
            test_case.assertIn(
                response.status_code,
                {301, 302, 303, 307, 308},
                f"{contract.name}: expected ordinary redirect",
            )
            location = response.headers.get("Location")
        if contract.redirect.location is not None:
            test_case.assertEqual(location, contract.redirect.location)
        return

    if response.status_code == 204 or contract.swap == "none":
        test_case.assertEqual(
            response.content,
            b"",
            f"{contract.name}: no-content response unexpectedly has a body",
        )
        return

    parser = parse_fragment(response.content)
    if contract.region_id:
        test_case.assertTrue(parser.start_tags, f"{contract.name}: empty fragment")
        # ``target`` is the initiating element's target. Only an outerHTML swap
        # replaces that element, so only then must the response root carry the
        # target id. innerHTML swaps inject the fragment inside the target, so a
        # non-empty fragment plus the registered marker/announcement is asserted
        # instead (the response root is often a different, or anonymous, element).
        if contract.swap == "outerHTML" and state not in contract.async_states:
            root_id = parser.start_tags[0][1].get("id")
            test_case.assertEqual(
                root_id,
                contract.region_id,
                f"{contract.name}: fragment root must match target",
            )

    if state in contract.async_states:
        class_name = ASYNC_MARKERS[state]
        role = contract.announcement[state].role
        test_case.assertEqual(
            parser.marker_count(class_name, role),
            1,
            (f"{contract.name}: expected exactly one real production marker .{class_name}[role={role!r}] for {state}"),
        )

    test_case.assertLessEqual(
        len(parser.announcements),
        1,
        f"{contract.name}: duplicate announcements",
    )
    expectation = contract.announcement.get(state)
    if expectation and expectation.role:
        test_case.assertEqual(
            len(parser.announcements),
            1,
            f"{contract.name}: expected one announcement for {state}",
        )
        test_case.assertEqual(parser.announcements[0]["role"], expectation.role)
    elif expectation:
        test_case.assertEqual(
            parser.announcements,
            [],
            f"{contract.name}: expected silence because {expectation.silence_reason}",
        )

    if contract.retry is not None and state == contract.retry.from_state:
        retries = parser.select(contract.retry.selector)
        test_case.assertEqual(
            len(retries),
            1,
            f"{contract.name}: expected one retry control matching {contract.retry.selector!r}",
        )
        control = retries[0]
        test_case.assertTrue(
            control.get("hx-get") or control.get("hx-post"),
            f"{contract.name}: retry control must issue a request",
        )
        test_case.assertTrue(
            control.get("hx-target"),
            f"{contract.name}: retry control must declare a target",
        )

    registered_oob = {item.root_id for item in contract.oob_roots}
    observed_oob = {attrs.get("id") for attrs in parser.oob}
    test_case.assertEqual(
        observed_oob,
        registered_oob,
        f"{contract.name}: unregistered or missing OOB roots",
    )

    selector = contract.focus.selector
    if selector:
        # A fragment injected with innerHTML cannot carry a page-shell focus
        # destination (e.g. the section heading that lives beside #detail-pane);
        # those are browser-layer concerns. When the fragment does carry the
        # destination, or when the swap replaces the root, require it exactly once.
        observed = parser.selector_count(selector)
        if contract.swap == "outerHTML" or observed:
            test_case.assertEqual(
                observed,
                1,
                f"{contract.name}: focus destination {selector!r} must exist exactly once",
            )


def execute_contract(test_case, contract: EndpointContract, *, url: str, state_driver):
    """Drive named deterministic states, issue HX requests, and assert responses."""
    for state in sorted(contract.response_states):
        scenario = state_driver(contract, state)
        method = contract.method or "get"
        response = getattr(test_case.client, method)(
            scenario.get("url", url),
            data=scenario.get("data", {}),
            HTTP_HX_REQUEST="true",
            **scenario.get("request_kwargs", {}),
        )
        assert_response_contract(test_case, contract, response, state=state)


def assert_contract(
    url: str,
    region_id: str,
    *,
    test_case=None,
    state_driver=None,
    contracts: tuple[EndpointContract, ...] = REGISTRY,
):
    """Fixture-bound façade resolving exactly one registry entry.

    With a test case and state driver it delegates to the explicit executor.
    Without them it returns the uniquely resolved immutable contract, which is
    useful to declaration-audit callers.
    """
    match = resolve(urlsplit(url).path)
    url_name = match.view_name
    contract = resolve_contract(url_name, region_id, contracts)
    if test_case is None and state_driver is None:
        return contract
    if test_case is None or state_driver is None:
        raise TypeError("assert_contract requires both test_case and state_driver")
    return execute_contract(
        test_case,
        contract,
        url=url,
        state_driver=state_driver,
    )
