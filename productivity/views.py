from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import GoalForm, MonthlyReviewForm, ProjectForm, QuickTaskForm, TaskForm, WeeklyReviewForm
from .models import Goal, MonthlyReview, Project, Task, WeeklyReview
from .services import (
    board_columns,
    daily_dashboard,
    goals_overview,
    save_monthly_review,
    save_weekly_review,
    start_of_month,
    start_of_week,
)


def dashboard(request):
    selected_energy = request.GET.get("energy", Task.Energy.MEDIUM)
    if selected_energy not in Task.Energy.values:
        selected_energy = Task.Energy.MEDIUM
    if request.method == "POST":
        form = QuickTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.status = Task.Status.INBOX
            task.source = Task.Source.WEB
            task.save()
            messages.success(request, f"Task captured: {task.title}")
            return redirect("productivity:dashboard")
    else:
        form = QuickTaskForm(initial={"planned_date": timezone.localdate(), "energy": selected_energy})
    data = daily_dashboard(selected_energy=selected_energy)
    return render(
        request,
        "productivity/dashboard.html",
        {
            **data,
            "form": form,
            "energy_choices": Task.Energy.choices,
            "recent_done": Task.objects.filter(status=Task.Status.DONE).order_by("-completed_at")[:8],
            "active_goals": Goal.objects.filter(status=Goal.Status.ACTIVE).order_by("priority", "target_date")[:6],
        },
    )


def board(request):
    if request.method == "POST":
        form = QuickTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.status = Task.Status.INBOX
            task.source = Task.Source.WEB
            task.save()
            messages.success(request, f"Task captured: {task.title}")
            return redirect("productivity:board")
    else:
        form = QuickTaskForm(initial={"planned_date": timezone.localdate()})
    return render(
        request,
        "productivity/board.html",
        {
            "columns": board_columns(),
            "form": form,
            "status_choices": Task.Status.choices,
        },
    )


def task_action(request, pk):
    if request.method != "POST":
        return redirect("productivity:dashboard")
    task = get_object_or_404(Task, pk=pk)
    status = request.POST.get("status")
    if status in Task.Status.values:
        task.status = status
        task.save(update_fields=["status", "completed_at", "updated_at"])
        messages.success(request, f"Task moved to {task.get_status_display()}.")
    else:
        messages.error(request, "Invalid task status.")
    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or "productivity:dashboard")


def goals(request):
    goal_form = GoalForm()
    project_form = ProjectForm()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_goal":
            goal_form = GoalForm(request.POST)
            if goal_form.is_valid():
                goal_form.save()
                messages.success(request, "Goal saved.")
                return redirect("productivity:goals")
        elif action == "save_project":
            project_form = ProjectForm(request.POST)
            if project_form.is_valid():
                project_form.save()
                messages.success(request, "Project saved.")
                return redirect("productivity:goals")
    return render(
        request,
        "productivity/goals.html",
        {
            "goal_form": goal_form,
            "project_form": project_form,
            "goals": goals_overview(),
            "standalone_projects": Project.objects.filter(goal__isnull=True).exclude(status=Project.Status.ARCHIVED),
        },
    )


def weekly_review(request):
    current_week = start_of_week()
    form = WeeklyReviewForm()
    if request.method == "POST":
        form = WeeklyReviewForm(request.POST)
        if form.is_valid():
            save_weekly_review(form.cleaned_data)
            messages.success(request, "Weekly review saved.")
            return redirect("productivity:weekly_review")
    latest = WeeklyReview.objects.filter(week_start=current_week).first()
    if request.method == "GET" and latest:
        form = WeeklyReviewForm(instance=latest)
    return render(
        request,
        "productivity/review.html",
        {
            "title": "Weekly Review",
            "eyebrow": "Review",
            "form": form,
            "reviews": WeeklyReview.objects.all()[:12],
            "date_field": "week_start",
        },
    )


def monthly_review(request):
    current_month = start_of_month()
    form = MonthlyReviewForm()
    if request.method == "POST":
        form = MonthlyReviewForm(request.POST)
        if form.is_valid():
            save_monthly_review(form.cleaned_data)
            messages.success(request, "Monthly review saved.")
            return redirect("productivity:monthly_review")
    latest = MonthlyReview.objects.filter(month=current_month).first()
    if request.method == "GET" and latest:
        form = MonthlyReviewForm(instance=latest)
    return render(
        request,
        "productivity/review.html",
        {
            "title": "Monthly Review",
            "eyebrow": "Review",
            "form": form,
            "reviews": MonthlyReview.objects.all()[:12],
            "date_field": "month",
        },
    )
