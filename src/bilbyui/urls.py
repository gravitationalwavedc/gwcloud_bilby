from django.urls import path

from . import views

app_name = "bilbyui"

urlpatterns = [
    path("_health/", views._health_view, name="health"),
    path("", views.public_jobs_view, name="public_jobs"),
    path(
        "jobs/<int:job_id>/files/<str:token>/download/",
        views.file_download_redirect,
        name="file_download",
    ),
    path(
        "jobs/<int:job_id>/parameters/",
        views.view_job_parameters_partial,
        name="view_job_parameters",
    ),
    path(
        "jobs/<int:job_id>/results/",
        views.view_job_results_partial,
        name="view_job_results",
    ),
    path("jobs/<int:job_id>/", views.view_job_view, name="view_job"),
    path("jobs/", views.my_jobs_view, name="my_jobs"),
]
