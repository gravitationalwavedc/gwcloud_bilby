"""Deterministic fixture support for contract tests."""

from dataclasses import dataclass

import django
from django.apps import apps
from django.urls import reverse

if not apps.ready:
    django.setup()

from bilbyui.models import BilbyJob, GWFlowJob  # noqa: E402
from bilbyui.services.api_tokens import create_token  # noqa: E402
from bilbyui.tests.test_utils import create_test_ini_string  # noqa: E402
from bilbyui.tests.testcases import BilbyTestCase  # noqa: E402


@dataclass(frozen=True)
class RequestFixture:
    kwargs: dict[str, object]
    query: dict[str, str]
    data: dict[str, str]


def no_kwargs(_test_case: BilbyTestCase) -> RequestFixture:
    return RequestFixture({}, {}, {})


def gwflow_job(test_case: BilbyTestCase) -> RequestFixture:
    sname = "S240101a"
    GWFlowJob.objects.get_or_create(
        sname=sname,
        defaults={
            "user": test_case.user,
            "libraries": ["cbc-workflow-o4a"],
            "schema_version": "v3",
            "ligo_only": False,
        },
    )
    return RequestFixture({"sname": sname}, {}, {})


def job(test_case: BilbyTestCase) -> RequestFixture:
    instance, _ = BilbyJob.objects.get_or_create(
        user=test_case.user,
        name="Contract job",
        defaults={
            "description": "HTMX contract fixture",
            "job_controller_id": 60001,
            "private": False,
            "ini_string": create_test_ini_string(
                {"detectors": "[\'H1\']", "label": "contract_job"}
            ),
        },
    )
    return RequestFixture({"job_id": instance.id}, {}, {"name": "Contract job"})


def event_search(test_case: BilbyTestCase) -> RequestFixture:
    fixture = job(test_case)
    return RequestFixture(
        {},
        {"q": "S240101a", "job_id": str(fixture.kwargs["job_id"])},
        {},
    )


def token(test_case: BilbyTestCase) -> RequestFixture:
    instance = create_token(test_case.user, "contract-token")
    return RequestFixture({"token_id": instance.id}, {}, {})


FIXTURE_FACTORIES = {
    "no_kwargs": no_kwargs,
    "gwflow_job": gwflow_job,
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

