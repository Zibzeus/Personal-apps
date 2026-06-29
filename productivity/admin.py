from django.contrib import admin

from .models import Goal, MonthlyReview, Project, Task, WeeklyReview


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ["title", "area", "status", "priority", "target_date", "updated_at"]
    list_filter = ["area", "status", "priority"]
    search_fields = ["title", "progress_note"]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["title", "goal", "status", "priority", "due_date", "updated_at"]
    list_filter = ["status", "priority"]
    search_fields = ["title", "notes"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "status", "priority", "energy", "planned_date", "due_date", "source"]
    list_filter = ["status", "priority", "energy", "source"]
    search_fields = ["title", "notes"]


@admin.register(WeeklyReview)
class WeeklyReviewAdmin(admin.ModelAdmin):
    list_display = ["week_start", "updated_at"]


@admin.register(MonthlyReview)
class MonthlyReviewAdmin(admin.ModelAdmin):
    list_display = ["month", "updated_at"]
