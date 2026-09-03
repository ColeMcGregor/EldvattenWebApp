from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .models import (
    Resource,
    ResourceTarget,
)


class ResourceTargetInlineFormSet(
    BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(
            form.errors
            for form in self.forms
        ):
            return

        resource = self.instance

        if (
            resource.visibility
            != Resource.Visibility.CUSTOM
        ):
            return

        has_include_target = False

        for form in self.forms:
            if not hasattr(
                form,
                "cleaned_data",
            ):
                continue

            if form.cleaned_data.get(
                "DELETE",
                False,
            ):
                continue

            effect = form.cleaned_data.get(
                "effect"
            )

            if (
                effect
                == ResourceTarget.Effect.INCLUDE
            ):
                has_include_target = True
                break

        if not has_include_target:
            raise ValidationError(
                "A custom resource must have "
                "at least one include target."
            )


class ResourceTargetInline(
    admin.StackedInline
):
    model = ResourceTarget
    formset = ResourceTargetInlineFormSet
    extra = 0

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


@admin.register(Resource)
class ResourceAdmin(
    admin.ModelAdmin
):
    list_display = (
        "title",
        "resource_type",
        "visibility",
        "is_active",
        "sort_order",
        "created_by",
        "updated_at",
    )

    list_filter = (
        "resource_type",
        "visibility",
        "is_active",
    )

    search_fields = (
        "title",
        "description",
        "external_url",
    )

    ordering = (
        "sort_order",
        "title",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    fields = (
        "title",
        "description",
        "resource_type",
        "file",
        "external_url",
        "visibility",
        "sort_order",
        "is_active",
        "created_by",
        "created_at",
        "updated_at",
    )

    inlines = (
        ResourceTargetInline,
    )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        if not obj.created_by_id:
            obj.created_by = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )