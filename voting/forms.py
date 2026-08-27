from django import forms
from django.forms import inlineformset_factory

from .models import (
    Vote,
    VoteComment,
    VoteEligibilityTarget,
    VoteOption,
)


class VoteBallotForm(forms.Form):
    option = forms.ModelChoiceField(
        queryset=VoteOption.objects.none(),
        empty_label=None,
        widget=forms.RadioSelect,
    )

    comment = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
            }
        ),
    )

    def __init__(
        self,
        *args,
        vote,
        existing_option=None,
        existing_comment="",
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.vote = vote

        self.fields["option"].queryset = vote.options.all()

        if existing_option is not None:
            self.fields["option"].initial = existing_option

        if existing_comment:
            self.fields["comment"].initial = existing_comment


class VoteForm(forms.ModelForm):
    class Meta:
        model = Vote
        fields = [
            "title",
            "description",
            "approval_rule",
            "is_anonymous",
            "requires_quorum",
            "quorum_numerator",
            "quorum_denominator",
            "requires_all_responses",
            "opens_at",
            "closes_at",
        ]

        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 6,
                }
            ),
            "opens_at": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),
            "closes_at": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["opens_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]

        self.fields["closes_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
        ]

        if (
            self.instance.pk
            and self.instance.status != Vote.Status.DRAFT
        ):
            self.fields["is_anonymous"].disabled = True


class VoteOptionForm(forms.ModelForm):
    class Meta:
        model = VoteOption
        fields = [
            "label",
            "sort_order",
        ]


class VoteEligibilityTargetForm(forms.ModelForm):
    class Meta:
        model = VoteEligibilityTarget
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


class VoteCommentForm(forms.ModelForm):
    class Meta:
        model = VoteComment
        fields = [
            "body",
        ]

        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 4,
                }
            ),
        }


VoteOptionFormSet = inlineformset_factory(
    Vote,
    VoteOption,
    form=VoteOptionForm,
    extra=2,
    can_delete=True,
)


VoteEligibilityTargetFormSet = inlineformset_factory(
    Vote,
    VoteEligibilityTarget,
    form=VoteEligibilityTargetForm,
    extra=1,
    can_delete=True,
)