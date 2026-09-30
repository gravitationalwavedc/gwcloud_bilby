from django.apps import AppConfig


class BilbyUiConfig(AppConfig):
    name = "bilbyui"

    def ready(self):
        import bilbyui.checks  # noqa: F401
