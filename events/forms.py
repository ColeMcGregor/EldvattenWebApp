from django import forms

from accounts.models import AccountStatus, User

from .models import Event, EventParticipation


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = (
            "title",
            "description",
            "start_at",
            "end_at",
            "location",
            "visibility",
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
                attrs={
                    "class": "event-form-input",
                    "type": "datetime-local",
                }
            ),
            "end_at": forms.DateTimeInput(
                attrs={
                    "class": "event-form-input",
                    "type": "datetime-local",
                }
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
        choices=EventParticipation.AttendanceStatus.choices,
        initial=EventParticipation.AttendanceStatus.ATTENDED,
        label="Attendance",
    )