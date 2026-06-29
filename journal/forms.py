import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import JournalEntry, empty_delta


class DateInput(forms.DateInput):
    input_type = "date"


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        files = data or []
        if not isinstance(files, (list, tuple)):
            files = [files]
        return [super(MultipleFileField, self).clean(file, initial) for file in files if file]


def style_fields(fields):
    for field in fields.values():
        field.widget.attrs.setdefault("class", "field-input")


class JournalEntryForm(forms.ModelForm):
    content_delta_raw = forms.CharField(required=False, widget=forms.HiddenInput)
    content_text = forms.CharField(required=False, widget=forms.HiddenInput)
    images = MultipleFileField(
        required=False,
        label="Images",
        widget=MultipleFileInput(attrs={"accept": "image/*", "multiple": True}),
    )

    class Meta:
        model = JournalEntry
        fields = ["date", "title", "mood_score", "energy_score", "productivity_score", "tags"]
        widgets = {
            "date": DateInput(),
        }
        labels = {
            "mood_score": "Mood",
            "energy_score": "Energy",
            "productivity_score": "Productivity",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self.fields)
        self.fields["date"].initial = self.fields["date"].initial or timezone.localdate()
        self.fields["title"].widget.attrs.setdefault("placeholder", "Optional title")
        self.fields["tags"].widget.attrs.setdefault("placeholder", "gratitude, work, health")
        if not self.is_bound:
            self.fields["content_delta_raw"].initial = json.dumps(
                self.instance.content_delta if self.instance and self.instance.pk else empty_delta()
            )
            self.fields["content_text"].initial = self.instance.content_text if self.instance and self.instance.pk else ""

    def clean_images(self):
        images = self.cleaned_data.get("images") or []
        for image in images:
            content_type = getattr(image, "content_type", "") or ""
            if not content_type.startswith("image/"):
                raise ValidationError("Only image attachments are supported.")
            if image.size > 5 * 1024 * 1024:
                raise ValidationError("Each image must be 5 MB or smaller.")
        return images

    def clean_content_delta_raw(self):
        raw = self.cleaned_data.get("content_delta_raw") or ""
        if not raw.strip():
            return empty_delta()
        try:
            delta = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("Journal content is not valid editor data.") from exc
        if not isinstance(delta, dict) or not isinstance(delta.get("ops"), list):
            raise ValidationError("Journal content must be a Delta object with ops.")
        return delta

    def clean_content_text(self):
        return (self.cleaned_data.get("content_text") or "").strip()

    def save(self, commit=True):
        entry = super().save(commit=False)
        entry.content_delta = self.cleaned_data["content_delta_raw"]
        entry.content_text = self.cleaned_data["content_text"]
        if commit:
            entry.save()
            self.save_m2m()
        return entry
