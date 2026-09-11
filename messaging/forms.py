from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import (
    BaseInlineFormSet,
    inlineformset_factory,
)

from accounts.models import AccountStatus, User

from .models import (
    Conversation,
    ConversationTarget,
    Message,
    UserBlock,
)


CONVERSATION_TARGET_FIELDS = (
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


class ConversationForm(forms.Form):
    conversation_type = forms.ChoiceField(
        choices=Conversation.ConversationType.choices,
        required=False,
        initial=Conversation.ConversationType.DIRECT,
        widget=forms.Select(
            attrs={
                "class": "conversation-type-select",
            }
        ),
    )

    title = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "conversation-title-input",
            }
        ),
    )

    participants = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="People",
        widget=forms.SelectMultiple(
            attrs={
                "class": "conversation-participants",
            }
        ),
    )

    def __init__(
        self,
        *args,
        current_user=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        users = User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        if current_user is not None:
            users = users.exclude(
                pk=current_user.pk,
            )

            blocked_user_pairs = (
                UserBlock.objects
                .filter(
                    Q(
                        blocker=current_user,
                    )
                    | Q(
                        blocked=current_user,
                    )
                )
                .values_list(
                    "blocker_id",
                    "blocked_id",
                )
            )

            excluded_ids = set()

            for (
                blocker_id,
                blocked_id,
            ) in blocked_user_pairs:
                if blocker_id != current_user.pk:
                    excluded_ids.add(
                        blocker_id
                    )

                if blocked_id != current_user.pk:
                    excluded_ids.add(
                        blocked_id
                    )

            users = users.exclude(
                pk__in=excluded_ids,
            )

        self.fields[
            "participants"
        ].queryset = users.order_by(
            "display_name",
            "username",
        )

    def clean(self):
        cleaned_data = super().clean()

        conversation_type = (
            cleaned_data.get(
                "conversation_type"
            )
            or Conversation.ConversationType.DIRECT
        )

        cleaned_data[
            "conversation_type"
        ] = conversation_type

        title = (
            cleaned_data.get(
                "title",
                "",
            )
            or ""
        ).strip()

        cleaned_data[
            "title"
        ] = title

        participants = cleaned_data.get(
            "participants"
        )

        if (
            conversation_type
            == Conversation.ConversationType.DIRECT
        ):
            if (
                participants is None
                or not participants.exists()
            ):
                self.add_error(
                    "participants",
                    (
                        "Select at least one person "
                        "for this conversation."
                    ),
                )

            cleaned_data["title"] = ""

        elif (
            conversation_type
            == Conversation.ConversationType.GROUP
        ):
            if not title:
                self.add_error(
                    "title",
                    (
                        "Enter a title for the "
                        "group conversation."
                    ),
                )

            if (
                participants is not None
                and participants.exists()
            ):
                self.add_error(
                    "participants",
                    (
                        "Do not select individual people "
                        "for a group conversation."
                    ),
                )

        return cleaned_data


class ConversationTargetForm(forms.ModelForm):
    class Meta:
        model = ConversationTarget
        fields = CONVERSATION_TARGET_FIELDS
        widgets = {
            field_name: forms.Select(
                attrs={
                    "class": (
                        "conversation-target-select"
                    ),
                }
            )
            for field_name
            in CONVERSATION_TARGET_FIELDS
        }


class BaseConversationTargetFormSet(
    BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        active_target_count = 0

        for form in self.forms:
            cleaned_data = getattr(
                form,
                "cleaned_data",
                None,
            )

            if not cleaned_data:
                continue

            if cleaned_data.get("DELETE"):
                continue

            has_selector = any(
                cleaned_data.get(
                    field_name
                )
                is not None
                for field_name
                in CONVERSATION_TARGET_FIELDS
            )

            if has_selector:
                active_target_count += 1

        if active_target_count == 0:
            raise ValidationError(
                (
                    "A group conversation must have "
                    "at least one target."
                )
            )


ConversationTargetFormSet = (
    inlineformset_factory(
        Conversation,
        ConversationTarget,
        form=ConversationTargetForm,
        formset=BaseConversationTargetFormSet,
        extra=1,
        can_delete=True,
    )
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
                    "class": (
                        "message-form-textarea"
                    ),
                    "rows": 3,
                }
            ),
        }