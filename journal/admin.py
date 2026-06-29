from django.contrib import admin

from .models import JournalAttachment, JournalEntry


class JournalAttachmentInline(admin.TabularInline):
    model = JournalAttachment
    extra = 0
    readonly_fields = ("original_name", "content_type", "size", "created_at")


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "title", "mood_score", "energy_score", "productivity_score", "updated_at")
    list_filter = ("mood_score", "energy_score", "productivity_score")
    search_fields = ("title", "content_text", "tags")
    date_hierarchy = "date"
    inlines = [JournalAttachmentInline]


@admin.register(JournalAttachment)
class JournalAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "entry", "content_type", "size", "created_at")
    search_fields = ("original_name", "entry__title", "entry__content_text")
