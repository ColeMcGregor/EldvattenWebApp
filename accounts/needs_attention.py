from django.db.models import Exists, F, OuterRef, Q
from django.urls import reverse
from django.utils import timezone

from actions.models import ActionAssignment
from events.models import (
    Event,
    EventInvitation,
    EventParticipation,
)
from voting.models import Vote, VoteEligibleUser


def get_action_attention_items(user):
    assignments = (
        ActionAssignment.objects
        .filter(
            user=user,
            is_active=True,
        )
        .exclude(
            status=ActionAssignment.Status.COMPLETED,
        )
        .select_related("action")
        .order_by(
            F("action__deadline").asc(
                nulls_last=True,
            ),
            "-assigned_at",
        )
    )

    items = []

    for assignment in assignments:
        items.append(
            {
                "type": "action",
                "type_label": "Action",
                "title": assignment.action.title,
                "status_text":
                    assignment.get_status_display(),
                "date_label": (
                    "Due"
                    if assignment.action.deadline
                    else ""
                ),
                "attention_date":
                    assignment.action.deadline,
                "target_url": reverse(
                    "actions:detail",
                    kwargs={
                        "action_id":
                            assignment.action_id,
                    },
                ),
            }
        )

    return items


def get_vote_attention_items(user):
    now = timezone.now()

    eligibilities = (
        VoteEligibleUser.objects
        .filter(
            user=user,
            has_responded=False,
            vote__status=Vote.Status.OPEN,
        )
        .filter(
            Q(vote__opens_at__isnull=True)
            | Q(vote__opens_at__lte=now)
        )
        .filter(
            Q(vote__closes_at__isnull=True)
            | Q(vote__closes_at__gt=now)
        )
        .select_related("vote")
        .order_by(
            F("vote__closes_at").asc(
                nulls_last=True,
            ),
            "-vote__opened_at",
        )
    )

    items = []

    for eligibility in eligibilities:
        items.append(
            {
                "type": "vote",
                "type_label": "Vote",
                "title": eligibility.vote.title,
                "status_text": "Response required",
                "date_label": (
                    "Closes"
                    if eligibility.vote.closes_at
                    else ""
                ),
                "attention_date":
                    eligibility.vote.closes_at,
                "target_url": reverse(
                    "voting:vote_detail",
                    kwargs={
                        "vote_id":
                            eligibility.vote_id,
                    },
                ),
            }
        )

    return items


def get_event_attention_items(user):
    now = timezone.now()

    participation_with_rsvp = (
        EventParticipation.objects
        .filter(
            event_id=OuterRef("event_id"),
            user=user,
        )
        .exclude(
            rsvp_status="",
        )
    )

    invitations = (
        EventInvitation.objects
        .filter(
            user=user,
            is_active=True,
            event__status=Event.Status.ACTIVE,
            event__start_at__gte=now,
        )
        .annotate(
            has_rsvp=Exists(
                participation_with_rsvp,
            )
        )
        .filter(
            has_rsvp=False,
        )
        .select_related("event")
        .order_by(
            "event__start_at",
            "-invited_at",
        )
    )

    items = []

    for invitation in invitations:
        items.append(
            {
                "type": "event",
                "type_label": "Event",
                "title": invitation.event.title,
                "status_text": "RSVP requested",
                "date_label": "Starts",
                "attention_date":
                    invitation.event.start_at,
                "target_url": reverse(
                    "events:event_detail",
                    kwargs={
                        "event_id":
                            invitation.event_id,
                    },
                ),
            }
        )

    return items


def get_needs_attention_items(user):
    items = []

    items.extend(
        get_action_attention_items(user)
    )

    items.extend(
        get_vote_attention_items(user)
    )

    items.extend(
        get_event_attention_items(user)
    )

    dated_items = [
        item
        for item in items
        if item["attention_date"] is not None
    ]

    undated_items = [
        item
        for item in items
        if item["attention_date"] is None
    ]

    dated_items.sort(
        key=lambda item: item["attention_date"]
    )

    return dated_items + undated_items