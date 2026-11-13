
from django import forms
from django.forms.models import ModelChoiceIterator
from django.utils import timezone

from .models import (
    Chapter,
    ChapterStatus,
    CitizenshipClass,
    CitizenshipRecord,
    Household,
    Office,
    UserOffice,
    GovernanceBody,
    GovernanceMembership,
    CommunityGroup,
    GroupMembership,
    SocialRank,
    Order,
    OrderRank,
    OrderMembership,
    UserSocialRank,
)


def member_choice_label(user):
    return f"{user.community_name} (@{user.username})"


class CommunityNameChoiceIterator(ModelChoiceIterator):
    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label)

        users = sorted(
            self.queryset,
            key=lambda user: (
                user.community_name.casefold(),
                user.username.casefold(),
            ),
        )

        for user in users:
            yield self.choice(user)


def configure_member_choices(field):
    field.label_from_instance = member_choice_label
    field.iterator = CommunityNameChoiceIterator
    field.widget.choices = field.choices


class ChapterForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = ("name", "description", "status")
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Chapter name"}
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Chapter description",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        statuses = ChapterStatus.objects.filter(
            is_selectable=True,
        )

        if self.instance.pk and self.instance.status_id:
            statuses = statuses | ChapterStatus.objects.filter(
                pk=self.instance.status_id,
            )

        self.fields["status"].queryset = (
            statuses.distinct().order_by("name")
        )

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class HouseholdForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = (
            "name",
            "description",
            "is_assignable",
        )
        labels = {
            "is_assignable": "Available for New Assignments",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Household name"}
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Household description",
                }
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class CitizenshipClassForm(forms.ModelForm):
    class Meta:
        model = CitizenshipClass
        fields = (
            "name",
            "description",
            "is_assignable",
        )
        labels = {
            "is_assignable": "Available for New Assignments",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class SocialRankForm(forms.ModelForm):
    class Meta:
        model = SocialRank
        fields = (
            "name",
            "description",
            "is_assignable",
        )
        labels = {
            "is_assignable": "Available for New Assignments",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class CitizenshipAssignmentForm(forms.ModelForm):
    class Meta:
        model = CitizenshipRecord
        fields = (
            "user",
            "citizenship_class",
            "chapter",
            "started_at",
            "notes",
        )
        widgets = {
            "started_at": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2}
            ),
        }
        labels = {
            "user": "Member",
            "started_at": "Start date",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["citizenship_class"].queryset = (
            CitizenshipClass.objects.filter(
                is_assignable=True,
            ).order_by("name")
        )

        self.fields["chapter"].queryset = (
            Chapter.objects.filter(
                status__is_selectable=True,
                status__allows_new_citizens=True,
            ).order_by("name")
        )

        self.fields["started_at"].initial = timezone.localdate()

        configure_member_choices(
            self.fields["user"]
        )

    def clean(self):
        values = super().clean()
        user = values.get("user")

        if user and CitizenshipRecord.objects.filter(
            user=user,
            ended_at__isnull=True,
        ).exists():
            self.add_error(
                "user",
                "End this member's current citizenship record first.",
            )

        return values


class SocialRankAssignmentForm(forms.ModelForm):
    class Meta:
        model = UserSocialRank
        fields = (
            "user",
            "social_rank",
            "started_at",
            "notes",
        )
        widgets = {
            "started_at": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2}
            ),
        }
        labels = {
            "user": "Member",
            "started_at": "Start date",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["social_rank"].queryset = (
            SocialRank.objects.filter(
                is_assignable=True,
            ).order_by("name")
        )

        self.fields["started_at"].initial = timezone.localdate()

        configure_member_choices(
            self.fields["user"]
        )

    def clean(self):
        values = super().clean()
        user = values.get("user")

        if user and UserSocialRank.objects.filter(
            user=user,
            ended_at__isnull=True,
        ).exists():
            self.add_error(
                "user",
                "End this member's current social rank first.",
            )

        return values


class OfficeForm(forms.ModelForm):
    class Meta:
        model = Office
        fields = (
            "name",
            "description",
            "is_assignable",
        )
        labels = {
            "is_assignable": "Available for New Assignments",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class GovernanceBodyForm(forms.ModelForm):
    class Meta:
        model = GovernanceBody
        fields = (
            "name",
            "description",
            "is_assignable",
        )
        labels = {
            "is_assignable": "Available for New Assignments",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class OfficeAssignmentForm(forms.ModelForm):
    class Meta:
        model = UserOffice
        fields = (
            "user",
            "office",
            "chapter",
            "started_at",
            "notes",
        )
        widgets = {
            "started_at": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2}
            ),
        }
        labels = {
            "user": "Member",
            "started_at": "Start date",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["office"].queryset = (
            Office.objects.filter(
                is_assignable=True,
            ).order_by("name")
        )

        self.fields["chapter"].queryset = (
            Chapter.objects.filter(
                status__is_selectable=True,
            ).order_by("name")
        )

        configure_member_choices(
            self.fields["user"]
        )

        self.fields["started_at"].initial = timezone.localdate()

    def clean(self):
        values = super().clean()

        user = values.get("user")
        office = values.get("office")
        chapter = values.get("chapter")

        if (
            user
            and office
            and chapter
            and UserOffice.objects.filter(
                user=user,
                office=office,
                chapter=chapter,
                ended_at__isnull=True,
            ).exists()
        ):
            self.add_error(
                "user",
                "This member already holds this office in this chapter.",
            )

        return values


class GovernanceMembershipForm(forms.ModelForm):
    class Meta:
        model = GovernanceMembership
        fields = (
            "user",
            "governance_body",
            "started_at",
            "notes",
        )
        widgets = {
            "started_at": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2}
            ),
        }
        labels = {
            "user": "Member",
            "started_at": "Start date",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["governance_body"].queryset = (
            GovernanceBody.objects.filter(
                is_assignable=True,
            ).order_by("name")
        )

        configure_member_choices(
            self.fields["user"]
        )

        self.fields["started_at"].initial = timezone.localdate()

    def clean(self):
        values = super().clean()

        user = values.get("user")
        body = values.get("governance_body")

        if (
            user
            and body
            and GovernanceMembership.objects.filter(
                user=user,
                governance_body=body,
                ended_at__isnull=True,
            ).exists()
        ):
            self.add_error(
                "user",
                "This member already belongs to this governance body.",
            )

        return values


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = (
            "name",
            "description",
            "uses_ranks",
            "is_assignable",
        )
        labels = {
            "uses_ranks": "Uses Order Ranks",
            "is_assignable": "Available for New Assignments",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean(self):
        values = super().clean()

        if (
            self.instance.pk
            and values.get("uses_ranks") is not None
            and values["uses_ranks"] != self.instance.uses_ranks
            and OrderMembership.objects.filter(
                order=self.instance,
            ).exists()
        ):
            self.add_error(
                "uses_ranks",
                "An Order's rank structure cannot be changed "
                "after memberships have been recorded.",
            )

        return values


class OrderRankForm(forms.ModelForm):
    class Meta:
        model = OrderRank
        fields = (
            "name",
            "rank_order",
            "is_assignable",
        )
        labels = {
            "rank_order": "Display Order",
            "is_assignable": "Available for New Assignments",
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class OrderMembershipForm(forms.ModelForm):
    class Meta:
        model = OrderMembership
        fields = (
            "user",
            "order",
            "order_rank",
            "started_at",
            "notes",
        )
        labels = {
            "user": "Member",
            "started_at": "Start date",
        }
        widgets = {
            "started_at": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configure_member_choices(
            self.fields["user"]
        )

        self.fields["order"].queryset = (
            Order.objects.filter(
                is_assignable=True,
            ).order_by("name")
        )

        self.fields["order_rank"].queryset = (
            OrderRank.objects.filter(
                is_assignable=True,
            ).order_by(
                "rank_order",
                "name",
            )
        )

        self.fields["order_rank"].required = False
        self.fields["started_at"].initial = timezone.localdate()

    def clean(self):
        values = super().clean()

        user = values.get("user")
        order = values.get("order")
        rank = values.get("order_rank")

        if order:
            if order.uses_ranks and not rank:
                self.add_error(
                    "order_rank",
                    "This Order requires an Order rank.",
                )
            elif not order.uses_ranks and rank:
                self.add_error(
                    "order_rank",
                    "This Order does not use ranks.",
                )

        if (
            user
            and order
            and OrderMembership.objects.filter(
                user=user,
                order=order,
                ended_at__isnull=True,
            ).exists()
        ):
            self.add_error(
                "user",
                "End this member's current membership in this Order first.",
            )

        return values


class CommunityGroupForm(forms.ModelForm):
    class Meta:
        model = CommunityGroup
        fields = (
            "name",
            "description",
            "is_assignable",
        )
        labels = {
            "is_assignable": "Available for New Assignments",
        }
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "Group name"}
            ),
            "description": forms.Textarea(
                attrs={"rows": 3}
            ),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()


class GroupMembershipForm(forms.ModelForm):
    class Meta:
        model = GroupMembership
        fields = (
            "user",
            "community_group",
            "started_at",
            "notes",
        )
        labels = {
            "user": "Member",
            "started_at": "Start date",
        }
        widgets = {
            "started_at": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "notes": forms.Textarea(
                attrs={"rows": 2}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configure_member_choices(
            self.fields["user"]
        )

        self.fields["community_group"].queryset = (
            CommunityGroup.objects.filter(
                is_assignable=True,
            ).order_by("name")
        )

        self.fields["started_at"].initial = timezone.localdate()

    def clean(self):
        values = super().clean()

        user = values.get("user")
        group = values.get("community_group")

        if (
            user
            and group
            and GroupMembership.objects.filter(
                user=user,
                community_group=group,
                ended_at__isnull=True,
            ).exists()
        ):
            self.add_error(
                "user",
                "This member already belongs to this community group.",
            )

        return values
