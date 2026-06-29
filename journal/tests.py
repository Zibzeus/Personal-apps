import json
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import JournalAttachment, JournalEntry
from .services import analytics_payload, heatmap_weeks, weekly_snapshot


def delta(text):
    return {"ops": [{"insert": text}]}


class JournalModelTests(TestCase):
    def test_entry_date_is_unique(self):
        today = timezone.localdate()
        JournalEntry.objects.create(date=today, content_delta=delta("First"), content_text="First")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                JournalEntry.objects.create(date=today, content_delta=delta("Second"), content_text="Second")

    def test_score_validators_reject_out_of_range_values(self):
        entry = JournalEntry(date=timezone.localdate(), mood_score=6, energy_score=3, productivity_score=3)
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_delta_plain_text_preview_and_ordering(self):
        today = timezone.localdate()
        old_entry = JournalEntry.objects.create(date=today - timedelta(days=1), content_delta=delta("Old day"))
        new_entry = JournalEntry.objects.create(date=today, content_delta=delta("New day with useful reflection"))
        old_entry.refresh_from_db()
        new_entry.refresh_from_db()
        self.assertEqual(old_entry.content_text, "Old day")
        self.assertEqual(new_entry.preview, "New day with useful reflection")
        self.assertEqual(list(JournalEntry.objects.all()), [new_entry, old_entry])


class JournalViewTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_dir)
        self.media_override.enable()
        self.user = User.objects.create_user(username="tester", password="secret")

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def post_payload(self, day=None, text="Today felt steady"):
        day = day or timezone.localdate()
        return {
            "date": day.isoformat(),
            "title": "Daily note",
            "mood_score": "4",
            "energy_score": "3",
            "productivity_score": "5",
            "tags": "work, focus",
            "content_delta_raw": json.dumps(delta(text)),
            "content_text": text,
        }

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("journal:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_dashboard_is_mounted_under_journal(self):
        self.assertEqual(reverse("journal:dashboard"), "/journal/")

    def test_dashboard_without_trailing_slash_redirects_after_login(self):
        self.client.force_login(self.user)
        response = self.client.get("/journal")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("journal:dashboard"))

    def test_dashboard_loads_and_saves_today_entry(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("journal:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mood Check-In")

        response = self.client.post(reverse("journal:dashboard"), self.post_payload())
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get()
        self.assertEqual(entry.date, timezone.localdate())
        self.assertEqual(entry.mood_score, 4)
        self.assertEqual(entry.content_delta, delta("Today felt steady"))
        self.assertEqual(entry.content_text, "Today felt steady")

    def test_entry_page_reads_without_editor_and_edit_page_updates_existing_date(self):
        self.client.force_login(self.user)
        day = timezone.localdate() - timedelta(days=2)
        JournalEntry.objects.create(date=day, title="Before", content_delta=delta("Before"), content_text="Before")
        response = self.client.get(reverse("journal:entry", args=[day.isoformat()]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Read the entry as a normal journal page")
        self.assertContains(response, "Edit Entry")
        self.assertNotContains(response, "journal-editor-shell")

        response = self.client.post(reverse("journal:entry_edit", args=[day.isoformat()]), self.post_payload(day=day, text="Updated"))
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get(date=day)
        self.assertEqual(entry.content_text, "Updated")
        self.assertEqual(entry.productivity_score, 5)

    def test_edit_page_uploads_image_attachment(self):
        self.client.force_login(self.user)
        day = timezone.localdate()
        image = SimpleUploadedFile("mood.png", b"fake-image-bytes", content_type="image/png")
        payload = self.post_payload(day=day, text="Photo day")
        payload["images"] = [image]

        response = self.client.post(reverse("journal:entry_edit", args=[day.isoformat()]), payload)
        self.assertEqual(response.status_code, 302)
        entry = JournalEntry.objects.get(date=day)
        attachment = JournalAttachment.objects.get(entry=entry)
        self.assertEqual(attachment.original_name, "mood.png")
        self.assertEqual(attachment.content_type, "image/png")

        response = self.client.get(reverse("journal:entry", args=[day.isoformat()]))
        self.assertContains(response, "mood.png")

    def test_history_and_analytics_render_after_login(self):
        self.client.force_login(self.user)
        JournalEntry.objects.create(
            date=timezone.localdate(),
            title="Grounded day",
            content_delta=delta("Some useful detail"),
            content_text="Some useful detail",
            tags="health",
            mood_score=5,
            energy_score=4,
            productivity_score=3,
        )
        response = self.client.get(reverse("journal:history"), {"q": "health"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grounded day")

        response = self.client.get(reverse("journal:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mood Heatmap")
        self.assertContains(response, "journal-chart-data")

    def test_service_summaries_are_json_ready(self):
        JournalEntry.objects.create(
            date=timezone.localdate(),
            content_delta=delta("Signal"),
            content_text="Signal",
            mood_score=4,
            energy_score=2,
            productivity_score=5,
        )
        snapshot = weekly_snapshot()
        self.assertEqual(snapshot["entries_this_week"], 1)
        self.assertEqual(snapshot["avg_productivity"], 5)
        self.assertTrue(heatmap_weeks())
        payload = analytics_payload()
        self.assertEqual(payload["radar"]["mood"], 4)
