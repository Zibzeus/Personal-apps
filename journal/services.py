from datetime import date, timedelta

from django.db.models import Q
from django.utils import timezone

from .models import JournalEntry


def start_of_week(day=None):
    day = day or timezone.localdate()
    return day - timedelta(days=day.weekday())


def start_of_month(day=None):
    day = day or timezone.localdate()
    return date(day.year, day.month, 1)


def score_average(entries, field):
    values = [getattr(entry, field) for entry in entries]
    if not values:
        return 0
    return round(sum(values) / len(values), 1)


def current_streak(day=None):
    day = day or timezone.localdate()
    existing = set(JournalEntry.objects.values_list("date", flat=True))
    streak = 0
    cursor = day
    while cursor in existing:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def weekly_snapshot(day=None):
    day = day or timezone.localdate()
    week_start = start_of_week(day)
    entries = list(JournalEntry.objects.filter(date__gte=week_start, date__lte=day))
    return {
        "week_start": week_start,
        "entries_this_week": len(entries),
        "avg_mood": score_average(entries, "mood_score"),
        "avg_energy": score_average(entries, "energy_score"),
        "avg_productivity": score_average(entries, "productivity_score"),
        "streak": current_streak(day),
    }


def recent_entries(limit=8):
    return JournalEntry.objects.all()[:limit]


def history_entries(query=""):
    queryset = JournalEntry.objects.all()
    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(content_text__icontains=query) | Q(tags__icontains=query))
    return queryset


def heatmap_weeks(day=None, weeks=12):
    day = day or timezone.localdate()
    end = day
    start = start_of_week(end - timedelta(days=(weeks * 7) - 1))
    entries = {entry.date: entry for entry in JournalEntry.objects.filter(date__gte=start, date__lte=end)}
    rows = []
    cursor = start
    while cursor <= end:
        week = []
        for _ in range(7):
            entry = entries.get(cursor)
            week.append(
                {
                    "date": cursor,
                    "has_entry": bool(entry),
                    "mood": entry.mood_score if entry else 0,
                    "level": entry.mood_score if entry else 0,
                    "title": entry.title if entry else "",
                }
            )
            cursor += timedelta(days=1)
        rows.append(week)
    return rows


def period_rows(day=None, weeks=8, months=6):
    day = day or timezone.localdate()
    weekly = []
    current_week = start_of_week(day)
    for offset in range(weeks - 1, -1, -1):
        week_start = current_week - timedelta(days=offset * 7)
        week_end = week_start + timedelta(days=6)
        entries = list(JournalEntry.objects.filter(date__gte=week_start, date__lte=week_end))
        weekly.append(
            {
                "label": week_start.strftime("%d %b"),
                "mood": score_average(entries, "mood_score"),
                "energy": score_average(entries, "energy_score"),
                "productivity": score_average(entries, "productivity_score"),
                "entries": len(entries),
            }
        )

    monthly = []
    month_start = start_of_month(day)
    for offset in range(months - 1, -1, -1):
        month = add_months(month_start, -offset)
        next_month = add_months(month, 1)
        entries = list(JournalEntry.objects.filter(date__gte=month, date__lt=next_month))
        monthly.append(
            {
                "label": month.strftime("%b %Y"),
                "mood": score_average(entries, "mood_score"),
                "energy": score_average(entries, "energy_score"),
                "productivity": score_average(entries, "productivity_score"),
                "entries": len(entries),
            }
        )
    return weekly, monthly


def add_months(day, delta):
    month_index = (day.year * 12 + day.month - 1) + delta
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def analytics_payload(day=None):
    day = day or timezone.localdate()
    weekly, monthly = period_rows(day)
    since = day - timedelta(days=29)
    entries = list(JournalEntry.objects.filter(date__gte=since, date__lte=day))
    radar = {
        "mood": score_average(entries, "mood_score"),
        "energy": score_average(entries, "energy_score"),
        "productivity": score_average(entries, "productivity_score"),
    }
    return {
        "weekly": weekly,
        "monthly": monthly,
        "radar": radar,
    }

