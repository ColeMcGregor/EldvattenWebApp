from django import forms
from django.db.models import Q

from accounts.models import AccountStatus, User

from .models import Message, UserBlock


class ConversationForm(forms.Form):
    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        label="Participants",
        widget=forms.SelectMultiple(
            attrs={
                "class": "conversation-participants",
            }
        ),
    )

    def __init__(self, *args, current_user=None, **kwargs):
        super().__init__(*args, **kwargs)

        users = User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        if current_user is not None:
            users = users.exclude(pk=current_user.pk)

            blocked_user_ids = UserBlock.objects.filter(
                Q(blocker=current_user)
                | Q(blocked=current_user)
            ).values_list(
                "blocker_id",
                "blocked_id",
            )

            excluded_ids = set()

            for blocker_id, blocked_id in blocked_user_ids:
                if blocker_id != current_user.pk:
                    excluded_ids.add(blocker_id)

                if blocked_id != current_user.pk:
                    excluded_ids.add(blocked_id)

            users = users.exclude(
                pk__in=excluded_ids,
            )

        self.fields["participants"].queryset = users.order_by(
            "display_name",
            "username",
        )


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = (
            "body",
        )
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "message-form-textarea",
                    "rows": 3,
                }
            ),
        }