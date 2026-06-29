from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import Goal, MonthlyReview, Priority, Task, WeeklyReview


ACTIVE_TASK_STATUSES = [
    Task.Status.INBOX,
    Task.Status.NEXT,
    Task.Status.DOING,
    Task.Status.WAITING,
]

BOARD_STATUSES = [
    Task.Status.INBOX,
    Task.Status.NEXT,
    Task.Status.DOING,
    Task.Status.WAITING,
    Task.Status.DONE,
]


@dataclass
class ProductivityBotResponse:
    message: str


def start_of_week(day=None):
    day = day or timezone.localdate()
    return day - timedelta(days=day.weekday())


def start_of_month(day=None):
    day = day or timezone.localdate()
    return date(day.year, day.month, 1)


def review_snapshot(day=None):
    day = day or timezone.localdate()
    active = Task.objects.filter(status__in=ACTIVE_TASK_STATUSES)
    return {
        "date": day.isoformat(),
        "active_goals": Goal.objects.filter(status=Goal.Status.ACTIVE).count(),
        "active_tasks": active.count(),
        "overdue_tasks": active.filter(due_date__lt=day).count(),
        "completed_this_week": Task.objects.filter(
            status=Task.Status.DONE,
            completed_at__date__gte=start_of_week(day),
            completed_at__date__lte=day,
        ).count(),
        "tasks_by_status": dict(Task.objects.values_list("status").annotate(total=Count("id"))),
    }


def task_order(queryset):
    return queryset.order_by("priority", "due_date", "planned_date", "-created_at")


def create_task(
    title,
    *,
    notes="",
    status=Task.Status.INBOX,
    priority=Priority.MEDIUM,
    energy=Task.Energy.MEDIUM,
    due_date=None,
    planned_date=None,
    goal=None,
    project=None,
    source=Task.Source.WEB,
    source_user_id="",
):
    return Task.objects.create(
        title=title.strip(),
        notes=notes.strip(),
        status=status,
        priority=priority,
        energy=energy,
        due_date=due_date,
        planned_date=planned_date,
        goal=goal,
        project=project,
        source=source,
        source_user_id=source_user_id,
    )


def create_goal(title, *, source_note=""):
    note = source_note.strip()
    return Goal.objects.create(title=title.strip(), progress_note=note)


def complete_task(task_id):
    task = Task.objects.filter(pk=task_id).first()
    if not task:
        return None
    task.status = Task.Status.DONE
    task.save(update_fields=["status", "completed_at", "updated_at"])
    return task


def daily_dashboard(selected_energy=Task.Energy.MEDIUM, day=None):
    day = day or timezone.localdate()
    if selected_energy not in Task.Energy.values:
        selected_energy = Task.Energy.MEDIUM
    active = Task.objects.select_related("goal", "project").filter(status__in=ACTIVE_TASK_STATUSES)
    overdue = task_order(active.filter(due_date__lt=day))
    today = task_order(active.filter(planned_date=day))
    suggested = []
    seen = set()
    for group in [
        overdue,
        today,
        task_order(active.filter(priority=Priority.HIGH, energy=selected_energy)),
    ]:
        for task in group:
            if task.id not in seen:
                suggested.append(task)
                seen.add(task.id)
            if len(suggested) >= 8:
                break
        if len(suggested) >= 8:
            break
    return {
        "day": day,
        "selected_energy": selected_energy,
        "overdue": overdue,
        "today": today,
        "suggested": suggested,
        "active_count": active.count(),
        "done_this_week": Task.objects.filter(
            status=Task.Status.DONE,
            completed_at__date__gte=start_of_week(day),
            completed_at__date__lte=day,
        ).count(),
    }


def board_columns():
    columns = []
    for status in BOARD_STATUSES:
        limit = 25 if status == Task.Status.DONE else 100
        tasks = (
            Task.objects.select_related("goal", "project")
            .filter(status=status)
            .order_by("priority", "planned_date", "due_date", "-created_at")[:limit]
        )
        columns.append({"status": status, "label": Task.Status(status).label, "tasks": tasks})
    return columns


def goals_overview():
    return (
        Goal.objects.prefetch_related("projects", "tasks")
        .filter(status__in=[Goal.Status.ACTIVE, Goal.Status.PAUSED])
        .order_by("status", "priority", "target_date", "title")
    )


def latest_weekly_focus():
    review = WeeklyReview.objects.order_by("-week_start").first()
    if not review or not review.next_focus.strip():
        return ""
    return review.next_focus.strip()


def save_weekly_review(cleaned_data):
    week_start = start_of_week(cleaned_data["week_start"])
    review, _ = WeeklyReview.objects.update_or_create(
        week_start=week_start,
        defaults={
            "wins": cleaned_data.get("wins", ""),
            "blockers": cleaned_data.get("blockers", ""),
            "next_focus": cleaned_data.get("next_focus", ""),
            "notes": cleaned_data.get("notes", ""),
            "snapshot": review_snapshot(week_start),
        },
    )
    return review


def save_monthly_review(cleaned_data):
    month = start_of_month(cleaned_data["month"])
    review, _ = MonthlyReview.objects.update_or_create(
        month=month,
        defaults={
            "wins": cleaned_data.get("wins", ""),
            "blockers": cleaned_data.get("blockers", ""),
            "next_focus": cleaned_data.get("next_focus", ""),
            "notes": cleaned_data.get("notes", ""),
            "snapshot": review_snapshot(month),
        },
    )
    return review


def today_text_summary(day=None):
    data = daily_dashboard(day=day)
    rows = list(data["overdue"][:5]) + [task for task in data["today"][:5] if task not in data["overdue"][:5]]
    if not rows:
        return "Tidak ada task overdue atau planned hari ini."
    lines = ["Task hari ini:"]
    for task in rows[:8]:
        marker = "overdue" if task.due_date and task.due_date < data["day"] else task.get_status_display()
        lines.append(f"#{task.id} [{marker}] P{task.priority} {task.title}")
    return "\n".join(lines)


def handle_productivity_command(text, *, source_user_id=""):
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("/"):
        raw = raw[1:]
    command, _, rest = raw.partition(" ")
    command = command.split("@", 1)[0].lower()
    rest = rest.strip()

    if command == "task":
        if not rest:
            return ProductivityBotResponse("Ketik: task <judul task>")
        task = create_task(rest, source=Task.Source.TELEGRAM, source_user_id=source_user_id)
        return ProductivityBotResponse(f"Task #{task.id} masuk Inbox: {task.title}")

    if command == "goal":
        if not rest:
            return ProductivityBotResponse("Ketik: goal <judul goal>")
        goal = create_goal(rest, source_note="Created from Telegram.")
        return ProductivityBotResponse(f"Goal #{goal.id} dibuat: {goal.title}")

    if command == "today":
        return ProductivityBotResponse(today_text_summary())

    if command == "done":
        if not rest or not rest.split()[0].isdigit():
            return ProductivityBotResponse("Ketik: done <id task>")
        task = complete_task(int(rest.split()[0]))
        if not task:
            return ProductivityBotResponse("Task tidak ditemukan.")
        return ProductivityBotResponse(f"Done: #{task.id} {task.title}")

    if command == "review":
        focus = latest_weekly_focus()
        if not focus:
            return ProductivityBotResponse("Belum ada weekly focus. Isi review mingguan di dashboard.")
        return ProductivityBotResponse(f"Weekly focus:\n{focus}")

    return None
