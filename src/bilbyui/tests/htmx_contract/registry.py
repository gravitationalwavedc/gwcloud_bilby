"""Semantic expectations for the HTMX interaction contract suite."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from .reachability import CONTRACTS as REACHABILITY

ALL_STATES = frozenset({"idle", "loading", "content", "empty", "stale", "error", "retry"})
LIFECYCLE_STATES = frozenset({"idle", "loading"})
RESPONSE_STATES = frozenset({"content", "empty", "stale", "error"})
ROLES = frozenset({"status", "alert"})
METHODS = frozenset({"get", "post", "delete"})
# States rendered through the shared _async_state.html partial, the CSS marker
# class that identifies them, and the live-region role that partial emits.
ASYNC_MARKERS = {
    "loading": "async-loading",
    "empty": "async-empty",
    "stale": "async-notice",
    "error": "async-error",
}
ASYNC_ROLES = {
    "loading": "status",
    "empty": "status",
    "stale": "alert",
    "error": "alert",
}


@dataclass(frozen=True)
class RetryExpectation:
    from_state: str
    terminal_states: frozenset[str]
    selector: str


@dataclass(frozen=True)
class RedirectExpectation:
    kind: Literal["ordinary", "hx"]
    location: str | None = None


@dataclass(frozen=True)
class OOBExpectation:
    root_id: str
    swap: str


@dataclass(frozen=True)
class AnnouncementExpectation:
    role: Literal["status", "alert"] | None = None
    silence_reason: str | None = None


@dataclass(frozen=True)
class FocusExpectation:
    rule: str
    selector: str | None = None


BrowserCapability = Literal["focus", "announcement", "loading", "race", "history", "clipboard"]


def _empty_mapping() -> Mapping[str, str]:
    return MappingProxyType({})


@dataclass(frozen=True)
class EndpointContract:
    name: str
    family: str
    method: Literal["get", "post", "delete"] | None
    url_name: str | None
    url_names: tuple[str, ...]
    url_kwargs_fixture: str | None
    target: str | None
    swap: str | None
    lifecycle_states: frozenset[str]
    response_states: frozenset[str]
    retry: RetryExpectation | None
    not_applicable: Mapping[str, str] = field(default_factory=_empty_mapping)
    blocking_gaps: Mapping[str, str] = field(default_factory=_empty_mapping)
    # Response states whose fragment is the shared _async_state.html partial.
    # ``target`` remains the initiating element's target; only outerHTML swaps
    # replace that element with the response root, so fragment-root equality is
    # asserted only for outerHTML, non-async states. innerHTML swaps assert a
    # non-empty fragment plus the registered announcement/marker instead.
    async_states: frozenset[str] = frozenset()
    accepted_statuses: frozenset[int] = frozenset({200})
    redirect: RedirectExpectation | None = None
    oob_roots: tuple[OOBExpectation, ...] = ()
    announcement: Mapping[str, AnnouncementExpectation] = field(default_factory=dict)
    focus: FocusExpectation = FocusExpectation("preserve")
    capabilities: frozenset[BrowserCapability] = frozenset()
    full_page: bool = False

    @property
    def region_id(self) -> str | None:
        if self.target and self.target.startswith("#") and " " not in self.target:
            return self.target[1:]
        return None


def _reason(value: str, prefix: str) -> str | None:
    marker = f"{prefix}("
    return value[len(marker) : -1] if value.startswith(marker) and value.endswith(")") else None


def validate_registry(contracts: tuple[EndpointContract, ...] | list[EndpointContract]) -> None:
    """Fail closed with diagnostics suitable for correcting registry records."""
    errors: list[str] = []
    names: set[str] = set()
    resolutions: dict[tuple[str, str], str] = {}

    for index, contract in enumerate(contracts):
        label = contract.name or f"record[{index}]"
        if not contract.name:
            errors.append(f"{label}: incomplete record: name is required")
        elif contract.name in names:
            errors.append(f"{label}: duplicate contract name")
        names.add(contract.name)

        if not contract.family:
            errors.append(f"{label}: incomplete record: family is required")
        if contract.method is not None and contract.method not in METHODS:
            errors.append(f"{label}: invalid method {contract.method!r}")
        if contract.method is not None and not contract.url_names:
            errors.append(f"{label}: incomplete record: server endpoint requires url_names")
        if contract.url_name and not contract.url_kwargs_fixture:
            errors.append(f"{label}: incomplete record: url_name requires url_kwargs_fixture")
        if contract.method is not None and not contract.target:
            errors.append(f"{label}: incomplete record: target is required")
        if contract.method is not None and not contract.swap:
            errors.append(f"{label}: incomplete record: swap is required")
        if not contract.accepted_statuses:
            errors.append(f"{label}: incomplete record: accepted_statuses is empty")
        if any(not isinstance(status, int) or not 100 <= status <= 599 for status in contract.accepted_statuses):
            errors.append(f"{label}: invalid HTTP status in accepted_statuses")

        declared = (
            contract.lifecycle_states
            | contract.response_states
            | frozenset(contract.not_applicable)
            | frozenset(contract.blocking_gaps)
            | (frozenset({"retry"}) if contract.retry is not None else frozenset())
        )
        unknown = declared - ALL_STATES
        if unknown:
            errors.append(f"{label}: unknown states: {', '.join(sorted(unknown))}")
        missing = ALL_STATES - declared
        if missing:
            errors.append(f"{label}: unclassified states: {', '.join(sorted(missing))}")
        overlaps = (
            (contract.lifecycle_states & contract.response_states)
            | (contract.lifecycle_states & frozenset(contract.not_applicable))
            | (contract.response_states & frozenset(contract.not_applicable))
            | (frozenset(contract.blocking_gaps) & declared - frozenset(contract.blocking_gaps))
        )
        if overlaps:
            errors.append(f"{label}: states classified more than once: {', '.join(sorted(overlaps))}")
        if not contract.lifecycle_states <= LIFECYCLE_STATES:
            errors.append(f"{label}: lifecycle_states contains a non-lifecycle state")
        if not contract.response_states <= RESPONSE_STATES:
            errors.append(f"{label}: response_states contains a non-response state")
        if "retry" not in contract.not_applicable and "retry" not in contract.blocking_gaps and contract.retry is None:
            errors.append(f"{label}: reachable retry requires retry semantics")
        if contract.retry and contract.retry.from_state not in contract.response_states:
            errors.append(f"{label}: retry source {contract.retry.from_state!r} is not reachable")
        for state, expectation in contract.announcement.items():
            if state not in contract.response_states:
                errors.append(f"{label}: announcement references unreachable state {state!r}")
            if expectation.role is not None and expectation.role not in ROLES:
                errors.append(f"{label}: invalid announcement role {expectation.role!r} for {state}")
            if bool(expectation.role) == bool(expectation.silence_reason):
                errors.append(f"{label}: announcement for {state} needs exactly one of role or silence_reason")
        missing_announcements = contract.response_states - frozenset(contract.announcement)
        if missing_announcements:
            errors.append(f"{label}: missing announcement semantics for {', '.join(sorted(missing_announcements))}")

        unknown_async = contract.async_states - RESPONSE_STATES
        if unknown_async:
            errors.append(
                f"{label}: async_states contains non-response states: {', '.join(sorted(unknown_async))}"
            )
        for state in contract.async_states:
            expected_role = ASYNC_ROLES[state]
            expectation = contract.announcement.get(state)
            if expectation is None or expectation.role != expected_role:
                errors.append(
                    f"{label}: async state {state!r} must announce role {expected_role!r} "
                    f"to match its .{ASYNC_MARKERS[state]} marker"
                )

        if contract.region_id:
            for registered_url_name in contract.url_names:
                key = (registered_url_name, contract.region_id)
                prior = resolutions.get(key)
                if prior:
                    errors.append(f"{label}: ambiguous url/region resolution {key!r}; also registered by {prior}")
                resolutions[key] = label

    if errors:
        raise ValueError("Invalid HTMX endpoint registry:\n- " + "\n- ".join(errors))


def resolve_contract(
    url_name: str, region_id: str, contracts: tuple[EndpointContract, ...] | None = None
) -> EndpointContract:
    """Resolve exactly one semantic contract by URL name and target region."""
    source = REGISTRY if contracts is None else contracts
    region_id = region_id.removeprefix("#")
    matches = [contract for contract in source if url_name in contract.url_names and contract.region_id == region_id]
    if len(matches) != 1:
        names = ", ".join(contract.name for contract in matches) or "none"
        raise LookupError(
            f"Expected exactly one contract for url={url_name!r}, region={region_id!r}; found {len(matches)} ({names})"
        )
    return matches[0]


def _announcement(
    states: frozenset[str], announcing: Mapping[str, str]
) -> Mapping[str, AnnouncementExpectation]:
    return MappingProxyType(
        {
            state: (
                AnnouncementExpectation(role=announcing[state])
                if state in announcing
                else AnnouncementExpectation(
                    silence_reason="Content-equivalent fragment replacement is intentionally silent"
                )
            )
            for state in states
        }
    )


DEFAULT_FOCUS = FocusExpectation("preserve")


def _contract(
    name: str,
    *,
    method: str | None = None,
    url_name: str | None = None,
    url_names: tuple[str, ...] | None = None,
    target: str | None = None,
    swap: str | None = None,
    kwargs: str | None = None,
    statuses: frozenset[int] = frozenset({200}),
    focus: FocusExpectation = DEFAULT_FOCUS,
    capabilities: frozenset[BrowserCapability] = frozenset({"loading", "announcement"}),
    full_page: bool = True,
    async_states: frozenset[str] = frozenset(),
    announcing: Mapping[str, str] | None = None,
) -> EndpointContract:
    source = REACHABILITY[name]
    states = source["states"]
    lifecycle = frozenset(state for state in LIFECYCLE_STATES if states[state] == "reachable")
    responses = frozenset(state for state in RESPONSE_STATES if states[state] == "reachable")
    not_applicable = {
        state: reason for state, value in states.items() if (reason := _reason(value, "not_applicable")) is not None
    }
    blocking_gaps = {
        state: reason
        for state, value in states.items()
        if (reason := _reason(value, "BLOCKING_PRODUCT_GAP")) is not None
    }
    retry = None
    if states["retry"] == "reachable":
        terminals = responses - {"error"}
        retry = RetryExpectation("error", terminals or frozenset({"content"}), ".async-error button[hx-get], .async-error form[hx-post]")

    roles: dict[str, str] = {state: ASYNC_ROLES[state] for state in async_states}
    roles.setdefault("error", "alert")
    if announcing:
        roles.update(announcing)

    return EndpointContract(
        name=name,
        family=source["family"],
        method=method,
        url_name=url_name,
        url_names=url_names or ((url_name,) if url_name else ()),
        url_kwargs_fixture=kwargs,
        target=target,
        swap=swap,
        lifecycle_states=lifecycle,
        response_states=responses,
        retry=retry,
        not_applicable=MappingProxyType(not_applicable),
        blocking_gaps=MappingProxyType(blocking_gaps),
        async_states=async_states,
        accepted_statuses=statuses,
        announcement=_announcement(responses, roles),
        focus=focus,
        capabilities=capabilities,
        full_page=full_page,
    )


REGISTRY = (
    _contract(
        "gwflow_list_search_filter_pagination",
        method="get",
        url_name="bilbyui:gwflow_jobs",
        target="#gwflow-job-list",
        swap="innerHTML",
        kwargs="no_kwargs",
        capabilities=frozenset({"loading", "announcement", "race", "history"}),
        async_states=frozenset({"empty", "error"}),
        announcing={"content": "status", "empty": "status"},
    ),
    _contract(
        "gwflow_detail_metadata",
        method="get",
        url_name="bilbyui:gwflow_job_metadata",
        target="#detail-pane",
        swap="innerHTML",
        kwargs="gwflow_job",
        focus=FocusExpectation("section_heading", "#detail-pane [tabindex='-1']"),
        async_states=frozenset({"error"}),
    ),
    _contract(
        "gwflow_detail_files",
        method="get",
        url_name="bilbyui:gwflow_job_files",
        target="#detail-pane",
        swap="innerHTML",
        kwargs="gwflow_job",
        focus=FocusExpectation("section_heading", "#detail-pane [tabindex='-1']"),
        async_states=frozenset({"empty"}),
        announcing={"empty": "status"},
    ),
    _contract(
        "gwflow_detail_history",
        method="get",
        url_name="bilbyui:gwflow_job_history",
        target="#detail-pane",
        swap="innerHTML",
        kwargs="gwflow_job",
        focus=FocusExpectation("section_heading", "#detail-pane [tabindex='-1']"),
        async_states=frozenset({"error"}),
        announcing={"content": "status", "stale": "status"},
    ),
    _contract(
        "gwflow_version_select_compare",
        method="get",
        url_name="bilbyui:gwflow_job_history",
        target="#gwflow-history-region",
        swap="outerHTML",
        kwargs="gwflow_job",
        focus=FocusExpectation("preserve"),
        async_states=frozenset({"error"}),
        announcing={"content": "status", "stale": "status"},
    ),
    _contract(
        "event_id_modal_open",
        method="get",
        url_name="bilbyui:event_id_modal",
        target="#event-id-modal-{job_id}",
        swap="outerHTML",
        kwargs="job",
        statuses=frozenset({200, 503}),
        focus=FocusExpectation("modal_search", "#event-id-search"),
        capabilities=frozenset({"loading", "announcement", "focus"}),
        async_states=frozenset({"error"}),
        full_page=False,
    ),
    _contract(
        "event_id_search",
        method="get",
        url_name="bilbyui:event_id_search",
        target="#event-id-results",
        swap="innerHTML",
        kwargs="event_search",
        statuses=frozenset({200, 503}),
        focus=FocusExpectation("preserve"),
        capabilities=frozenset({"loading", "announcement", "race"}),
        async_states=frozenset({"error"}),
        full_page=False,
    ),
    _contract(
        "job_field_edits",
        method="post",
        url_name="bilbyui:edit_job_name",
        url_names=(
            "bilbyui:edit_job_name",
            "bilbyui:edit_job_description",
            "bilbyui:edit_job_privacy",
            "bilbyui:edit_job_labels",
            "bilbyui:edit_job_event_id",
            "bilbyui:view_job_field_partial",
        ),
        target="#field-name-contract-job",
        swap="outerHTML",
        kwargs="job",
        statuses=frozenset({200, 400}),
        focus=FocusExpectation("field_control", "#field-name-contract-job"),
        capabilities=frozenset({"loading", "announcement", "focus"}),
        full_page=False,
    ),
    _contract(
        "token_create",
        method="post",
        url_name="bilbyui:api_token_create",
        target="#token-actions",
        swap="innerHTML",
        kwargs="no_kwargs",
        statuses=frozenset({200, 400}),
        focus=FocusExpectation("token_result", "#token-actions"),
        capabilities=frozenset({"loading", "announcement", "focus"}),
        async_states=frozenset({"error"}),
        full_page=False,
    ),
    _contract(
        "token_revoke",
        method="delete",
        url_name="bilbyui:api_token_revoke",
        target="#token-row-contract-token",
        swap="none",
        kwargs="token",
        statuses=frozenset({204, 502}),
        focus=FocusExpectation("next_token_or_heading", "#token-list-heading"),
        capabilities=frozenset({"loading", "announcement", "focus"}),
        full_page=False,
    ),
    _contract(
        "token_copy",
        method=None,
        target=".token-copy-status",
        swap="textContent",
        kwargs=None,
        focus=FocusExpectation("preserve"),
        capabilities=frozenset({"announcement", "clipboard"}),
        full_page=False,
    ),
)

validate_registry(REGISTRY)
CONTRACTS = REGISTRY
