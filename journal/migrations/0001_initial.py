# Generated manually for the local journal app MVP.

import django.core.validators
from django.db import migrations, models

import journal.models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="JournalEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(unique=True)),
                ("title", models.CharField(blank=True, max_length=180)),
                ("content_delta", models.JSONField(blank=True, default=journal.models.empty_delta)),
                ("content_text", models.TextField(blank=True)),
                (
                    "mood_score",
                    models.PositiveSmallIntegerField(
                        choices=[(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")],
                        default=3,
                        validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)],
                    ),
                ),
                (
                    "energy_score",
                    models.PositiveSmallIntegerField(
                        choices=[(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")],
                        default=3,
                        validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)],
                    ),
                ),
                (
                    "productivity_score",
                    models.PositiveSmallIntegerField(
                        choices=[(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")],
                        default=3,
                        validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(5)],
                    ),
                ),
                ("tags", models.CharField(blank=True, help_text="Comma-separated tags", max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-date"],
                "indexes": [
                    models.Index(fields=["date"], name="journal_jou_date_152ca5_idx"),
                    models.Index(fields=["mood_score"], name="journal_jou_mood_sc_96ad86_idx"),
                    models.Index(fields=["energy_score", "productivity_score"], name="journal_jou_energy__54a394_idx"),
                ],
            },
        ),
    ]
