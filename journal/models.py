from uuid import uuid4

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import get_valid_filename


SCORE_CHOICES = [(value, str(value)) for value in range(1, 6)]


def empty_delta():
    return {"ops": []}


def delta_plain_text(delta):
    if not isinstance(delta, dict):
        return ""
    parts = []
    for op in delta.get("ops", []):
        insert = op.get("insert", "") if isinstance(op, dict) else ""
        if isinstance(insert, str):
            parts.append(insert)
    return "".join(parts).strip()


def journal_attachment_path(instance, filename):
    safe_name = get_valid_filename(filename)
    entry_date = instance.entry.date
    return f"journal/{entry_date:%Y/%m/%d}/{uuid4().hex}-{safe_name}"


class JournalEntry(models.Model):
    date = models.DateField(unique=True)
    title = models.CharField(max_length=180, blank=True)
    content_delta = models.JSONField(default=empty_delta, blank=True)
    content_text = models.TextField(blank=True)
    mood_score = models.PositiveSmallIntegerField(
        choices=SCORE_CHOICES,
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    energy_score = models.PositiveSmallIntegerField(
        choices=SCORE_CHOICES,
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    productivity_score = models.PositiveSmallIntegerField(
        choices=SCORE_CHOICES,
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    tags = models.CharField(max_length=240, blank=True, help_text="Comma-separated tags")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["mood_score"]),
            models.Index(fields=["energy_score", "productivity_score"]),
        ]

    def __str__(self):
        return f"{self.date:%Y-%m-%d} journal"

    def save(self, *args, **kwargs):
        if not self.content_text:
            self.content_text = delta_plain_text(self.content_delta)
        super().save(*args, **kwargs)

    @property
    def preview(self):
        text = " ".join(self.content_text.split())
        if len(text) <= 180:
            return text
        return f"{text[:177]}..."

    @property
    def tag_list(self):
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]


class JournalAttachment(models.Model):
    entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="attachments")
    image = models.FileField(upload_to=journal_attachment_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.original_name or self.image.name
