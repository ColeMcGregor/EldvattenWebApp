
from django import forms
from django.db.models import CharField, F, Value
from django.db.models.functions import Coalesce, Concat, NullIf, Trim

from .models import Action, ActionTarget


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


class ActionForm(forms.ModelForm):
    class Meta:
        model = Action
        fields = [
            "title",
            "instructions",
            "external_url",
            "deadline",
            "is_required",
            "linked_threads",
        ]

        widgets = {
            "title": forms.TextInput(),
            "instructions": forms.Textarea(
                attrs={
                    "rows": 6,
                }
            ),
            "external_url": forms.URLInput(),
            "deadline": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "linked_threads":
                forms.SelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["deadline"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]


class ActionTargetForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user_field = self.fields["user"]
        user_field.label_from_instance = community_user_label
        user_field.queryset = order_users_by_community_name(
            user_field.queryset
        )

    class Meta:
        model = ActionTarget
        fields = [
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
        ]
