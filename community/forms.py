from django import forms
from django.forms import (
    BaseInlineFormSet,
    inlineformset_factory,
)

from .models import (
    ForumBoard,
    ForumBoardTarget,
    ForumBoardThreadCreationTarget,
    ForumCategory,
    ForumPost,
    ForumPostAttachment,
    ForumPostReport,
    ForumThread,
    ForumThreadTarget,
)


FORUM_TARGET_FIELDS = (
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


def forum_target_widgets():
    return {
        field_name: forms.Select(
            attrs={
                "class": "forum-target-select",
            }
        )
        for field_name in FORUM_TARGET_FIELDS
    }


def formset_has_target(formset):
    for form in formset.forms:
        if not hasattr(
            form,
            "cleaned_data",
        ):
            continue

        if form.cleaned_data.get(
            "DELETE"
        ):
            continue

        if any(
            form.cleaned_data.get(
                field_name
            )
            is not None
            for field_name
            in FORUM_TARGET_FIELDS
        ):
            return True

    return False


class ForumCategoryForm(forms.ModelForm):
    class Meta:
        model = ForumCategory

        fields = (
            "name",
            "description",
            "display_order",
        )

        widgets = {
            "name": forms.TextInput(),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                }
            ),
            "display_order":
                forms.NumberInput(
                    attrs={
                        "min": 0,
                    }
                ),
        }


class ForumBoardForm(forms.ModelForm):
    class Meta:
        model = ForumBoard

        fields = (
            "category",
            "name",
            "description",
            "display_order",
            "thread_creation_policy",
        )

        widgets = {
            "name": forms.TextInput(),
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                }
            ),
            "display_order":
                forms.NumberInput(
                    attrs={
                        "min": 0,
                    }
                ),
            "thread_creation_policy":
                forms.Select(),
        }


class ForumTargetFormBase(
    forms.ModelForm
):
    class Meta:
        fields = FORUM_TARGET_FIELDS
        widgets = forum_target_widgets()


class ForumBoardTargetForm(
    ForumTargetFormBase
):
    class Meta(
        ForumTargetFormBase.Meta
    ):
        model = ForumBoardTarget


class ForumBoardThreadCreationTargetForm(
    ForumTargetFormBase
):
    class Meta(
        ForumTargetFormBase.Meta
    ):
        model = (
            ForumBoardThreadCreationTarget
        )


class ForumThreadTargetForm(
    ForumTargetFormBase
):
    class Meta(
        ForumTargetFormBase.Meta
    ):
        model = ForumThreadTarget


class BaseForumTargetFormSet(
    BaseInlineFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return


class BaseForumBoardThreadCreationTargetFormSet(
    BaseForumTargetFormSet
):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        if (
            self.instance.thread_creation_policy
            != ForumBoard
            .ThreadCreationPolicy
            .TARGETED
        ):
            return

        if not formset_has_target(self):
            raise forms.ValidationError(
                "A targeted board must have "
                "at least one thread-creation "
                "target."
            )


ForumBoardTargetFormSet = (
    inlineformset_factory(
        ForumBoard,
        ForumBoardTarget,
        form=ForumBoardTargetForm,
        formset=BaseForumTargetFormSet,
        extra=1,
        can_delete=True,
    )
)


ForumBoardThreadCreationTargetFormSet = (
    inlineformset_factory(
        ForumBoard,
        ForumBoardThreadCreationTarget,
        form=(
            ForumBoardThreadCreationTargetForm
        ),
        formset=(
            BaseForumBoardThreadCreationTargetFormSet
        ),
        extra=1,
        can_delete=True,
    )
)


class ForumThreadCreateForm(
    forms.Form
):
    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "forum-thread-title-input",
            }
        ),
    )

    body = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "forum-post-textarea",
                "rows": 8,
            }
        ),
    )


class ForumThreadEditForm(
    forms.ModelForm
):
    class Meta:
        model = ForumThread

        fields = (
            "title",
        )

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class":
                        "forum-thread-title-input",
                }
            ),
        }


ForumThreadTargetFormSet = (
    inlineformset_factory(
        ForumThread,
        ForumThreadTarget,
        form=ForumThreadTargetForm,
        formset=BaseForumTargetFormSet,
        extra=1,
        can_delete=True,
    )
)


class ForumPostForm(
    forms.ModelForm
):
    class Meta:
        model = ForumPost

        fields = (
            "body",
        )

        widgets = {
            "body": forms.Textarea(
                attrs={
                    "class": "forum-post-textarea",
                    "rows": 6,
                }
            ),
        }


class ForumPostAttachmentForm(
    forms.ModelForm
):
    class Meta:
        model = ForumPostAttachment

        fields = (
            "label",
            "url",
            "display_order",
        )

        widgets = {
            "label": forms.TextInput(),
            "url": forms.URLInput(),
            "display_order":
                forms.NumberInput(
                    attrs={
                        "min": 0,
                    }
                ),
        }


ForumPostAttachmentFormSet = (
    inlineformset_factory(
        ForumPost,
        ForumPostAttachment,
        form=ForumPostAttachmentForm,
        extra=1,
        can_delete=True,
    )
)


class ForumPostReportForm(
    forms.ModelForm
):
    class Meta:
        model = ForumPostReport

        fields = (
            "reason",
        )

        widgets = {
            "reason": forms.Textarea(
                attrs={
                    "rows": 5,
                }
            ),
        }


class ForumDraftContentForm(
    forms.Form
):
    title = forms.CharField(
        max_length=255,
        required=False,
    )

    body = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 8,
            }
        ),
    )


class ForumThreadMoveForm(
    forms.Form
):
    destination_board = (
        forms.ModelChoiceField(
            queryset=ForumBoard.objects.none(),
        )
    )

    def __init__(
        self,
        *args,
        board_queryset=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if board_queryset is not None:
            self.fields[
                "destination_board"
            ].queryset = board_queryset


class ForumThreadMergeForm(
    forms.Form
):
    destination_thread = (
        forms.ModelChoiceField(
            queryset=ForumThread.objects.none(),
        )
    )

    def __init__(
        self,
        *args,
        thread_queryset=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if thread_queryset is not None:
            self.fields[
                "destination_thread"
            ].queryset = thread_queryset


class ForumThreadSplitForm(
    forms.Form
):
    title = forms.CharField(
        max_length=255,
    )

    destination_board = (
        forms.ModelChoiceField(
            queryset=ForumBoard.objects.none(),
        )
    )

    posts = forms.ModelMultipleChoiceField(
        queryset=ForumPost.objects.none(),
    )

    def __init__(
        self,
        *args,
        board_queryset=None,
        post_queryset=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if board_queryset is not None:
            self.fields[
                "destination_board"
            ].queryset = board_queryset

        if post_queryset is not None:
            self.fields[
                "posts"
            ].queryset = post_queryset


class ForumPostMoveForm(
    forms.Form
):
    destination_thread = (
        forms.ModelChoiceField(
            queryset=ForumThread.objects.none(),
        )
    )

    posts = forms.ModelMultipleChoiceField(
        queryset=ForumPost.objects.none(),
    )

    def __init__(
        self,
        *args,
        thread_queryset=None,
        post_queryset=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        if thread_queryset is not None:
            self.fields[
                "destination_thread"
            ].queryset = thread_queryset

        if post_queryset is not None:
            self.fields[
                "posts"
            ].queryset = post_queryset