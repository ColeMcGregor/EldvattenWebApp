from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import (
    Comment,
    Post,
    PostTarget,
)


POST_TARGET_FIELDS = (
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


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = (
            "body",
            "visibility",
        )
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "post-form-textarea",
                    "rows": 3,
                    "placeholder": (
                        "Share Something?"
                    ),
                }
            ),
            "visibility": forms.Select(
                attrs={
                    "class": "post-form-select",
                }
            ),
        }


class PostTargetForm(forms.ModelForm):
    class Meta:
        model = PostTarget
        fields = POST_TARGET_FIELDS
        widgets = {
            field_name: forms.Select(
                attrs={
                    "class": "post-target-select",
                }
            )
            for field_name in POST_TARGET_FIELDS
        }


class BasePostTargetFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if (
            self.instance.visibility
            != Post.Visibility.SELECTED_GROUPS
        ):
            return

        has_target = False

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            for field_name in POST_TARGET_FIELDS:
                if form.cleaned_data.get(field_name) is not None:
                    has_target = True
                    break

            if has_target:
                break

        if not has_target:
            raise forms.ValidationError(
                "Add at least one audience target."
            )


PostTargetFormSet = inlineformset_factory(
    Post,
    PostTarget,
    form=PostTargetForm,
    formset=BasePostTargetFormSet,
    extra=1,
    can_delete=True,
)


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = (
            "body",
        )
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "comment-form-textarea",
                    "rows": 3,
                }
            ),
        }


class ReplyForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = (
            "body",
        )
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "reply-form-textarea",
                    "rows": 2,
                }
            ),
        }