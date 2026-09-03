from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import HttpResponseForbidden
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import AccountStatus, User
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import (
    AttendanceForm,
    AttendanceManagementForm,
    EventForm,
    EventTargetForm,
    RSVPForm,
)
from .models import (
    Event,
    EventParticipation,
    EventTarget,
)
from .services import (
    can_view_event,
    copy_invitation_targets_to_visibility,
    event_target_values,
    event_visibility_matches_invitation_targets,
    material_event_changes,
    notify_event_cancelled,
    notify_event_updated,
    sync_event_invitations,
    user_is_invited,
)


EventTargetFormSet = inlineformset_factory(
    Event,
    EventTarget,
    form=EventTargetForm,
    extra=1,
    can_delete=True,
)


def event_values(event):
    return {
        "title": event.title,
        "description": event.description,
        "start_at": event.start_at.isoformat(),
        "end_at": event.end_at.isoformat(),
        "location": event.location,
        "organizer": str(event.organizer),
        "visibility": event.visibility,
        "status": event.status,
    }


def participation_values(participation):
    return {
        "event": str(participation.event),
        "user": str(participation.user),
        "rsvp_status": participation.rsvp_status,
        "attendance_status": (
            participation.attendance_status
        ),
        "rsvp_updated_at": (
            participation.rsvp_updated_at.isoformat()
            if participation.rsvp_updated_at
            else None
        ),
        "attendance_recorded_at": (
            participation.attendance_recorded_at.isoformat()
            if participation.attendance_recorded_at
            else None
        ),
    }


def formset_target_count(formset):
    count = 0

    for form in formset.forms:
        if not hasattr(
            form,
            "cleaned_data",
        ):
            continue

        if not form.cleaned_data:
            continue

        if form.cleaned_data.get(
            "DELETE",
            False,
        ):
            continue

        selector_fields = (
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

        if any(
            form.cleaned_data.get(field_name)
            for field_name in selector_fields
        ):
            count += 1

    return count


def save_target_formset(
    formset,
    purpose,
):
    deleted_objects = list(
        formset.deleted_objects
    )

    targets = formset.save(
        commit=False,
    )

    for target in deleted_objects:
        target.delete()

    for target in targets:
        target.purpose = purpose
        target.full_clean()
        target.save()

    formset.save_m2m()


def target_values_by_id(
    event,
    purpose,
):
    return {
        target.id: event_target_values(target)
        for target in event.targets.filter(
            purpose=purpose,
        )
    }


def record_target_changes(
    *,
    request,
    event,
    purpose,
    old_values,
):
    current_targets = {
        target.id: target
        for target in event.targets.filter(
            purpose=purpose,
        )
    }

    for target_id, target in (
        current_targets.items()
    ):
        new_value = event_target_values(
            target
        )

        old_value = old_values.get(
            target_id
        )

        if old_value is None:
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type="EventTarget",
                target_id=target.id,
                target_label=str(target),
                old_value=None,
                new_value=new_value,
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

        elif old_value != new_value:
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type="EventTarget",
                target_id=target.id,
                target_label=str(target),
                old_value=old_value,
                new_value=new_value,
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

    for target_id, old_value in (
        old_values.items()
    ):
        if target_id in current_targets:
            continue

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type="EventTarget",
            target_id=target_id,
            target_label=(
                f"{purpose.title()} target "
                f"for {event}"
            ),
            old_value=old_value,
            new_value=None,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )


def event_list(request):
    events = Event.objects.select_related(
        "organizer",
    ).prefetch_related(
        "targets",
    )

    visible_events = [
        event
        for event in events
        if can_view_event(
            request.user,
            event,
        )
    ]

    return render(
        request,
        "events/event_list.html",
        {
            "events": visible_events,
        },
    )


def event_detail(
    request,
    event_id,
):
    event = get_object_or_404(
        Event.objects.select_related(
            "organizer",
        ).prefetch_related(
            "targets",
            "participations__user",
        ),
        pk=event_id,
    )

    if not can_view_event(
        request.user,
        event,
    ):
        return HttpResponseForbidden()

    participation = None
    rsvp_form = None
    attendance_management_form = None

    invited = user_is_invited(
        request.user,
        event,
    )

    if (
        invited
        and event.status
        == Event.Status.ACTIVE
    ):
        participation = (
            EventParticipation.objects.filter(
                event=event,
                user=request.user,
            ).first()
        )

        rsvp_form = RSVPForm(
            instance=participation,
        )

    if (
        request.user.is_authenticated
        and request.user.has_perm(
            "events.record_attendance"
        )
    ):
        attendance_management_form = (
            AttendanceManagementForm()
        )

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "participation": participation,
            "rsvp_form": rsvp_form,
            "attendance_management_form": (
                attendance_management_form
            ),
            "is_invited": invited,
        },
    )


