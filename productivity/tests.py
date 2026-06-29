from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Goal, MonthlyReview, Priority, Task, WeeklyReview
from .services import (
    daily_dashboard,
    handle_productivity_command,
    review_snapshot,
    save_monthly_review,
    save_weekly_review,
    start_of_month,
    start_of_week,
)


class ProductivityModelTests(TestCase):
    def test_goal_progress_percent_is_clamped(self):
        goal = Goal.objects.create(
            title="Read 12 books",
            target_value=Decimal("12"),
            current_value=Decimal("15"),
            unit="books",
        )
        self.assertEqual(goal.progress_percent, Decimal("100"))

    def test_task_completion_timestamp_tracks_done_status(self):
        task = Task.objects.create(title="Write plan")
        self.assertIsNone(task.completed_at)

        task.status = Task.Status.DONE
        task.save()
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)

        task.status = Task.Status.NEXT
        task.save()
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)

    def test_daily_dashboard_orders_overdue_today_then_energy_match(self):
        today = timezone.localdate()
        high_energy = Task.objects.create(
            title="Deep analysis",
            priority=Priority.HIGH,
            energy=Task.Energy.HIGH,
        )
        today_task = Task.objects.create(
            title="Today admin",
            priority=Priority.MEDIUM,
            planned_date=today,
        )
        overdue = Task.objects.create(
            title="Late invoice",
            priority=Priority.LOW,
            due_date=today - timedelta(days=1),
        )
        data = daily_dashboard(selected_energy=Task.Energy.HIGH, day=today)
        self.assertEqual(data["suggested"][:3], [overdue, today_task, high_energy])

    def test_reviews_store_snapshot(self):
        Task.objects.create(title="Inbox item")
        weekly = save_weekly_review(
            {
                "week_start": timezone.localdate(),
                "wins": "Shipped",
                "blockers": "",
                "next_focus": "Deep work",
                "notes": "",
            }
        )
        monthly = save_monthly_review(
            {
                "month": timezone.localdate(),
                "wins": "Consistent",
                "blockers": "",
                "next_focus": "Finish MVP",
                "notes": "",
            }
        )
        self.assertEqual(weekly.week_start, start_of_week())
        self.assertEqual(monthly.month, start_of_month())
        self.assertEqual(weekly.snapshot["active_tasks"], 1)
        self.assertEqual(monthly.snapshot["active_goals"], 0)
        self.assertEqual(review_snapshot()["active_tasks"], 1)


class ProductivityViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="secret")

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("productivity:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_dashboard_is_mounted_under_productivity(self):
        self.assertEqual(reverse("productivity:dashboard"), "/productivity/")

    def test_dashboard_loads_after_login_and_quick_adds_task(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("productivity:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Execution Dashboard")

        response = self.client.post(
            reverse("productivity:dashboard"),
            {
                "title": "Follow up proposal",
                "priority": Priority.HIGH,
                "energy": Task.Energy.LOW,
                "planned_date": timezone.localdate().isoformat(),
                "due_date": "",
                "goal": "",
                "project": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title="Follow up proposal")
        self.assertEqual(task.status, Task.Status.INBOX)
        self.assertEqual(task.source, Task.Source.WEB)

    def test_task_status_transition_and_board_filtering(self):
        self.client.force_login(self.user)
        task = Task.objects.create(title="Prepare deck")
        response = self.client.post(
            reverse("productivity:task_action", args=[task.id]),
            {"status": Task.Status.DOING, "next": reverse("productivity:board")},
        )
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DOING)

        response = self.client.get(reverse("productivity:board"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prepare deck")
        self.assertContains(response, "Doing")

    def test_goals_and_reviews_pages(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("productivity:goals"),
            {
                "action": "save_goal",
                "title": "Ship personal ops",
                "area": Goal.Area.WORK,
                "status": Goal.Status.ACTIVE,
                "priority": Priority.HIGH,
                "target_date": "",
                "target_value": "10",
                "current_value": "2",
                "unit": "milestones",
                "progress_note": "MVP first.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Goal.objects.count(), 1)

        response = self.client.post(
            reverse("productivity:weekly_review"),
            {
                "week_start": timezone.localdate().isoformat(),
                "wins": "Captured tasks",
                "blockers": "",
                "next_focus": "Finish manager",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WeeklyReview.objects.count(), 1)
        response = self.client.post(
            reverse("productivity:weekly_review"),
            {
                "week_start": timezone.localdate().isoformat(),
                "wins": "Updated wins",
                "blockers": "",
                "next_focus": "Refine manager",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WeeklyReview.objects.count(), 1)
        self.assertEqual(WeeklyReview.objects.get().next_focus, "Refine manager")

        response = self.client.post(
            reverse("productivity:monthly_review"),
            {
                "month": timezone.localdate().isoformat(),
                "wins": "Momentum",
                "blockers": "",
                "next_focus": "Review trend",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MonthlyReview.objects.count(), 1)


class ProductivityTelegramTests(TestCase):
    def test_task_command_creates_inbox_task(self):
        result = handle_productivity_command("task follow up vendor", source_user_id="42")
        task = Task.objects.get()
        self.assertIn(f"Task #{task.id}", result.message)
        self.assertEqual(task.status, Task.Status.INBOX)
        self.assertEqual(task.source, Task.Source.TELEGRAM)
        self.assertEqual(task.source_user_id, "42")

    def test_goal_command_creates_lightweight_goal(self):
        result = handle_productivity_command("/goal learn django testing")
        goal = Goal.objects.get()
        self.assertIn(f"Goal #{goal.id}", result.message)
        self.assertEqual(goal.title, "learn django testing")

    def test_today_and_done_commands(self):
        task = Task.objects.create(title="Pay bill", planned_date=timezone.localdate())
        today = handle_productivity_command("today")
        self.assertIn(f"#{task.id}", today.message)

        done = handle_productivity_command(f"done {task.id}")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)
        self.assertIn("Done", done.message)

    def test_review_and_invalid_commands(self):
        empty_review = handle_productivity_command("review")
        self.assertIn("Belum ada weekly focus", empty_review.message)

        WeeklyReview.objects.create(week_start=start_of_week(), next_focus="Close the weekly plan")
        review = handle_productivity_command("/review")
        self.assertIn("Close the weekly plan", review.message)

        invalid_done = handle_productivity_command("done nope")
        self.assertIn("done <id task>", invalid_done.message)
        self.assertIsNone(handle_productivity_command("makan 35000 bca"))
