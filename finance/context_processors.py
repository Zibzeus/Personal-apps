from django.conf import settings


def app_settings(request):
    return {
        "DEFAULT_CURRENCY": settings.DEFAULT_CURRENCY,
        "SAVING_RATE_TARGET": settings.SAVING_RATE_TARGET,
    }