@login_required
@transaction.atomic
def event_create(request):
    if not request.user.has_perm(
        "events.add_event"
    ):
        return HttpResponseForbidden()

    event = Event(
        organizer=request.user,
    )

    if request.method == "POST":
        form = EventForm(
            request.POST,
            instance=event,
            allow_status_change=False,
        )

        invitation_formset = (
            EventTargetFormSet(
                request.POST,
                instance=event,
                prefix="invitation",
                queryset=EventTarget.objects.none(),
            )
        )

        visibility_formset = (
            EventTargetFormSet(
                request.POST,
                instance=event,
                prefix="visibility",
                queryset=EventTarget.objects.none(),
            )
        )

        form_is_valid = form.is_valid()

        invitation_is_valid = (
            invitation_formset.is_valid()
        )

        visible_to_invited_only = False

        if form_is_valid:
            visible_to_invited_only = (
                form.cleaned_data[
                    "visible_to_invited_only"
                ]
            )

        if visible_to_invited_only:
            visibility_is_valid = True
        else:
            visibility_is_valid = (
                visibility_formset.is_valid()
            )

        if (
            form_is_valid
            and invitation_is_valid
            and visibility_is_valid
        ):
            invitation_count = (
                formset_target_count(
                    invitation_formset
                )
            )

            visibility_count = 0

            if not visible_to_invited_only:
                visibility_count = (
                    formset_target_count(
                        visibility_formset
                    )
                )

            if (
                visible_to_invited_only
                and invitation_count == 0
            ):
                form.add_error(
                    None,
                    (
                        "At least one invitation target "
                        "is required when visibility is "
                        "limited to invited users."
                    ),
                )

            elif (
                not visible_to_invited_only
                and form.cleaned_data["visibility"]
                == Event.Visibility.CUSTOM
                and visibility_count == 0
            ):
                form.add_error(
                    None,
                    (
                        "At least one visibility target "
                        "is required for custom visibility."
                    ),
                )

            else:
                event = form.save(
                    commit=False,
                )

                event.organizer = request.user
                event.status = Event.Status.ACTIVE

                if visible_to_invited_only:
                    event.visibility = (
                        Event.Visibility.CUSTOM
                    )

                event.save()

                save_target_formset(
                    invitation_formset,
                    EventTarget.Purpose.INVITATION,
                )

                if visible_to_invited_only:
                    copy_invitation_targets_to_visibility(
                        event
                    )

                elif (
                    event.visibility
                    == Event.Visibility.CUSTOM
                ):
                    save_target_formset(
                        visibility_formset,
                        EventTarget.Purpose.VISIBILITY,
                    )

                else:
                    event.targets.filter(
                        purpose=(
                            EventTarget.Purpose.VISIBILITY
                        ),
                    ).delete()

                record_audit_event(
                    actor=request.user,
                    request=request,
                    action=AuditLog.Action.CREATE,
                    target_type=(
                        event._meta.verbose_name
                    ),
                    target_id=event.pk,
                    target_label=str(event),
                    new_value=event_values(event),
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )

                record_target_changes(
                    request=request,
                    event=event,
                    purpose=(
                        EventTarget.Purpose.INVITATION
                    ),
                    old_values={},
                )

                record_target_changes(
                    request=request,
                    event=event,
                    purpose=(
                        EventTarget.Purpose.VISIBILITY
                    ),
                    old_values={},
                )

                sync_event_invitations(
                    event,
                    actor=request.user,
                    request=request,
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )

                return redirect(
                    "events:event_detail",
                    event_id=event.pk,
                )

    else:
        form = EventForm(
            instance=event,
            allow_status_change=False,
        )

        invitation_formset = EventTargetFormSet(
            instance=event,
            prefix="invitation",
            queryset=EventTarget.objects.none(),
        )

        visibility_formset = EventTargetFormSet(
            instance=event,
            prefix="visibility",
            queryset=EventTarget.objects.none(),
        )

    return render(
        request,
        "events/event_form.html",
        {
            "form": form,
            "invitation_formset": (
                invitation_formset
            ),
            "visibility_formset": (
                visibility_formset
            ),
            "page_title": "Create Event",
        },
    )


