from math import ceil

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus, User
from notifications.models import Notification
from notifications.services import create_notifications
from organization.models import (
    CitizenshipRecord,
    GovernanceMembership,
    GroupMembership,
    HouseholdLeadership,
    HouseholdMembership,
    OrderMembership,
    UserOffice,
    UserSocialRank,
)

from .models import (
    Vote,
    VoteComment,
    VoteEligibleUser,
    VoteResponse,
)


def resolve_vote_eligibility_target(target):
    user_ids = set(
        User.objects.filter(
            account_status=AccountStatus.MEMBER,
            is_active=True,
        ).values_list(
            "id",
            flat=True,
        )
    )

    if target.user is not None:
        if (
            target.user.is_active
            and target.user.account_status == AccountStatus.MEMBER
        ):
            return {target.user.id}

        return set()

    if target.citizenship_class is not None:
        matching_ids = set(
            CitizenshipRecord.objects.filter(
                citizenship_class=target.citizenship_class,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.social_rank is not None:
        matching_ids = set(
            UserSocialRank.objects.filter(
                social_rank=target.social_rank,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.office is not None:
        office_records = UserOffice.objects.filter(
            office=target.office,
            ended_at__isnull=True,
        )

        if target.chapter is not None:
            office_records = office_records.filter(
                chapter=target.chapter,
            )

        matching_ids = set(
            office_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.chapter is not None:
        matching_ids = set(
            CitizenshipRecord.objects.filter(
                chapter=target.chapter,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.household is not None:
        matching_ids = set(
            HouseholdMembership.objects.filter(
                household=target.household,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.governance_body is not None:
        matching_ids = set(
            GovernanceMembership.objects.filter(
                governance_body=target.governance_body,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.order is not None:
        order_records = OrderMembership.objects.filter(
            order=target.order,
            ended_at__isnull=True,
        )

        if target.order_rank is not None:
            order_records = order_records.filter(
                order_rank=target.order_rank,
            )

        matching_ids = set(
            order_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    elif target.order_rank is not None:
        matching_ids = set(
            OrderMembership.objects.filter(
                order_rank=target.order_rank,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.community_group is not None:
        matching_ids = set(
            GroupMembership.objects.filter(
                community_group=target.community_group,
                ended_at__isnull=True,
            ).values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    if target.household_leadership_type is not None:
        leadership_records = HouseholdLeadership.objects.filter(
            leadership_type=target.household_leadership_type,
            ended_at__isnull=True,
        )

        if target.household is not None:
            leadership_records = leadership_records.filter(
                household=target.household,
            )

        matching_ids = set(
            leadership_records.values_list(
                "user_id",
                flat=True,
            )
        )

        user_ids &= matching_ids

    return user_ids


def resolve_vote_eligibility(vote):
    eligible_user_ids = set()

    for target in vote.eligibility_targets.all():
        eligible_user_ids.update(
            resolve_vote_eligibility_target(target)
        )

    return eligible_user_ids


def preview_vote_eligibility(vote):
    user_ids = resolve_vote_eligibility(vote)

    return User.objects.filter(
        id__in=user_ids,
    ).order_by(
        "display_name",
        "username",
    )


@transaction.atomic
def open_vote(vote):
    vote = Vote.objects.select_for_update().get(
        id=vote.id,
    )

    if vote.status != Vote.Status.DRAFT:
        raise ValidationError(
            "Only a draft vote can be opened."
        )

    if not vote.options.exists():
        raise ValidationError(
            "A vote must have at least one option before it can open."
        )

    if not vote.eligibility_targets.exists():
        raise ValidationError(
            "A vote must have at least one eligibility target before it can open."
        )

    now = timezone.now()

    if vote.opens_at is not None and now < vote.opens_at:
        raise ValidationError(
            "This vote is scheduled to open later."
        )

    eligible_user_ids = resolve_vote_eligibility(vote)

    if not eligible_user_ids:
        raise ValidationError(
            "This vote does not currently have any eligible users."
        )

    VoteEligibleUser.objects.filter(
        vote=vote,
    ).delete()

    VoteEligibleUser.objects.bulk_create(
        [
            VoteEligibleUser(
                vote=vote,
                user_id=user_id,
            )
            for user_id in eligible_user_ids
        ],
        ignore_conflicts=True,
    )

    vote.status = Vote.Status.OPEN
    vote.opened_at = now
    vote.closed_at = None

    vote.full_clean()

    vote.save(
        update_fields=[
            "status",
            "opened_at",
            "closed_at",
            "updated_at",
        ]
    )

    recipients = User.objects.filter(
        id__in=eligible_user_ids,
    )

    create_notifications(
        recipients=recipients,
        notification_type=Notification.Type.VOTE,
        title=f"New vote: {vote.title}",
        message=(
            "A new vote is available for your response."
        ),
        source_type="Vote",
        source_id=vote.id,
        target_url=reverse(
            "voting:vote_detail",
            args=[
                vote.id,
            ],
        ),
    )

    return vote


def get_vote_eligibility(vote, user):
    return VoteEligibleUser.objects.filter(
        vote=vote,
        user=user,
    ).first()


def can_user_vote(vote, user):
    if not user.is_authenticated:
        return False

    if not user.is_active:
        return False

    if user.account_status != AccountStatus.MEMBER:
        return False

    if vote.status != Vote.Status.OPEN:
        return False

    now = timezone.now()

    if vote.opens_at is not None and now < vote.opens_at:
        return False

    if vote.closes_at is not None and now >= vote.closes_at:
        return False

    eligibility = VoteEligibleUser.objects.filter(
        vote=vote,
        user=user,
    ).first()

    if eligibility is None:
        return False

    if vote.is_anonymous and eligibility.has_responded:
        return False

    return True


@transaction.atomic
def submit_vote_response(
    vote,
    user,
    option,
):
    vote = Vote.objects.select_for_update().get(
        id=vote.id,
    )

    if not can_user_vote(vote, user):
        raise ValidationError(
            "You are not eligible to vote in this vote."
        )

    if option.vote_id != vote.id:
        raise ValidationError(
            "The selected option does not belong to this vote."
        )

    eligibility = (
        VoteEligibleUser.objects
        .select_for_update()
        .get(
            vote=vote,
            user=user,
        )
    )

    if vote.is_anonymous:
        if eligibility.has_responded:
            raise ValidationError(
                "You have already submitted a response to this anonymous vote."
            )

        response = VoteResponse(
            eligibility=None,
            option=option,
            submitted_at=None,
            updated_at=None,
        )

        response.full_clean()
        response.save()

        eligibility.has_responded = True
        eligibility.save(
            update_fields=[
                "has_responded",
            ]
        )

        return response, True

    now = timezone.now()

    response = VoteResponse.objects.filter(
        eligibility=eligibility,
    ).first()

    created = response is None

    if created:
        response = VoteResponse(
            eligibility=eligibility,
            option=option,
            submitted_at=now,
            updated_at=now,
        )

    else:
        response.option = option
        response.updated_at = now

    response.full_clean()
    response.save()

    if not eligibility.has_responded:
        eligibility.has_responded = True
        eligibility.save(
            update_fields=[
                "has_responded",
            ]
        )

    return response, created


def can_user_comment(vote, user):
    if not user.is_authenticated:
        return False

    if not user.is_active:
        return False

    if user.account_status != AccountStatus.MEMBER:
        return False

    if vote.status != Vote.Status.OPEN:
        return False

    now = timezone.now()

    if vote.opens_at is not None and now < vote.opens_at:
        return False

    if vote.closes_at is not None and now >= vote.closes_at:
        return False

    eligibility = VoteEligibleUser.objects.filter(
        vote=vote,
        user=user,
    ).first()

    if eligibility is None:
        return False

    if vote.is_anonymous and eligibility.has_responded:
        return False

    return True


@transaction.atomic
def submit_vote_comment(
    vote,
    user,
    body,
):
    vote = Vote.objects.select_for_update().get(
        id=vote.id,
    )

    if not can_user_comment(vote, user):
        raise ValidationError(
            "You are not eligible to comment on this vote."
        )

    cleaned_body = body.strip()

    if not cleaned_body:
        raise ValidationError(
            "A vote comment cannot be empty."
        )

    comment, created = VoteComment.objects.update_or_create(
        vote=vote,
        author=user,
        defaults={
            "body": cleaned_body,
        },
    )

    comment.full_clean()

    return comment, created


def get_vote_response_count(vote):
    return VoteResponse.objects.filter(
        option__vote=vote,
    ).count()


def get_vote_participation_count(vote):
    return VoteEligibleUser.objects.filter(
        vote=vote,
        has_responded=True,
    ).count()


def get_required_quorum_count(vote):
    eligible_count = vote.eligible_users.count()

    if not vote.requires_quorum:
        return 0

    if eligible_count == 0:
        return 0

    return ceil(
        eligible_count
        * vote.quorum_numerator
        / vote.quorum_denominator
    )


def has_vote_quorum(vote):
    if not vote.requires_quorum:
        return True

    required_count = get_required_quorum_count(vote)
    participation_count = get_vote_participation_count(vote)

    return participation_count >= required_count


def has_all_required_responses(vote):
    if not vote.requires_all_responses:
        return True

    eligible_count = vote.eligible_users.count()
    participation_count = get_vote_participation_count(vote)

    return (
        eligible_count > 0
        and participation_count == eligible_count
    )


def get_vote_tally(vote):
    tally = []

    for option in vote.options.all():
        response_count = VoteResponse.objects.filter(
            option=option,
        ).count()

        tally.append(
            {
                "option_id": option.id,
                "label": option.label,
                "response_count": response_count,
            }
        )

    return tally


def calculate_vote_result(vote):
    eligible_count = vote.eligible_users.count()
    response_count = get_vote_response_count(vote)
    quorum_required = get_required_quorum_count(vote)
    quorum_met = has_vote_quorum(vote)
    all_required_responses_received = (
        has_all_required_responses(vote)
    )

    tally = get_vote_tally(vote)

    result = {
        "eligible_count": eligible_count,
        "response_count": response_count,
        "quorum_required": quorum_required,
        "quorum_met": quorum_met,
        "all_required_responses_received": (
            all_required_responses_received
        ),
        "tally": tally,
        "winner": None,
        "has_winner": False,
        "approval_requirement_met": False,
        "reason": "",
    }

    if eligible_count == 0:
        result["reason"] = "No eligible voters."
        return result

    if not quorum_met:
        result["reason"] = "Quorum was not met."
        return result

    if not all_required_responses_received:
        result["reason"] = (
            "All required responses have not been received."
        )
        return result

    if response_count == 0:
        result["reason"] = "No responses were submitted."
        return result

    sorted_tally = sorted(
        tally,
        key=lambda item: item["response_count"],
        reverse=True,
    )

    highest_count = sorted_tally[0]["response_count"]

    highest_options = [
        item
        for item in sorted_tally
        if item["response_count"] == highest_count
    ]

    if len(highest_options) != 1:
        result["reason"] = "The vote ended in a tie."
        return result

    winner = highest_options[0]

    if vote.approval_rule == Vote.ApprovalRule.UNANIMOUS:
        if winner["response_count"] != response_count:
            result["reason"] = (
                "The vote did not reach unanimous agreement."
            )
            return result

        result["winner"] = winner
        result["has_winner"] = True
        result["approval_requirement_met"] = True
        result["reason"] = (
            "The vote reached unanimous agreement."
        )

        return result

    if vote.approval_rule == Vote.ApprovalRule.SIMPLE_MAJORITY:
        if winner["response_count"] <= response_count / 2:
            result["reason"] = (
                "No option received a simple majority."
            )
            return result

        result["winner"] = winner
        result["has_winner"] = True
        result["approval_requirement_met"] = True
        result["reason"] = (
            "An option received a simple majority."
        )

        return result

    result["reason"] = (
        "The vote does not have a supported approval rule."
    )

    return result


@transaction.atomic
def close_vote(vote):
    vote = Vote.objects.select_for_update().get(
        id=vote.id,
    )

    if vote.status != Vote.Status.OPEN:
        raise ValidationError(
            "Only an open vote can be closed."
        )

    if (
        vote.requires_all_responses
        and not has_all_required_responses(vote)
    ):
        raise ValidationError(
            "This vote requires a response from every eligible voter before it can close."
        )

    now = timezone.now()

    vote.status = Vote.Status.CLOSED
    vote.closed_at = now

    vote.full_clean()

    vote.save(
        update_fields=[
            "status",
            "closed_at",
            "updated_at",
        ]
    )

    return calculate_vote_result(vote)