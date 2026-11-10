
from django import forms

from .models import BugReport


class BugReportForm(forms.ModelForm):
    class Meta:
        model = BugReport

        fields = [
            "contact_email",
            "description",
            "expected_behavior",
            "steps_to_reproduce",
            "page_url",
        ]

        labels = {
            "contact_email": "Email (optional)",
            "description": "Describe the bug",
            "expected_behavior": "What did you expect to happen?",
            "steps_to_reproduce": "How can we reproduce it?",
            "page_url": "Page where the bug occurred",
        }

        widgets = {
            "contact_email": forms.EmailInput(
                attrs={
                    "autocomplete": "email",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": (
                        "Describe what happened and "
                        "what went wrong."
                    ),
                }
            ),
            "expected_behavior": forms.Textarea(
                attrs={
                    "rows": 3,
                }
            ),
            "steps_to_reproduce": forms.Textarea(
                attrs={
                    "rows": 4,
                }
            ),
            "page_url": forms.URLInput(
                attrs={
                    "placeholder": "https://",
                }
            ),
        }

    def clean_description(self):
        description = self.cleaned_data["description"].strip()

        if len(description) < 10:
            raise forms.ValidationError(
                "Please provide at least 10 characters "
                "describing the problem."
            )

        return description


class BugReportManagementForm(forms.ModelForm):
    class Meta:
        model = BugReport

        fields = [
            "status",
            "admin_notes",
        ]

        widgets = {
            "admin_notes": forms.Textarea(
                attrs={
                    "rows": 6,
                }
            ),
        }
