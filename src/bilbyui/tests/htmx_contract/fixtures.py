"""Deterministic fixture and external-boundary support for contract tests."""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from unittest.mock import patch

import django
from django.apps import apps
from django.urls import reverse

if not apps.ready:
    django.setup()

from bilbyui.tests.testcases import BilbyTestCase  # noqa: E402


@dataclass(frozen=True)
class RequestFixture:
    kwargs: dict[str, object]
    query: dict[str, str]
    data: dict[str, str]


def no_kwargs(_test_case: BilbyTestCase) -> RequestFixture:
    return RequestFixture({}, {}, {})


def gwflow_job(_test_case: BilbyTestCase) -> RequestFixture:
    return RequestFixture({"sname": "S240101a"}, {}, {})


def gwflow_version(_test_case: BilbyTestCase) -> RequestFixture:
    return RequestFixture({"sname": "S240101a", "history_id": "contract-history"}, {}, {})


def job(_test_case: BilbyTestCase) -> RequestFixture:
    return RequestFixture({"job_id": "contract-job"}, {}, {"name": "Contract job"})


def event_search(_test_case: BilbyTestCase) -> RequestFixture:
    return RequestFixture({}, {"query": "S240101a"}, {})


def token(_test_case: BilbyTestCase) -> RequestFixture:
    return RequestFixture({"token_id": 1}, {}, {})


FIXTURE_FACTORIES = {
    "no_kwargs": no_kwargs,
    "gwflow_job": gwflow_job,
    "gwflow_version": gwflow_version,
    "job": job,
    "event_search": event_search,
    "token": token,
}


def resolve_fixture(test_case: BilbyTestCase, key: str | None) -> RequestFixture:
    if key is None:
        return no_kwargs(test_case)
    try:
        factory = FIXTURE_FACTORIES[key]
    except KeyError as error:
        raise KeyError(
            f"Unknown HTMX contract fixture {key!r}; available: "
            f"{', '.join(sorted(FIXTURE_FACTORIES))}"
        ) from error
    return factory(test_case)


def fixture_url(test_case: BilbyTestCase, contract) -> str:
    if contract.url_name is None:
        raise ValueError(f"{contract.name}: client-only contract has no URL")
    fixture = resolve_fixture(test_case, contract.url_kwargs_fixture)
    return reverse(contract.url_name, kwargs=fixture.kwargs)


@contextmanager
def isolated_external_services():
    """Make accidental network-backed contract setup fail deterministically."""
    blocked = RuntimeError("live external call blocked by HTMX contract fixtures")
    with ExitStack() as stack:
        stack.enter_context(
            patch("bilbyui.services.gwflow.get_es_client", side_effect=blocked)
        )
        stack.enter_context(patch("bilbyui.views.get_superevent", side_effect=blocked))
        stack.enter_context(patch("bilbyui.views.get_version", side_effect=blocked))
        yield


class HTMXContractTestCase(BilbyTestCase):
    """BilbyTestCase base with authenticated local user and blocked externals."""

    def setUp(self):
        super().setUp()
        self.authenticate()
        self._external_guard = isolated_external_services()
        self._external_guard.__enter__()
        self.addCleanup(self._external_guard.__exit__, None, None, None)
