from django import forms

from organization.models import CommunityGroup

from .models import Comment, Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = (
            "body",
            "visibility",
            "visible_to_groups",
        )
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "post-form-textarea",
                    "rows": 6,
                }
            ),
            "visibility": forms.Select(
                attrs={
                    "class": "post-form-select",
                }
            ),
            "visible_to_groups": forms.SelectMultiple(
                attrs={
                    "class": "post-form-groups",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")
        visible_to_groups = cleaned_data.get("visible_to_groups")

        if (
            visibility == Post.Visibility.SELECTED_GROUPS
            and not visible_to_groups
        ):
            self.add_error(
                "visible_to_groups",
                "Select at least one group for this visibility.",
            )

        if (
            visibility != Post.Visibility.SELECTED_GROUPS
            and visible_to_groups
        ):
            cleaned_data["visible_to_groups"] = CommunityGroup.objects.none()

        return cleaned_data


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