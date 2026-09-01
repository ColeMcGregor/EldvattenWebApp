from django import forms

from .models import NotificationPreference


class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference

        fields = [
            "push_enabled",
            "message_push",
            "action_push",
            "vote_push",
            "event_push",
            "community_push",
            "account_push",
            "system_push",
        ]

        labels = {
            "push_enabled":
                "Push notifications",
            "message_push":
                "Messages",
            "action_push":
                "Actions",
            "vote_push":
                "Votes",
            "event_push":
                "Events",
            "community_push":
                "Community",
            "account_push":
                "Account",
            "system_push":
                "System",
        }