@login_required
@transaction.atomic
def event_edit(
    request,
    event_id,
):
    if not request.user.has_perm(
        "events.change_event"
    ):
        return HttpResponseForbidden()

    event = get_object_or_404(
        Event,
        pk=event_id,
    )

    old_event_value = event_values(
        event
    )

    old_invitation_targets = (
        target_values_by_id(
            event,
            EventTarget.Purpose.INVITATION,
        )
    )

    old_visibility_targets = (
        target_values_by_id(
            event,
            EventTarget.Purpose.VISIBILITY,
        )
    )

    invitation_queryset = (
        event.targets.filter(
            purpose=EventTarget.Purpose.INVITATION,
        )
    )

    visibility_queryset = (
        event.targets.filter(
            purpose=EventTarget.Purpose.VISIBILITY,
        )
    )

    if request.method == "POST":
        form = EventForm(
            request.POST,
            instance=event,
        )

        invitation_formset = EventTargetFormSet(
            request.POST,
            instance=event,
            prefix="invitation",
            queryset=invitation_queryset,
        )

        visibility_formset = EventTargetFormSet(
            request.POST,
            instance=event,
            prefix="visibility",
            queryset=visibility_queryset,
        )

        form_is_valid = form.is_valid()

        invitation_is_valid = (
            invitation_formset.is_valid()
        )

        visible_to_invited_only = False

        if form_is_valid:
            visible_to_invited_only = (
                form.cleaned_data[
                    "visible_to_invited_only"
                ]
            )

        if visible_to_invited_only:
            visibility_is_valid = True
        else:
            visibility_is_valid = (
                visibility_formset.is_valid()
            )

        if (
            form_is_valid
            and invitation_is_valid
            and visibility_is_valid
        ):
            invitation_count = (
                formset_target_count(
                    invitation_formset
                )
            )

            visibility_count = 0

            if not visible_to_invited_only:
                visibility_count = (
                    formset_target_count(
                        visibility_formset
                    )
                )

            if (
                visible_to_invited_only
                and invitation_count == 0
            ):
                form.add_error(
                    None,
                    (
                        "At least one invitation target "
                        "is required when visibility is "
                        "limited to invited users."
                    ),
                )

            elif (
                not visible_to_invited_only
                and form.cleaned_data["visibility"]
                == Event.Visibility.CUSTOM
                and visibility_count == 0
            ):
                form.add_error(
                    None,
                    (
                        "At least one visibility target "
                        "is required for custom visibility."
                    ),
                )

            else:
                event = form.save(
                    commit=False,
                )

                if visible_to_invited_only:
                    event.visibility = (
                        Event.Visibility.CUSTOM
                    )

                event.save()

                save_target_formset(
                    invitation_formset,
                    EventTarget.Purpose.INVITATION,
                )

                if visible_to_invited_only:
                    copy_invitation_targets_to_visibility(
                        event
                    )

                elif (
                    event.visibility
                    == Event.Visibility.CUSTOM
                ):
                    save_target_formset(
                        visibility_formset,
                        EventTarget.Purpose.VISIBILITY,
                    )

                else:
                    event.targets.filter(
                        purpose=(
                            EventTarget.Purpose.VISIBILITY
                        ),
                    ).delete()

                new_event_value = event_values(
                    event
                )

                changed_fields = (
                    material_event_changes(
                        old_event_value,
                        new_event_value,
                    )
                )

                was_cancelled = (
                    old_event_value["status"]
                    != Event.Status.CANCELLED
                    and event.status
                    == Event.Status.CANCELLED
                )

                if (
                    old_event_value
                    != new_event_value
                ):
                    record_audit_event(
                        actor=request.user,
                        request=request,
                        action=AuditLog.Action.UPDATE,
                        target_type=(
                            event._meta.verbose_name
                        ),
                        target_id=event.pk,
                        target_label=str(event),
                        old_value=old_event_value,
                        new_value=new_event_value,
                        source=(
                            AuditLog.Source.WEB_APP
                        ),
                        method=(
                            AuditLog.Method.MANUAL
                        ),
                    )

                record_target_changes(
                    request=request,
                    event=event,
                    purpose=(
                        EventTarget.Purpose.INVITATION
                    ),
                    old_values=(
                        old_invitation_targets
                    ),
                )

                record_target_changes(
                    request=request,
                    event=event,
                    purpose=(
                        EventTarget.Purpose.VISIBILITY
                    ),
                    old_values=(
                        old_visibility_targets
                    ),
                )

                (
                    activated_invitations,
                    _,
                ) = sync_event_invitations(
                    event,
                    actor=request.user,
                    request=request,
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                    send_notifications=(
                        event.status
                        == Event.Status.ACTIVE
                    ),
                )

                if was_cancelled:
                    notify_event_cancelled(
                        event
                    )

                elif changed_fields:
                    newly_invited_user_ids = {
                        invitation.user_id
                        for invitation
                        in activated_invitations
                    }

                    notify_event_updated(
                        event,
                        changed_fields,
                        exclude_user_ids=(
                            newly_invited_user_ids
                        ),
                    )

                return redirect(
                    "events:event_detail",
                    event_id=event.pk,
                )

    else:
        visible_to_invited_only = (
            event_visibility_matches_invitation_targets(
                event
            )
        )

        form = EventForm(
            instance=event,
            initial={
                "visible_to_invited_only": (
                    visible_to_invited_only
                ),
            },
        )

        invitation_formset = EventTargetFormSet(
            instance=event,
            prefix="invitation",
            queryset=invitation_queryset,
        )

        visibility_formset = EventTargetFormSet(
            instance=event,
            prefix="visibility",
            queryset=visibility_queryset,
        )

    return render(
        request,
        "events/event_form.html",
        {
            "form": form,
            "event": event,
            "invitation_formset": (
                invitation_formset
            ),
            "visibility_formset": (
                visibility_formset
            ),
            "page_title": "Edit Event",
        },
    )


