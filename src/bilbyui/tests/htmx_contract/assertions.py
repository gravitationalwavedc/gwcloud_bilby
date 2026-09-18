"""Server-side assertions for semantic HTMX response contracts."""

from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.urls import resolve

from .registry import REGISTRY, EndpointContract, resolve_contract


class FragmentCollector(HTMLParser):
    """Collect IDs, roles, state markers, OOB roots and selector primitives."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.start_tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.start_tags.append((tag, dict(attrs)))

    @property
    def ids(self) -> list[str]:
        return [
            element_id
            for _, attrs in self.start_tags
            if (element_id := attrs.get("id")) is not None
        ]

    @property
    def announcements(self) -> list[dict[str, str | None]]:
        return [
            attrs for _, attrs in self.start_tags if attrs.get("role") in {"status", "alert"}
        ]

    @property
    def states(self) -> list[str]:
        return [
            state
            for _, attrs in self.start_tags
            if (state := attrs.get("data-async-state")) is not None
        ]

    @property
    def oob(self) -> list[dict[str, str | None]]:
        return [attrs for _, attrs in self.start_tags if "hx-swap-oob" in attrs]

    def selector_count(self, selector: str) -> int:
        if selector.startswith("#"):
            wanted = selector[1:].split(" ", 1)[0]
            return self.ids.count(wanted)
        if selector.startswith("."):
            wanted = selector[1:]
            return sum(
                wanted in (attrs.get("class") or "").split()
                for _, attrs in self.start_tags
            )
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
        root_id = parser.start_tags[0][1].get("id")
        test_case.assertEqual(
            root_id,
            contract.region_id,
            f"{contract.name}: fragment root must match target",
        )

    if state in contract.response_states:
        test_case.assertIn(
            state,
            parser.states,
            f"{contract.name}: missing data-async-state={state!r}",
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

    registered_oob = {item.root_id for item in contract.oob_roots}
    observed_oob = {attrs.get("id") for attrs in parser.oob}
    test_case.assertEqual(
        observed_oob,
        registered_oob,
        f"{contract.name}: unregistered or missing OOB roots",
    )

    selector = contract.focus.selector
    if selector:
        test_case.assertEqual(
            parser.selector_count(selector),
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
