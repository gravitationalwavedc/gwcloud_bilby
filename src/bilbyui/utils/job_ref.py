from functools import wraps

from django.http import Http404, HttpResponsePermanentRedirect
from django.urls import resolve, reverse
from graphql_relay.node.node import from_global_id


def parse_job_ref(job_ref):
    """
    Resolves a job reference into a numeric job id.

    :param job_ref: A job reference, either a raw numeric id string or a Relay global id
    :return: A tuple of (job_id, is_relay_id) where job_id is the integer job id and
        is_relay_id is True when job_ref was a Relay global id
    """
    if job_ref.isdigit():
        return int(job_ref), False

    try:
        type_name, pk = from_global_id(job_ref)
    except Exception as err:
        raise Http404 from err

    if type_name != "BilbyJobNode":
        raise Http404

    try:
        job_id = int(pk)
    except (TypeError, ValueError) as err:
        raise Http404 from err

    return job_id, True


def canonical_job_path(request, resolved_job_id):
    """
    Builds the canonical URL path for a resolved job id.

    :param request: The current HttpRequest whose path and query string are used as a template
    :param resolved_job_id: The integer job id to substitute into the resolved view
    :return: The canonical URL path (including any query string) for the resolved job id
    """
    match = resolve(request.path)
    kwargs = {**match.kwargs, "job_id": resolved_job_id}
    path = reverse(match.view_name, kwargs=kwargs)
    if request.GET:
        path = f"{path}?{request.GET.urlencode()}"
    return path


def resolve_job_ref_view(view_func):
    """
    Decorator that resolves a job reference before dispatching to a view.

    :param view_func: The view function to wrap
    :return: A wrapped view that resolves the job reference, redirecting to the
        canonical path when a Relay global id is supplied, otherwise calling the
        wrapped view with the resolved integer job id
    """

    @wraps(view_func)
    def wrapper(request, job_id, *args, **kwargs):
        resolved_id, is_relay_id = parse_job_ref(job_id)
        if is_relay_id:
            return HttpResponsePermanentRedirect(canonical_job_path(request, resolved_id))
        return view_func(request, resolved_id, *args, **kwargs)

    return wrapper
