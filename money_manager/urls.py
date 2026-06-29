from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from django.views.generic import RedirectView

from . import views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", views.home, name="home"),
    path("money/", include("finance.urls")),
    path("productivity/", include("productivity.urls")),
    path("journal", RedirectView.as_view(pattern_name="journal:dashboard", permanent=False), name="journal_redirect"),
    path("journal/", include("journal.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

