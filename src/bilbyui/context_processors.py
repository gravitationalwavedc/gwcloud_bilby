from django.conf import settings


def google_analytics_id(_request):
    return {"google_analytics_id": settings.GOOGLE_ANALYTICS_ID}
