from django.urls import path

from . import views


app_name = "productivity"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("board/", views.board, name="board"),
    path("tasks/<int:pk>/", views.task_action, name="task_action"),
    path("goals/", views.goals, name="goals"),
    path("reviews/weekly/", views.weekly_review, name="weekly_review"),
    path("reviews/monthly/", views.monthly_review, name="monthly_review"),
]
