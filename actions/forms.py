from django import forms

from .models import Action, ActionTarget


class ActionForm(forms.ModelForm):
    class Meta:
        model = Action
        fields = [
            "title",
            "instructions",
            "external_url",
            "deadline",
            "is_required",
            "linked_posts",
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
            "linked_posts": forms.SelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["deadline"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]


class ActionTargetForm(forms.ModelForm):
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