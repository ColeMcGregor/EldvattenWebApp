
from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory

from accounts.models import AccountStatus, User

from .models import Resource, ResourceTarget


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource

        fields = (
            "title",
            "description",
            "resource_type",
            "file",
            "external_url",
            "visibility",
            "sort_order",
            "is_active",
        )

        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 5,
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        resource_type = cleaned_data.get(
            "resource_type"
        )

        if resource_type == Resource.ResourceType.FILE:
            cleaned_data["external_url"] = ""

        elif resource_type == Resource.ResourceType.LINK:
            cleaned_data["file"] = False

        return cleaned_data


class ResourceTargetForm(forms.ModelForm):
    class Meta:
        model = ResourceTarget

        fields = (
            "effect",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["user"].queryset = (
            User.objects.filter(
                account_status=AccountStatus.MEMBER,
                is_active=True,
            ).order_by(
                "display_name",
                "username",
            )
        )


class BaseResourceTargetFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(
            form.errors
            for form in self.forms
        ):
            return

        if (
            self.instance.visibility
            != Resource.Visibility.CUSTOM
        ):
            return

        for form in self.forms:
            data = form.cleaned_data

            if not data or data.get("DELETE"):
                continue

            if (
                data.get("effect")
                == ResourceTarget.Effect.INCLUDE
            ):
                return

        raise ValidationError(
            "A custom resource must have "
            "at least one include target."
        )


ResourceTargetFormSet = inlineformset_factory(
    Resource,
    ResourceTarget,
    form=ResourceTargetForm,
    formset=BaseResourceTargetFormSet,
    extra=1,
    can_delete=True,
    max_num=100,
    validate_max=True,
)
