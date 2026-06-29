from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Priority(models.IntegerChoices):
    HIGH = 1, "High"
    MEDIUM = 2, "Medium"
    LOW = 3, "Low"


class Goal(models.Model):
    class Area(models.TextChoices):
        WORK = "work", "Work"
        HEALTH = "health", "Health"
        LEARNING = "learning", "Learning"
        RELATIONSHIP = "relationship", "Relationship"
        PERSONAL = "personal", "Personal"
        BUSINESS = "business", "Business"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        DONE = "done", "Done"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=160)
    area = models.CharField(max_length=30, choices=Area.choices, default=Area.PERSONAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices,
        default=Priority.MEDIUM,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
    )
    target_date = models.DateField(null=True, blank=True)
    progress_note = models.TextField(blank=True)
    target_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    current_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "priority", "target_date", "title"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["target_date"]),
        ]

    def __str__(self):
        return self.title

    @property
    def progress_percent(self):
        if not self.target_value or self.target_value <= 0:
            return Decimal("0")
        current = self.current_value or Decimal("0")
        percent = (current / self.target_value) * Decimal("100")
        return min(Decimal("100"), max(Decimal("0"), percent.quantize(Decimal("0.01"))))


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WAITING = "waiting", "Waiting"
        DONE = "done", "Done"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=160)
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True, related_name="projects")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices,
        default=Priority.MEDIUM,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
    )
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "priority", "due_date", "title"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["due_date"]),
        ]

    def __str__(self):
        return self.title


class TaskQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(status__in=[Task.Status.DONE, Task.Status.CANCELED])


class Task(models.Model):
    class Status(models.TextChoices):
        INBOX = "inbox", "Inbox"
        NEXT = "next", "Next"
        DOING = "doing", "Doing"
        WAITING = "waiting", "Waiting"
        DONE = "done", "Done"
        CANCELED = "canceled", "Canceled"

    class Energy(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Source(models.TextChoices):
        WEB = "web", "Web"
        TELEGRAM = "telegram", "Telegram"
        SYSTEM = "system", "System"

    title = models.CharField(max_length=180)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INBOX)
    priority = models.PositiveSmallIntegerField(
        choices=Priority.choices,
        default=Priority.MEDIUM,
        validators=[MinValueValidator(1), MaxValueValidator(3)],
    )
    energy = models.CharField(max_length=20, choices=Energy.choices, default=Energy.MEDIUM)
    due_date = models.DateField(null=True, blank=True)
    planned_date = models.DateField(null=True, blank=True)
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.WEB)
    source_user_id = models.CharField(max_length=80, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TaskQuerySet.as_manager()

    class Meta:
        ordering = ["status", "priority", "planned_date", "due_date", "-created_at"]
        indexes = [
            models.Index(fields=["status", "priority"]),
            models.Index(fields=["planned_date", "status"]),
            models.Index(fields=["due_date", "status"]),
            models.Index(fields=["source", "source_user_id"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.status == self.Status.DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != self.Status.DONE:
            self.completed_at = None
        super().save(*args, **kwargs)


class WeeklyReview(models.Model):
    week_start = models.DateField(unique=True)
    wins = models.TextField(blank=True)
    blockers = models.TextField(blank=True)
    next_focus = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-week_start"]

    def __str__(self):
        return f"Week of {self.week_start:%Y-%m-%d}"


class MonthlyReview(models.Model):
    month = models.DateField(unique=True)
    wins = models.TextField(blank=True)
    blockers = models.TextField(blank=True)
    next_focus = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month"]

    def __str__(self):
        return f"{self.month:%Y-%m} review"
