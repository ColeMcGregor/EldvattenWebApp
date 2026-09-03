from django import forms

from accounts.models import AccountStatus, User

from .models import (
    Event,
    EventParticipation,
    EventTarget,
)


class EventForm(forms.ModelForm):
    visible_to_invited_only = forms.BooleanField(
        required=False,
        label="Visible to invited users only?",
    )

    def __init__(
        self,
        *args,
        allow_status_change=True,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if not allow_status_change:
            self.fields.pop(
                "status",
                None,
            )

    class Meta:
        model = Event

        fields = (
            "title",
            "description",
            "start_at",
            "end_at",
            "location",
            "visibility",
            "status",
        )

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "event-form-input",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "event-form-textarea",
                    "rows": 5,
                }
            ),
            "start_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "event-form-input",
                    "type": "datetime-local",
                },
            ),
            "end_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "event-form-input",
                    "type": "datetime-local",
                },
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "event-form-input",
                }
            ),
            "visibility": forms.Select(
                attrs={
                    "class": "event-form-select",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "event-form-select",
                }
            ),
        }


class EventTargetForm(forms.ModelForm):
    class Meta:
        model = EventTarget

        fields = (
            "user",
            "citizenship_class",
            "social_rank",
            "office",
            "chapter",
            "household",
            "governance_body",
            "order",
            "order_rank",
            "community_group",
            "household_leadership_type",
        )

        widgets = {
            "user": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "citizenship_class": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "social_rank": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "office": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "chapter": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "household": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "governance_body": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "order": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "order_rank": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "community_group": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
            "household_leadership_type": forms.Select(
                attrs={
                    "class": "event-target-select",
                }
            ),
        }


class RSVPForm(forms.ModelForm):
    class Meta:
        model = EventParticipation

        fields = (
            "rsvp_status",
        )

        widgets = {
            "rsvp_status": forms.Select(
                attrs={
                    "class": "event-rsvp-select",
                }
            ),
        }


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = EventParticipation

        fields = (
            "attendance_status",
        )

        widgets = {
            "attendance_status": forms.Select(
                attrs={
                    "class": "event-attendance-select",
                }
            ),
        }


class AttendanceManagementForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        ).order_by(
            "display_name",
            "username",
        ),
        label="Member",
    )

    attendance_status = forms.ChoiceField(
        choices=(
            EventParticipation
            .AttendanceStatus
            .choices
        ),
        initial=(
            EventParticipation
            .AttendanceStatus
            .ATTENDED
        ),
        label="Attendance",
    )