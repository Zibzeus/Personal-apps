from django import forms
from django.utils import timezone

from .models import Goal, MonthlyReview, Project, Task, WeeklyReview
from .services import start_of_month, start_of_week


class DateInput(forms.DateInput):
    input_type = "date"


def style_fields(fields):
    for field in fields.values():
        field.widget.attrs.setdefault("class", "field-input")
        if isinstance(field.widget, forms.Textarea):
            field.widget.attrs.setdefault("rows", 4)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_fields(self.fields)


class TaskForm(StyledModelForm):
    class Meta:
        model = Task
        fields = ["title", "notes", "status", "priority", "energy", "planned_date", "due_date", "goal", "project"]
        widgets = {
            "planned_date": DateInput(),
            "due_date": DateInput(),
            "notes": forms.Textarea(),
        }


class QuickTaskForm(StyledModelForm):
    class Meta:
        model = Task
        fields = ["title", "priority", "energy", "planned_date", "due_date", "goal", "project"]
        widgets = {
            "planned_date": DateInput(),
            "due_date": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["planned_date"].initial = self.fields["planned_date"].initial or timezone.localdate()
        self.fields["title"].widget.attrs.setdefault("placeholder", "Capture next action")


class GoalForm(StyledModelForm):
    class Meta:
        model = Goal
        fields = [
            "title",
            "area",
            "status",
            "priority",
            "target_date",
            "target_value",
            "current_value",
            "unit",
            "progress_note",
        ]
        widgets = {
            "target_date": DateInput(),
            "progress_note": forms.Textarea(),
        }


class ProjectForm(StyledModelForm):
    class Meta:
        model = Project
        fields = ["title", "goal", "status", "priority", "due_date", "notes"]
        widgets = {
            "due_date": DateInput(),
            "notes": forms.Textarea(),
        }


class WeeklyReviewForm(StyledModelForm):
    class Meta:
        model = WeeklyReview
        fields = ["week_start", "wins", "blockers", "next_focus", "notes"]
        widgets = {
            "week_start": DateInput(),
            "wins": forms.Textarea(),
            "blockers": forms.Textarea(),
            "next_focus": forms.Textarea(),
            "notes": forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["week_start"].initial = self.fields["week_start"].initial or start_of_week()

    def clean_week_start(self):
        return start_of_week(self.cleaned_data["week_start"])

    def validate_unique(self):
        return None


class MonthlyReviewForm(StyledModelForm):
    class Meta:
        model = MonthlyReview
        fields = ["month", "wins", "blockers", "next_focus", "notes"]
        widgets = {
            "month": DateInput(),
            "wins": forms.Textarea(),
            "blockers": forms.Textarea(),
            "next_focus": forms.Textarea(),
            "notes": forms.Textarea(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["month"].initial = self.fields["month"].initial or start_of_month()

    def clean_month(self):
        return start_of_month(self.cleaned_data["month"])

    def validate_unique(self):
        return None
