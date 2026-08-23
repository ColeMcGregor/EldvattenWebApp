from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import AccountStatus, User
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import (
    AttendanceForm,
    AttendanceManagementForm,
    EventForm,
    RSVPForm,
)
from .models import Event, EventParticipation


def is_member(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.account_status == AccountStatus.MEMBER
    )


def can_view_event(user, event):
    if event.visibility == Event.Visibility.PUBLIC:
        return True

    if is_member(user):
        return True

    return (
        user.is_authenticated
        and user.has_perm("events.view_event")
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
    }


def participation_values(participation):
    return {
        "event": str(participation.event),
        "user": str(participation.user),
        "rsvp_status": participation.rsvp_status,
        "attendance_status": participation.attendance_status,
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


def event_list(request):
    if (
        is_member(request.user)
        or (
            request.user.is_authenticated
            and request.user.has_perm("events.view_event")
        )
    ):
        events = Event.objects.all()
    else:
        events = Event.objects.filter(
            visibility=Event.Visibility.PUBLIC
        )

    return render(
        request,
        "events/event_list.html",
        {
            "events": events,
        },
    )


def event_detail(request, event_id):
    event = get_object_or_404(Event, pk=event_id)

    if not can_view_event(request.user, event):
        return HttpResponseForbidden()

    participation = None
    rsvp_form = None
    attendance_management_form = None

    if is_member(request.user):
        participation = EventParticipation.objects.filter(
            event=event,
            user=request.user,
        ).first()

        rsvp_form = RSVPForm(instance=participation)

    if (
        request.user.is_authenticated
        and request.user.has_perm("events.record_attendance")
    ):
        attendance_management_form = AttendanceManagementForm()

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "participation": participation,
            "rsvp_form": rsvp_form,
            "attendance_management_form": attendance_management_form,
        },
    )


@login_required
def event_create(request):
    if not request.user.has_perm("events.add_event"):
        return HttpResponseForbidden()

    if request.method == "POST":
        form = EventForm(request.POST)

        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.CREATE,
                target_type=event._meta.verbose_name,
                target_id=event.pk,
                target_label=str(event),
                new_value=event_values(event),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            return redirect(
                "events:event_detail",
                event_id=event.pk,
            )
    else:
        form = EventForm()

    return render(
        request,
        "events/event_form.html",
        {
            "form": form,
            "page_title": "Create Event",
        },
    )


@login_required
def event_edit(request, event_id):
    if not request.user.has_perm("events.change_event"):
        return HttpResponseForbidden()

    event = get_object_or_404(Event, pk=event_id)
    old_value = event_values(event)

    if request.method == "POST":
        form = EventForm(
            request.POST,
            instance=event,
        )

        if form.is_valid():
            event = form.save()

            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type=event._meta.verbose_name,
                target_id=event.pk,
                target_label=str(event),
                old_value=old_value,
                new_value=event_values(event),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            return redirect(
                "events:event_detail",
                event_id=event.pk,
            )
    else:
        form = EventForm(instance=event)

    return render(
        request,
        "events/event_form.html",
        {
            "form": form,
            "event": event,
            "page_title": "Edit Event",
        },
    )


@login_required
def event_delete(request, event_id):
    if not request.user.has_perm("events.delete_event"):
        return HttpResponseForbidden()

    event = get_object_or_404(Event, pk=event_id)

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

        return redirect("events:event_list")

    return render(
        request,
        "events/event_confirm_delete.html",
        {
            "event": event,
        },
    )


@login_required
@require_POST
def update_rsvp(request, event_id):
    if not is_member(request.user):
        return HttpResponseForbidden()

    event = get_object_or_404(Event, pk=event_id)

    if not can_view_event(request.user, event):
        return HttpResponseForbidden()

    participation = EventParticipation.objects.filter(
        event=event,
        user=request.user,
    ).first()

    old_value = (
        participation_values(participation)
        if participation
        else None
    )

    form = RSVPForm(
        request.POST,
        instance=participation,
    )

    if form.is_valid():
        participation = form.save(commit=False)
        participation.event = event
        participation.user = request.user
        participation.rsvp_updated_at = timezone.now()
        participation.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if old_value
                else AuditLog.Action.CREATE
            ),
            target_type=participation._meta.verbose_name,
            target_id=participation.pk,
            target_label=str(participation),
            old_value=old_value,
            new_value=participation_values(participation),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "events:event_detail",
        event_id=event.pk,
    )


@login_required
@require_POST
def update_attendance(request, event_id, user_id):
    if not request.user.has_perm("events.record_attendance"):
        return HttpResponseForbidden()

    event = get_object_or_404(Event, pk=event_id)

    user = get_object_or_404(
        User,
        pk=user_id,
        account_status=AccountStatus.MEMBER,
    )

    participation = EventParticipation.objects.filter(
        event=event,
        user=user,
    ).first()

    old_value = (
        participation_values(participation)
        if participation
        else None
    )

    form = AttendanceForm(
        request.POST,
        instance=participation,
    )

    if form.is_valid():
        participation = form.save(commit=False)
        participation.event = event
        participation.user = user
        participation.attendance_recorded_at = timezone.now()
        participation.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if old_value
                else AuditLog.Action.CREATE
            ),
            target_type=participation._meta.verbose_name,
            target_id=participation.pk,
            target_label=str(participation),
            old_value=old_value,
            new_value=participation_values(participation),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "events:event_detail",
        event_id=event.pk,
    )


@login_required
@require_POST
def record_attendance(request, event_id):
    if not request.user.has_perm("events.record_attendance"):
        return HttpResponseForbidden()

    event = get_object_or_404(Event, pk=event_id)
    form = AttendanceManagementForm(request.POST)

    if form.is_valid():
        user = form.cleaned_data["user"]
        attendance_status = form.cleaned_data["attendance_status"]

        participation = EventParticipation.objects.filter(
            event=event,
            user=user,
        ).first()

        old_value = (
            participation_values(participation)
            if participation
            else None
        )

        if participation is None:
            participation = EventParticipation(
                event=event,
                user=user,
            )

        participation.attendance_status = attendance_status
        participation.attendance_recorded_at = timezone.now()
        participation.save()

        record_audit_event(
            actor=request.user,
            request=request,
            action=(
                AuditLog.Action.UPDATE
                if old_value
                else AuditLog.Action.CREATE
            ),
            target_type=participation._meta.verbose_name,
            target_id=participation.pk,
            target_label=str(participation),
            old_value=old_value,
            new_value=participation_values(participation),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    return redirect(
        "events:event_detail",
        event_id=event.pk,
    )