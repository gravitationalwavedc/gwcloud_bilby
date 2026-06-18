from django.urls import path

from . import views

app_name = "bilbyui"

urlpatterns = [
    path("_health/", views._health_view, name="health"),
]
