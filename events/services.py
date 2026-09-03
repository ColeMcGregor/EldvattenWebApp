from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus, User
from audit.services import record_audit_event
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
    Event,
    EventInvitation,
    EventTarget,
)


MATERIAL_EVENT_FIELDS = {
    "title": "title",
    "start_at": "start time",
    "end_at": "end time",
    "location": "location",
}


def is_member(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.MEMBER
    )


def resolve_event_target(target):
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
            return {
                target.user.id,
            }

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


def resolve_event_targets(
    event,
    purpose,
):
    resolved_user_ids = set()

    targets = event.targets.filter(
        purpose=purpose,
    )

    for target in targets:
        resolved_user_ids.update(
            resolve_event_target(target)
        )

    return resolved_user_ids


def resolve_event_invitation_targets(event):
    return resolve_event_targets(
        event,
        EventTarget.Purpose.INVITATION,
    )


def resolve_event_visibility_targets(event):
    return resolve_event_targets(
        event,
        EventTarget.Purpose.VISIBILITY,
    )


def event_target_values(target):
    return {
        "event_id": target.event_id,
        "purpose": target.purpose,
        "user_id": target.user_id,
        "citizenship_class_id": (
            target.citizenship_class_id
        ),
        "social_rank_id": target.social_rank_id,
        "office_id": target.office_id,
        "chapter_id": target.chapter_id,
        "household_id": target.household_id,
        "governance_body_id": (
            target.governance_body_id
        ),
        "order_id": target.order_id,
        "order_rank_id": target.order_rank_id,
        "community_group_id": (
            target.community_group_id
        ),
        "household_leadership_type_id": (
            target.household_leadership_type_id
        ),
    }


def event_invitation_values(invitation):
    return {
        "event_id": invitation.event_id,
        "user_id": invitation.user_id,
        "is_active": invitation.is_active,
        "invited_at": (
            invitation.invited_at.isoformat()
            if invitation.invited_at
            else None
        ),
        "uninvited_at": (
            invitation.uninvited_at.isoformat()
            if invitation.uninvited_at
            else None
        ),
    }


def target_signature(target):
    return (
        target.user_id,
        target.citizenship_class_id,
        target.social_rank_id,
        target.office_id,
        target.chapter_id,
        target.household_id,
        target.governance_body_id,
        target.order_id,
        target.order_rank_id,
        target.community_group_id,
        target.household_leadership_type_id,
    )


def event_visibility_matches_invitation_targets(
    event,
):
    invitation_targets = {
        target_signature(target)
        for target in event.targets.filter(
            purpose=EventTarget.Purpose.INVITATION,
        )
    }

    visibility_targets = {
        target_signature(target)
        for target in event.targets.filter(
            purpose=EventTarget.Purpose.VISIBILITY,
        )
    }

    return (
        event.visibility == Event.Visibility.CUSTOM
        and bool(invitation_targets)
        and invitation_targets == visibility_targets
    )


@transaction.atomic
def copy_invitation_targets_to_visibility(
    event,
):
    event.targets.filter(
        purpose=EventTarget.Purpose.VISIBILITY,
    ).delete()

    invitation_targets = event.targets.filter(
        purpose=EventTarget.Purpose.INVITATION,
    )

    for target in invitation_targets:
        visibility_target = EventTarget(
            event=event,
            purpose=EventTarget.Purpose.VISIBILITY,
            user=target.user,
            citizenship_class=target.citizenship_class,
            social_rank=target.social_rank,
            office=target.office,
            chapter=target.chapter,
            household=target.household,
            governance_body=target.governance_body,
            order=target.order,
            order_rank=target.order_rank,
            community_group=target.community_group,
            household_leadership_type=(
                target.household_leadership_type
            ),
        )

        visibility_target.full_clean()
        visibility_target.save()


def user_is_invited(
    user,
    event,
):
    if not is_member(user):
        return False

    return EventInvitation.objects.filter(
        event=event,
        user=user,
        is_active=True,
    ).exists()


def can_view_event(
    user,
    event,
):
    if (
        user.is_authenticated
        and user.id == event.organizer_id
    ):
        return True

    if (
        user.is_authenticated
        and user.has_perm("events.view_event")
    ):
        return True

    if event.visibility == Event.Visibility.PUBLIC:
        return True

    if event.visibility == Event.Visibility.MEMBERS:
        return is_member(user)

    if event.visibility != Event.Visibility.CUSTOM:
        return False

    if not is_member(user):
        return False

    visible_user_ids = resolve_event_visibility_targets(
        event
    )

    return user.id in visible_user_ids


def active_event_invitees(event):
    return User.objects.filter(
        event_invitations__event=event,
        event_invitations__is_active=True,
        account_status=AccountStatus.MEMBER,
        is_active=True,
    ).distinct()


def material_event_changes(
    old_value,
    new_value,
):
    return [
        field_name
        for field_name in MATERIAL_EVENT_FIELDS
        if old_value.get(field_name)
        != new_value.get(field_name)
    ]


