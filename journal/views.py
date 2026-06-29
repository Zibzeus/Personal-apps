import json
from datetime import date

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import JournalEntryForm
from .models import JournalAttachment, JournalEntry, empty_delta
from .services import analytics_payload, heatmap_weeks, history_entries, recent_entries, weekly_snapshot


def editor_delta(form, entry=None):
    raw = form["content_delta_raw"].value()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (TypeError, json.JSONDecodeError):
            pass
    if entry:
        return entry.content_delta
    return empty_delta()


def save_attachments(entry, uploaded_files):
    for image in uploaded_files:
        JournalAttachment.objects.create(
            entry=entry,
            image=image,
            original_name=image.name,
            content_type=getattr(image, "content_type", "") or "",
            size=image.size,
        )


def dashboard(request):
    today = timezone.localdate()
    entry = JournalEntry.objects.filter(date=today).first()
    if request.method == "POST":
        form = JournalEntryForm(request.POST, request.FILES, instance=entry)
        if form.is_valid():
            saved = form.save()
            save_attachments(saved, form.cleaned_data.get("images", []))
            messages.success(request, f"Journal saved for {saved.date:%Y-%m-%d}.")
            return redirect("journal:dashboard")
    else:
        form = JournalEntryForm(instance=entry, initial={"date": today})
    return render(
        request,
        "journal/dashboard.html",
        {
            "entry": entry,
            "form": form,
            "editor_delta": editor_delta(form, entry),
            "reader_delta": entry.content_delta if entry else empty_delta(),
            "recent_entries": recent_entries(),
            "snapshot": weekly_snapshot(today),
            "today": today,
        },
    )


def entry_detail(request, entry_date):
    try:
        parsed_date = date.fromisoformat(entry_date)
    except ValueError:
        messages.error(request, "Invalid journal date.")
        return redirect("journal:dashboard")
    entry = get_object_or_404(JournalEntry.objects.prefetch_related("attachments"), date=parsed_date)
    return render(
        request,
        "journal/entry.html",
        {
            "entry": entry,
            "reader_delta": entry.content_delta,
            "entry_date": parsed_date,
        },
    )


def entry_edit(request, entry_date):
    try:
        parsed_date = date.fromisoformat(entry_date)
    except ValueError:
        messages.error(request, "Invalid journal date.")
        return redirect("journal:dashboard")
    entry = JournalEntry.objects.prefetch_related("attachments").filter(date=parsed_date).first()
    if request.method == "POST":
        form = JournalEntryForm(request.POST, request.FILES, instance=entry)
        if form.is_valid():
            saved = form.save()
            save_attachments(saved, form.cleaned_data.get("images", []))
            messages.success(request, f"Journal saved for {saved.date:%Y-%m-%d}.")
            return redirect("journal:entry", entry_date=saved.date.isoformat())
    else:
        form = JournalEntryForm(instance=entry, initial={"date": parsed_date})
    return render(
        request,
        "journal/entry_edit.html",
        {
            "entry": entry,
            "form": form,
            "editor_delta": editor_delta(form, entry),
            "entry_date": parsed_date,
        },
    )


def history(request):
    query = request.GET.get("q", "").strip()
    return render(
        request,
        "journal/history.html",
        {
            "query": query,
            "entries": history_entries(query)[:60],
        },
    )


def analytics(request):
    payload = analytics_payload()
    return render(
        request,
        "journal/analytics.html",
        {
            "heatmap_weeks": heatmap_weeks(),
            "charts_json": json.dumps(payload),
            "monthly_rows": payload["monthly"],
            "weekly_rows": payload["weekly"],
            "radar": payload["radar"],
        },
    )
