from django.urls import path

from . import views

app_name = "bilbyui"

urlpatterns = [
    path("_health/", views._health_view, name="health"),  # noqa: SLF001
    path("", views.public_jobs_view, name="public_jobs"),
    path(
        "job-results/<str:job_id>/files/<str:token>/download/",
        views.file_download_redirect,
        name="file_download",
    ),
    path(
        "job-results/<str:job_id>/parameters/",
        views.view_job_parameters_partial,
        name="view_job_parameters",
    ),
    path(
        "job-results/<str:job_id>/results/",
        views.view_job_results_partial,
        name="view_job_results",
    ),
    path(
        "job-results/<str:job_id>/field/<str:field>/",
        views.view_job_field_partial,
        name="view_job_field_partial",
    ),
    path("job-results/<str:job_id>/edit/name/", views.edit_job_name, name="edit_job_name"),
    path(
        "job-results/<str:job_id>/edit/description/",
        views.edit_job_description,
        name="edit_job_description",
    ),
    path(
        "job-results/<str:job_id>/edit/privacy/",
        views.edit_job_privacy,
        name="edit_job_privacy",
    ),
    path(
        "job-results/<str:job_id>/edit/labels/",
        views.edit_job_labels,
        name="edit_job_labels",
    ),
    path("event-ids/", views.event_id_search, name="event_id_search"),
    path(
        "job-results/<str:job_id>/event-id-modal/",
        views.event_id_modal,
        name="event_id_modal",
    ),
    path(
        "job-results/<str:job_id>/edit/event-id/",
        views.edit_job_event_id,
        name="edit_job_event_id",
    ),
    path("job-results/<str:job_id>/", views.view_job_view, name="view_job"),
    path("job-list/", views.my_jobs_view, name="my_jobs"),
    path("api-token/", views.api_token_view, name="api_tokens"),
    path("api-token/create/", views.api_token_create, name="api_token_create"),
    path(
        "api-token/<int:token_id>/revoke/",
        views.api_token_revoke,
        name="api_token_revoke",
    ),
    path("<path:path>", views.not_found_view, name="not_found"),
]
