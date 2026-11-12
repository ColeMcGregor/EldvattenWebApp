
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import CharField, F, Value
from django.db.models.functions import Coalesce, Concat, NullIf, Trim
from django.forms import BaseInlineFormSet, inlineformset_factory

from accounts.models import AccountStatus, User

from .models import Resource, ResourceTarget


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

        user_field = self.fields["user"]
        user_field.label_from_instance = community_user_label

        eligible_users = User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        user_field.queryset = order_users_by_community_name(
            eligible_users
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
