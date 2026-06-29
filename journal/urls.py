from django.urls import path

from . import views


app_name = "journal"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("entry/<str:entry_date>/", views.entry_detail, name="entry"),
    path("entry/<str:entry_date>/edit/", views.entry_edit, name="entry_edit"),
    path("history/", views.history, name="history"),
    path("analytics/", views.analytics, name="analytics"),
]