@login_required
def event_delete(
    request,
    event_id,
):
    if not request.user.has_perm(
        "events.delete_event"
    ):
        return HttpResponseForbidden()

    event = get_object_or_404(
        Event,
        pk=event_id,
    )

    if request.method == "POST":
        old_value = event_values(event)

        target_id = event.pk
        target_label = str(event)
        target_type = event._meta.verbose_name

        event.delete()

        record_audit_event(
            actor=request.user,
            request=request,
            action=AuditLog.Action.DELETE,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            old_value=old_value,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        return redirect(
            "events:event_list"
        )

    return render(
        request,
        "events/event_confirm_delete.html",
        {
            "event": event,
        },
    )


@login_required
@require_POST
def update_rsvp(
    request,
    event_id,
):
    event = get_object_or_404(
        Event,
        pk=event_id,
    )

    if (
        event.status
        == Event.Status.CANCELLED
    ):
        return HttpResponseForbidden()

    if not user_is_invited(
        request.user,
        event,
    ):
        return HttpResponseForbidden()

    if not can_view_event(
        request.user,
        event,
    ):
        return HttpResponseForbidden()

    participation = (
        EventParticipation.objects.filter(
            event=event,
            user=request.user,
        ).first()
    )

    old_value = (
        participation_values(
            participation
        )
        if participation
        else None
    )

    form = RSVPForm(
        request.POST,
        instance=participation,
    )

    if form.is_valid():
        participation = form.save(
            commit=False,
        )

        participation.event = event
        participation.user = request.user
        participation.rsvp_updated_at = (
            timezone.now()
        )

        participation.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if old_value
                else AuditLog.Action.CREATE
            ),
            target_type=(
                participation._meta.verbose_name
            ),
            target_id=participation.pk,
            target_label=str(participation),
            old_value=old_value,
            new_value=participation_values(
                participation
            ),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "events:event_detail",
        event_id=event.pk,
    )


@login_required
@require_POST
def update_attendance(
    request,
    event_id,
    user_id,
):
    if not request.user.has_perm(
        "events.record_attendance"
    ):
        return HttpResponseForbidden()

    event = get_object_or_404(
        Event,
        pk=event_id,
    )

    user = get_object_or_404(
        User,
        pk=user_id,
        account_status=AccountStatus.MEMBER,
    )

    participation = (
        EventParticipation.objects.filter(
            event=event,
            user=user,
        ).first()
    )

    old_value = (
        participation_values(
            participation
        )
        if participation
        else None
    )

    form = AttendanceForm(
        request.POST,
        instance=participation,
    )

    if form.is_valid():
        participation = form.save(
            commit=False,
        )

        participation.event = event
        participation.user = user
        participation.attendance_recorded_at = (
            timezone.now()
        )

        participation.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if old_value
                else AuditLog.Action.CREATE
            ),
            target_type=(
                participation._meta.verbose_name
            ),
            target_id=participation.pk,
            target_label=str(participation),
            old_value=old_value,
            new_value=participation_values(
                participation
            ),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "events:event_detail",
        event_id=event.pk,
    )


@login_required
@require_POST
def record_attendance(
    request,
    event_id,
):
    if not request.user.has_perm(
        "events.record_attendance"
    ):
        return HttpResponseForbidden()

    event = get_object_or_404(
        Event,
        pk=event_id,
    )

    form = AttendanceManagementForm(
        request.POST
    )

    if form.is_valid():
        user = form.cleaned_data[
            "user"
        ]

        attendance_status = (
            form.cleaned_data[
                "attendance_status"
            ]
        )

        participation = (
            EventParticipation.objects.filter(
                event=event,
                user=user,
            ).first()
        )

        old_value = (
            participation_values(
                participation
            )
            if participation
            else None
        )

        if participation is None:
            participation = (
                EventParticipation(
                    event=event,
                    user=user,
                )
            )

        participation.attendance_status = (
            attendance_status
        )

        participation.attendance_recorded_at = (
            timezone.now()
        )

        participation.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if old_value
                else AuditLog.Action.CREATE
            ),
            target_type=(
                participation._meta.verbose_name
            ),
            target_id=participation.pk,
            target_label=str(participation),
            old_value=old_value,
            new_value=participation_values(
                participation
            ),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "events:event_detail",
        event_id=event.pk,
    )