from functools import wraps

from django.http import Http404, HttpResponsePermanentRedirect
from graphql_relay.node.node import from_global_id


def parse_job_ref(job_ref):
    if job_ref.isdigit():
        return int(job_ref), False

    try:
        type_name, pk = from_global_id(job_ref)
    except Exception:
        raise Http404

    if type_name != "BilbyJobNode":
        raise Http404

    try:
        job_id = int(pk)
    except (TypeError, ValueError):
        raise Http404

    return job_id, True


def canonical_job_path(request, job_ref, job_id):
    path = request.path.replace(f"/job-results/{job_ref}/", f"/job-results/{job_id}/", 1)
    if request.GET:
        path = f"{path}?{request.GET.urlencode()}"
    return path


def resolve_job_ref_view(view_func):
    @wraps(view_func)
    def wrapper(request, job_id, *args, **kwargs):
        resolved_id, is_relay_id = parse_job_ref(job_id)
        if is_relay_id:
            return HttpResponsePermanentRedirect(canonical_job_path(request, job_id, resolved_id))
        return view_func(request, resolved_id, *args, **kwargs)

    return wrapper