def notify_event_updated(
    event,
    changed_fields,
    *,
    exclude_user_ids=None,
):
    if not changed_fields:
        return

    if event.status != Event.Status.ACTIVE:
        return

    recipients = active_event_invitees(
        event
    )

    if exclude_user_ids:
        recipients = recipients.exclude(
            id__in=exclude_user_ids,
        )

    recipients = list(recipients)

    if not recipients:
        return

    changed_labels = [
        MATERIAL_EVENT_FIELDS[field_name]
        for field_name in changed_fields
    ]

    create_notifications(
        recipients=recipients,
        notification_type=(
            Notification.Type.EVENT
        ),
        title=f"Event updated: {event.title}",
        message=(
            "Updated event details: "
            + ", ".join(changed_labels)
            + "."
        ),
        source_type="Event",
        source_id=event.id,
        target_url=reverse(
            "events:event_detail",
            args=[
                event.id,
            ],
        ),
    )


def notify_event_cancelled(event):
    recipients = list(
        active_event_invitees(
            event
        )
    )

    if not recipients:
        return

    create_notifications(
        recipients=recipients,
        notification_type=(
            Notification.Type.EVENT
        ),
        title=f"Event cancelled: {event.title}",
        message=(
            "This EldVatten event has been cancelled."
        ),
        source_type="Event",
        source_id=event.id,
        target_url=reverse(
            "events:event_detail",
            args=[
                event.id,
            ],
        ),
    )


@transaction.atomic
def sync_event_invitations(
    event,
    *,
    actor=None,
    request=None,
    source="SYSTEM",
    method="AUTOMATIC",
    send_notifications=True,
):
    resolved_user_ids = (
        resolve_event_invitation_targets(
            event
        )
    )

    existing_invitations = {
        invitation.user_id: invitation
        for invitation in EventInvitation.objects.filter(
            event=event,
        ).select_related(
            "user",
            "event",
        )
    }

    activated_invitations = []
    deactivated_invitations = []

    now = timezone.now()

    for user_id in resolved_user_ids:
        invitation = existing_invitations.get(
            user_id
        )

        if invitation is None:
            invitation = EventInvitation.objects.create(
                event=event,
                user_id=user_id,
            )

            invitation = (
                EventInvitation.objects.select_related(
                    "user",
                    "event",
                ).get(
                    id=invitation.id,
                )
            )

            record_audit_event(
                action="ASSIGN",
                target_type="EventInvitation",
                target_id=invitation.id,
                target_label=str(invitation),
                actor=actor,
                request=request,
                old_value=None,
                new_value=event_invitation_values(
                    invitation
                ),
                effective_at=invitation.invited_at,
                source=source,
                method=method,
                notes=(
                    "Event invitation created from "
                    "current invitation targets."
                ),
            )

            activated_invitations.append(
                invitation
            )

            continue

        if not invitation.is_active:
            old_value = event_invitation_values(
                invitation
            )

            invitation.is_active = True
            invitation.uninvited_at = None

            invitation.full_clean()

            invitation.save(
                update_fields=[
                    "is_active",
                    "uninvited_at",
                ]
            )

            record_audit_event(
                action="ASSIGN",
                target_type="EventInvitation",
                target_id=invitation.id,
                target_label=str(invitation),
                actor=actor,
                request=request,
                old_value=old_value,
                new_value=event_invitation_values(
                    invitation
                ),
                effective_at=now,
                source=source,
                method=method,
                notes=(
                    "Event invitation reactivated "
                    "from current invitation targets."
                ),
            )

            activated_invitations.append(
                invitation
            )

    for user_id, invitation in (
        existing_invitations.items()
    ):
        if user_id in resolved_user_ids:
            continue

        if not invitation.is_active:
            continue

        old_value = event_invitation_values(
            invitation
        )

        invitation.is_active = False
        invitation.uninvited_at = now

        invitation.full_clean()

        invitation.save(
            update_fields=[
                "is_active",
                "uninvited_at",
            ]
        )

        record_audit_event(
            action="REMOVE",
            target_type="EventInvitation",
            target_id=invitation.id,
            target_label=str(invitation),
            actor=actor,
            request=request,
            old_value=old_value,
            new_value=event_invitation_values(
                invitation
            ),
            effective_at=now,
            source=source,
            method=method,
            notes=(
                "Event invitation deactivated because "
                "the user no longer matches the current "
                "invitation targets."
            ),
        )

        deactivated_invitations.append(
            invitation
        )

    if (
        send_notifications
        and activated_invitations
    ):
        create_notifications(
            recipients=[
                invitation.user
                for invitation in activated_invitations
            ],
            notification_type=(
                Notification.Type.EVENT
            ),
            title=f"New event: {event.title}",
            message=(
                "You have been invited to an "
                "EldVatten event."
            ),
            source_type="Event",
            source_id=event.id,
            target_url=reverse(
                "events:event_detail",
                args=[
                    event.id,
                ],
            ),
        )

    return (
        activated_invitations,
        deactivated_invitations,
    )