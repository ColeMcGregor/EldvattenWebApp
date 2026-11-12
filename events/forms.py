
from django import forms
from django.db.models import CharField, F, Value
from django.db.models.functions import Coalesce, Concat, NullIf, Trim

from accounts.models import AccountStatus, User

from .models import (
    Event,
    EventParticipation,
    EventTarget,
)


def community_user_label(user):
    name = user.community_name

    if name == user.username:
        return f"@{user.username}"

    return f"{name} (@{user.username})"


def order_users_by_community_name(queryset):
    return queryset.annotate(
        community_sort_name=Coalesce(
            NullIf(
                Trim(F("eldvatten_name")),
                Value(""),
            ),
            NullIf(
                Trim(F("display_name")),
                Value(""),
            ),
            NullIf(
                Trim(
                    Concat(
                        F("first_name"),
                        Value(" "),
                        F("last_name"),
                        output_field=CharField(),
                    )
                ),
                Value(""),
            ),
            F("username"),
            output_field=CharField(),
        )
    ).order_by(
        "community_sort_name",
        "username",
        "pk",
    )


class CommunityUserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return community_user_label(obj)


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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user_field = self.fields["user"]
        user_field.label_from_instance = community_user_label
        user_field.queryset = order_users_by_community_name(
            user_field.queryset
        )

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
    user = CommunityUserChoiceField(
        queryset=User.objects.none(),
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        eligible_users = User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        self.fields["user"].queryset = (
            order_users_by_community_name(eligible_users)
        )
