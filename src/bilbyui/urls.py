from django.urls import path

from . import views

app_name = "bilbyui"

urlpatterns = [
    path("_health/", views._health_view, name="health"),
    path("", views.public_jobs_view, name="public_jobs"),
    path("job/<int:job_id>/", views.view_job_stub, name="view_job"),
]
