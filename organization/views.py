from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from administration.permissions import (
    has_any_permission,
    has_permission_prefix,
)
from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import (
    ChapterForm,
    HouseholdForm,
    CitizenshipClassForm,
    SocialRankForm,
    CitizenshipAssignmentForm,
    SocialRankAssignmentForm,
    OfficeForm,
    GovernanceBodyForm,
    OfficeAssignmentForm,
    GovernanceMembershipForm,
    OrderForm,
    OrderRankForm,
    OrderMembershipForm,
    CommunityGroupForm,
    GroupMembershipForm,
)
from .models import (
    Chapter,
    ChapterStatus,
    CitizenshipRecord,
    Household,
    HouseholdMembership,
    HouseholdLeadership,
    UserOffice,
    CitizenshipClass,
    SocialRank,
    UserSocialRank,
    Office,
    GovernanceBody,
    GovernanceMembership,
    Order,
    OrderRank,
    OrderMembership,
    CommunityGroup,
    GroupMembership,
)


ORGANIZATION_MANAGEMENT_PERMISSION_PREFIXES = (
    "organization.add_",
    "organization.change_",
)


def can_view_chapters(user):
    return has_any_permission(
        user,
        (
            "organization.view_chapter",
            "organization.add_chapter",
            "organization.change_chapter",
        ),
    )


def can_edit_chapters(user):
    return has_any_permission(
        user,
        ("organization.change_chapter",),
    )


def chapter_audit_values(chapter):
    return {
        "name": chapter.name,
        "description": chapter.description,
        "status": chapter.status.name,
    }


@login_required
def organization_index(request):
    if not has_permission_prefix(
        request.user,
        ORGANIZATION_MANAGEMENT_PERMISSION_PREFIXES,
    ):
        raise PermissionDenied

    return render(
        request,
        "administration/organization_index.html",
    )


@login_required
@require_http_methods(["GET", "POST"])
def chapter_manage(request):
    can_add = has_any_permission(
        request.user,
        ("organization.add_chapter",),
    )

    can_edit = can_edit_chapters(request.user)

    if not can_view_chapters(request.user):
        raise PermissionDenied

    manage_url = reverse(
        "organization:chapter_manage",
    )

    search = request.GET.get(
        "search",
        "",
    ).strip()[:150]

    status = request.GET.get(
        "status",
        "",
    ).strip()

    action = request.GET.get(
        "action",
        "",
    ).strip()

    edit_id = request.GET.get(
        "edit",
        "",
    ).strip()

    form = None
    form_mode = None
    form_action = ""
    chapter = None
    old_value = None

    if action == "create":
        if not can_add:
            raise PermissionDenied

        form_mode = "create"
        form_action = (
            f"{manage_url}?action=create"
        )

    elif edit_id:
        if not can_edit:
            raise PermissionDenied

        chapter = get_object_or_404(
            Chapter.objects.select_related("status"),
            pk=edit_id,
        )

        form_mode = "edit"
        form_action = (
            f"{manage_url}?edit={chapter.pk}"
        )

        old_value = chapter_audit_values(
            chapter,
        )

    if request.method == "POST":
        if form_mode is None:
            raise PermissionDenied

        form = ChapterForm(
            request.POST,
            instance=chapter,
        )

        if form.is_valid():
            saved_chapter = form.save()

            record_audit_event(
                actor=request.user,
                request=request,
                action=(
                    AuditLog.Action.UPDATE
                    if chapter is not None
                    else AuditLog.Action.CREATE
                ),
                target_type="chapter",
                target_id=saved_chapter.pk,
                target_label=saved_chapter.name,
                old_value=old_value,
                new_value=chapter_audit_values(
                    saved_chapter,
                ),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            messages.success(
                request,
                (
                    "Chapter updated successfully."
                    if chapter is not None
                    else "Chapter created successfully."
                ),
            )

            return redirect(
                "organization:chapter_manage",
            )

    elif form_mode:
        form = ChapterForm(
            instance=chapter,
        )

    chapters = Chapter.objects.select_related(
        "status",
    ).all()

    if search:
        chapters = chapters.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
        )

    if status:
        if ChapterStatus.objects.filter(
            pk=status,
        ).exists():
            chapters = chapters.filter(
                status_id=status,
            )
        else:
            status = ""

    chapters = chapters.order_by(
        "name",
        "pk",
    )

    paginator = Paginator(
        chapters,
        25,
    )

    page = paginator.get_page(
        request.GET.get("page"),
    )

    records = []

    for item in page.object_list:
        records.append({
            "name": item.name,
            "status_label": item.status.name,
            "description": item.description,
            "detail_url": reverse(
                "organization:chapter_detail",
                kwargs={
                    "chapter_id": item.pk,
                },
            ),
            "can_edit": can_edit,
            "edit_url": (
                f"{manage_url}?edit={item.pk}"
                if can_edit
                else ""
            ),
        })

    status_filters = []

    for chapter_status in ChapterStatus.objects.order_by(
        "name",
    ):
        status_filters.append({
            "value": str(chapter_status.pk),
            "label": chapter_status.name,
            "selected": (
                status == str(chapter_status.pk)
            ),
        })

    query_parameters = request.GET.copy()

    for parameter in (
        "page",
        "action",
        "edit",
    ):
        query_parameters.pop(
            parameter,
            None,
        )

    return render(
        request,
        "administration/organization_manage.html",
        {
            "title": "Chapters",
            "singular_title": "Chapter",
            "description": (
                "Manage EldVatten chapters, "
                "their descriptions, and statuses."
            ),
            "manage_url": manage_url,
            "create_url": (
                f"{manage_url}?action=create"
            ),
            "can_add": can_add,
            "can_edit": can_edit,
            "form": form,
            "form_mode": form_mode,
            "form_action": form_action,
            "records": records,
            "page": page,
            "search": search,
            "status_filters": status_filters,
            "filter_query": (
                query_parameters.urlencode()
            ),
            "tabs": [],
        },
    )


@login_required
@require_http_methods(["GET"])
def chapter_detail(request, chapter_id):
    if not can_view_chapters(request.user):
        raise PermissionDenied

    chapter = get_object_or_404(
        Chapter.objects.select_related(
            "status",
        ),
        pk=chapter_id,
    )

    manage_url = reverse(
        "organization:chapter_manage",
    )

    can_edit = can_edit_chapters(
        request.user,
    )

    citizenship_records = list(
        CitizenshipRecord.objects.filter(
            chapter=chapter,
        ).select_related(
            "user",
            "citizenship_class",
        ).order_by(
            "user__username",
            "-started_at",
        )
    )

    office_records = list(
        UserOffice.objects.filter(
            chapter=chapter,
        ).select_related(
            "user",
            "office",
        ).order_by(
            "office__name",
            "user__username",
            "-started_at",
        )
    )

    current_citizens = []
    former_citizens = []
    current_officers = []
    former_officers = []

    for record in citizenship_records:
        item = {
            "name": record.user.community_name,
            "details": record.citizenship_class.name,
            "started_at": record.started_at,
            "ended_at": record.ended_at,
        }

        if record.ended_at is None:
            current_citizens.append(item)
        else:
            former_citizens.append(item)

    for record in office_records:
        item = {
            "name": record.user.community_name,
            "details": record.office.name,
            "started_at": record.started_at,
            "ended_at": record.ended_at,
        }

        if record.ended_at is None:
            current_officers.append(item)
        else:
            former_officers.append(item)

    fields = [
        {
            "label": "Name",
            "value": chapter.name,
        },
        {
            "label": "Description",
            "value": chapter.description or "Not provided",
        },
        {
            "label": "Status",
            "value": chapter.status.name,
        },
        {
            "label": "Accepting New Citizens",
            "value": (
                "Yes"
                if chapter.status.allows_new_citizens
                else "No"
            ),
        },
        {
            "label": "Created",
            "value": chapter.created_at,
        },
        {
            "label": "Last Updated",
            "value": chapter.updated_at,
        },
    ]

    sections = [
        {
            "title": "Current Officers",
            "description": (
                "Members currently holding "
                "chapter offices."
            ),
            "count": len(current_officers),
            "items": current_officers,
            "empty_message": (
                "No current officers recorded."
            ),
        },
        {
            "title": "Current Citizens",
            "description": (
                "Members currently associated "
                "with this chapter through "
                "their citizenship records."
            ),
            "count": len(current_citizens),
            "items": current_citizens,
            "empty_message": (
                "No current citizens recorded."
            ),
        },
        {
            "title": "Former Officers",
            "description": (
                "Historical chapter officer "
                "appointments."
            ),
            "count": len(former_officers),
            "items": former_officers,
            "empty_message": (
                "No former officers recorded."
            ),
        },
        {
            "title": "Former Citizens",
            "description": (
                "Historical chapter "
                "citizenship records."
            ),
            "count": len(former_citizens),
            "items": former_citizens,
            "empty_message": (
                "No former citizens recorded."
            ),
        },
    ]

    return render(
        request,
        "administration/organization_detail.html",
        {
            "title": "Chapters",
            "singular_title": "Chapter",
            "record": chapter,
            "description": (
                "Chapter information, current "
                "membership, leadership, "
                "and historical assignments."
            ),
            "manage_url": manage_url,
            "can_edit": can_edit,
            "edit_url": (
                f"{manage_url}?edit={chapter.pk}"
                if can_edit
                else ""
            ),
            "fields": fields,
            "sections": sections,
        },
    )


def can_view_households(user):
    return has_any_permission(
        user,
        (
            "organization.view_household",
            "organization.add_household",
            "organization.change_household",
        ),
    )


def can_edit_households(user):
    return has_any_permission(
        user,
        ("organization.change_household",),
    )


def household_audit_values(household):
    return {
        "name": household.name,
        "description": household.description,
        "is_assignable": household.is_assignable,
    }


@login_required
@require_http_methods(["GET", "POST"])
def household_manage(request):
    can_add = has_any_permission(
        request.user,
        ("organization.add_household",),
    )
    can_edit = can_edit_households(request.user)

    if not can_view_households(request.user):
        raise PermissionDenied

    manage_url = reverse("organization:household_manage")
    search = request.GET.get("search", "").strip()[:150]
    status = request.GET.get("status", "").strip()
    action = request.GET.get("action", "").strip()
    edit_id = request.GET.get("edit", "").strip()

    form = None
    form_mode = None
    form_action = ""
    household = None
    old_value = None

    if action == "create":
        if not can_add:
            raise PermissionDenied
        form_mode = "create"
        form_action = f"{manage_url}?action=create"

    elif edit_id:
        if not can_edit:
            raise PermissionDenied
        household = get_object_or_404(Household, pk=edit_id)
        form_mode = "edit"
        form_action = f"{manage_url}?edit={household.pk}"
        old_value = household_audit_values(household)

    if request.method == "POST":
        if form_mode is None:
            raise PermissionDenied

        form = HouseholdForm(request.POST, instance=household)
        if form.is_valid():
            saved_household = form.save()
            record_audit_event(
                actor=request.user,
                request=request,
                action=(
                    AuditLog.Action.UPDATE
                    if household is not None
                    else AuditLog.Action.CREATE
                ),
                target_type="household",
                target_id=saved_household.pk,
                target_label=saved_household.name,
                old_value=old_value,
                new_value=household_audit_values(saved_household),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )
            messages.success(
                request,
                (
                    "Household updated successfully."
                    if household is not None
                    else "Household created successfully."
                ),
            )
            return redirect("organization:household_manage")

    elif form_mode:
        form = HouseholdForm(instance=household)

    households = Household.objects.all()
    if search:
        households = households.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
        )

    if status == "assignable":
        households = households.filter(is_assignable=True)
    elif status == "unavailable":
        households = households.filter(is_assignable=False)
    else:
        status = ""

    page = Paginator(
        households.order_by("name", "pk"),
        25,
    ).get_page(request.GET.get("page"))

    records = [
        {
            "name": item.name,
            "status_label": (
                "Available for assignments"
                if item.is_assignable
                else "Not accepting new assignments"
            ),
            "description": item.description,
            "detail_url": reverse(
                "organization:household_detail",
                kwargs={"household_id": item.pk},
            ),
            "can_edit": can_edit,
            "edit_url": (
                f"{manage_url}?edit={item.pk}"
                if can_edit else ""
            ),
        }
        for item in page.object_list
    ]

    query_parameters = request.GET.copy()
    for parameter in ("page", "action", "edit"):
        query_parameters.pop(parameter, None)

    return render(
        request,
        "administration/organization_manage.html",
        {
            "title": "Households",
            "singular_title": "Household",
            "description": (
                "Manage EldVatten households and their "
                "availability for new assignments."
            ),
            "manage_url": manage_url,
            "create_url": f"{manage_url}?action=create",
            "can_add": can_add,
            "can_edit": can_edit,
            "form": form,
            "form_mode": form_mode,
            "form_action": form_action,
            "records": records,
            "page": page,
            "search": search,
            "status_filters": [
                {
                    "value": "assignable",
                    "label": "Available for assignments",
                    "selected": status == "assignable",
                },
                {
                    "value": "unavailable",
                    "label": "Not accepting new assignments",
                    "selected": status == "unavailable",
                },
            ],
            "filter_query": query_parameters.urlencode(),
            "tabs": [],
        },
    )


@login_required
@require_http_methods(["GET"])
def household_detail(request, household_id):
    if not can_view_households(request.user):
        raise PermissionDenied

    household = get_object_or_404(Household, pk=household_id)
    manage_url = reverse("organization:household_manage")
    can_edit = can_edit_households(request.user)

    memberships = HouseholdMembership.objects.filter(
        household=household,
    ).select_related("user").order_by(
        "user__username", "-started_at",
    )
    leaderships = HouseholdLeadership.objects.filter(
        household=household,
    ).select_related(
        "user", "leadership_type",
    ).order_by(
        "leadership_type__name", "user__username", "-started_at",
    )

    current_members = []
    former_members = []
    current_leaders = []
    former_leaders = []

    for record in memberships:
        item = {
            "name": record.user.community_name,
            "details": "Household member",
            "started_at": record.started_at,
            "ended_at": record.ended_at,
        }
        if record.ended_at is None:
            current_members.append(item)
        else:
            former_members.append(item)

    for record in leaderships:
        item = {
            "name": record.user.community_name,
            "details": record.leadership_type.name,
            "started_at": record.started_at,
            "ended_at": record.ended_at,
        }
        if record.ended_at is None:
            current_leaders.append(item)
        else:
            former_leaders.append(item)

    sections = [
        {
            "title": "Current Leadership",
            "description": "Current household leadership assignments.",
            "count": len(current_leaders),
            "items": current_leaders,
            "empty_message": "No current leaders recorded.",
        },
        {
            "title": "Current Members",
            "description": "Current household memberships.",
            "count": len(current_members),
            "items": current_members,
            "empty_message": "No current members recorded.",
        },
        {
            "title": "Former Leadership",
            "description": "Historical household leadership assignments.",
            "count": len(former_leaders),
            "items": former_leaders,
            "empty_message": "No former leaders recorded.",
        },
        {
            "title": "Former Members",
            "description": "Historical household memberships.",
            "count": len(former_members),
            "items": former_members,
            "empty_message": "No former members recorded.",
        },
    ]

    return render(
        request,
        "administration/organization_detail.html",
        {
            "title": "Households",
            "singular_title": "Household",
            "record": household,
            "description": (
                "Household information, current members, "
                "leadership, and historical assignments."
            ),
            "manage_url": manage_url,
            "can_edit": can_edit,
            "edit_url": (
                f"{manage_url}?edit={household.pk}"
                if can_edit else ""
            ),
            "fields": [
                {"label": "Name", "value": household.name},
                {
                    "label": "Description",
                    "value": household.description or "Not provided",
                },
                {
                    "label": "Available for New Assignments",
                    "value": "Yes" if household.is_assignable else "No",
                },
                {"label": "Created", "value": household.created_at},
                {"label": "Last Updated", "value": household.updated_at},
            ],
            "sections": sections,
        },
    )


# Citizenship classes and social ranks share the same management layout, but
# remain separate models with distinct assignment history and permissions.
def organization_definition_manage(
    request, *, model, form_class, assignment_model, assignment_form_class,
    route_name, title, singular_title, assignment_title,
    assignment_fields, tabs=None, detail_route=None, detail_kwarg=None,
    extra_definition_fields=(),
):
    model_name = model._meta.model_name
    assignment_name = assignment_model._meta.model_name
    can_add = has_any_permission(request.user, (f"organization.add_{model_name}",))
    can_edit = has_any_permission(request.user, (f"organization.change_{model_name}",))
    can_view = has_any_permission(request.user, (f"organization.view_{model_name}",))
    can_assign = has_any_permission(request.user, (f"organization.add_{assignment_name}",))
    can_end = has_any_permission(request.user, (f"organization.change_{assignment_name}",))
    can_view_assignments = has_any_permission(
        request.user,
        (
            f"organization.view_{assignment_name}",
            f"organization.add_{assignment_name}",
            f"organization.change_{assignment_name}",
        ),
    )
    if not (can_add or can_edit or can_view or can_view_assignments):
        raise PermissionDenied

    manage_url = reverse(route_name)
    search = request.GET.get("search", "").strip()[:150]
    status = request.GET.get("status", "").strip()
    action = request.GET.get("action", "").strip()
    edit_id = request.GET.get("edit", "").strip()
    show_assignment_form = request.GET.get("assignment") == "create"

    instance = None
    form = None
    form_mode = None
    form_action = ""
    old_values = None
    assignment_form = None

    if action == "create":
        if not can_add:
            raise PermissionDenied
        form_mode = "create"
        form_action = f"{manage_url}?action=create"
    elif edit_id:
        if not can_edit:
            raise PermissionDenied
        instance = get_object_or_404(model, pk=edit_id)
        old_values = {
            "name": instance.name,
            "description": instance.description,
            "is_assignable": instance.is_assignable,
            **{field: getattr(instance, field) for field in extra_definition_fields},
        }
        form_mode = "edit"
        form_action = f"{manage_url}?edit={instance.pk}"

    if show_assignment_form and not can_assign:
        raise PermissionDenied

    if request.method == "POST" and request.POST.get("operation") == "assign":
        if not can_assign:
            raise PermissionDenied
        assignment_form = assignment_form_class(request.POST)
        show_assignment_form = True
        if assignment_form.is_valid():
            assignment = assignment_form.save(commit=False)
            assignment.changed_by = request.user
            assignment.save()
            audit_values = {
                "user_id": assignment.user_id,
                "started_at": assignment.started_at.isoformat(),
                "notes": assignment.notes,
            }
            for field in assignment_fields:
                audit_values[f"{field}_id"] = getattr(assignment, f"{field}_id")
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.ASSIGN,
                target_type=assignment_model._meta.verbose_name,
                target_id=assignment.pk,
                target_label=str(assignment),
                new_value=audit_values,
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )
            messages.success(request, f"{assignment_title} recorded.")
            return redirect(manage_url)

    elif request.method == "POST" and request.POST.get("operation") == "end":
        if not can_end:
            raise PermissionDenied
        assignment = get_object_or_404(
            assignment_model.objects.select_related("user"),
            pk=request.POST.get("assignment_id"),
            ended_at__isnull=True,
        )
        today = timezone.localdate()
        if assignment.started_at > today:
            messages.error(
                request,
                "Cannot end a future-dated assignment. Correct its start date first.",
            )
        else:
            assignment.ended_at = today
            assignment.changed_by = request.user
            assignment.save(update_fields=["ended_at", "changed_by", "updated_at"])
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.REMOVE,
                target_type=assignment_model._meta.verbose_name,
                target_id=assignment.pk,
                target_label=str(assignment),
                old_value={"ended_at": None},
                new_value={"ended_at": today.isoformat()},
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )
            messages.success(request, f"{assignment_title} ended. The history was preserved.")
        return redirect(manage_url)

    elif request.method == "POST":
        if form_mode is None:
            raise PermissionDenied
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            record_audit_event(
                actor=request.user,
                request=request,
                action=AuditLog.Action.UPDATE if instance is not None else AuditLog.Action.CREATE,
                target_type=model._meta.verbose_name,
                target_id=saved.pk,
                target_label=saved.name,
                old_value=old_values,
                new_value={
                    "name": saved.name,
                    "description": saved.description,
                    "is_assignable": saved.is_assignable,
                    **{field: getattr(saved, field) for field in extra_definition_fields},
                },
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )
            messages.success(
                request,
                f"{singular_title} {'updated' if instance is not None else 'created'} successfully.",
            )
            return redirect(manage_url)

    elif form_mode:
        form = form_class(instance=instance)

    if show_assignment_form and assignment_form is None:
        assignment_form = assignment_form_class()

    definitions = model.objects.all()
    if search:
        definitions = definitions.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )
    if status == "assignable":
        definitions = definitions.filter(is_assignable=True)
    elif status == "unavailable":
        definitions = definitions.filter(is_assignable=False)
    else:
        status = ""
    page = Paginator(definitions.order_by("name", "pk"), 25).get_page(
        request.GET.get("page")
    )
    records = [
        {
            "name": item.name,
            "status_label": "Available for assignments" if item.is_assignable else "Not accepting new assignments",
            "description": item.description,
            "detail_url": (
                reverse(detail_route, kwargs={detail_kwarg: item.pk})
                if detail_route and (can_view or can_edit or can_add)
                else ""
            ),
            "can_edit": can_edit,
            "edit_url": f"{manage_url}?edit={item.pk}" if can_edit else "",
        }
        for item in page.object_list
    ]

    current_assignments = []
    assignment_history = []
    if can_view_assignments:
        assignments = assignment_model.objects.select_related(
            "user", *assignment_fields,
        ).order_by("-started_at", "-pk")
        # Keep current assignments visible and bound the historical list.
        current = assignments.filter(ended_at__isnull=True)
        past = assignments.filter(ended_at__isnull=False)
        for assignment in current:
            current_assignments.append({
                "id": assignment.pk,
                "name": assignment.user.community_name,
                "details": " · ".join(str(value) for field in assignment_fields if (value := getattr(assignment, field)) is not None),
                "started_at": assignment.started_at,
                "ended_at": None,
            })
        history_page = Paginator(past, 25).get_page(request.GET.get("history_page"))
        for assignment in history_page.object_list:
            assignment_history.append({
                "id": assignment.pk,
                "name": assignment.user.community_name,
                "details": " · ".join(str(value) for field in assignment_fields if (value := getattr(assignment, field)) is not None),
                "started_at": assignment.started_at,
                "ended_at": assignment.ended_at,
            })
    else:
        history_page = None

    filters = request.GET.copy()
    for key in ("page", "history_page", "action", "edit", "assignment"):
        filters.pop(key, None)

    return render(
        request,
        "administration/organization_manage.html",
        {
            "title": title,
            "singular_title": singular_title,
            "description": f"Manage {title.lower()}, assignment availability, and historical records.",
            "manage_url": manage_url,
            "create_url": f"{manage_url}?action=create",
            "can_add": can_add,
            "can_edit": can_edit,
            "form": form,
            "form_mode": form_mode,
            "form_action": form_action,
            "records": records,
            "page": page,
            "search": search,
            "status_filters": [
                {"value": "assignable", "label": "Available for assignments", "selected": status == "assignable"},
                {"value": "unavailable", "label": "Not accepting new assignments", "selected": status == "unavailable"},
            ],
            "filter_query": filters.urlencode(),
            "tabs": [
                {"title": label, "url": reverse(url_name), "active": route_name == url_name}
                for label, url_name in (tabs or (
                    ("Citizenship", "organization:citizenship_manage"),
                    ("Social Ranks", "organization:social_rank_manage"),
                ))
            ],
            "assignment_title": assignment_title,
            "assignment_form": assignment_form,
            "show_assignment_form": show_assignment_form,
            "can_assign": can_assign,
            "can_end": can_end,
            "can_view_assignments": can_view_assignments,
            "current_assignments": current_assignments,
            "assignment_history": assignment_history,
            "history_page": history_page,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def citizenship_manage(request):
    return organization_definition_manage(
        request,
        model=CitizenshipClass,
        form_class=CitizenshipClassForm,
        assignment_model=CitizenshipRecord,
        assignment_form_class=CitizenshipAssignmentForm,
        route_name="organization:citizenship_manage",
        title="Citizenship Classes",
        singular_title="Citizenship Class",
        assignment_title="Citizenship Assignment",
        assignment_fields=("citizenship_class", "chapter"),
    )


@login_required
@require_http_methods(["GET", "POST"])
def social_rank_manage(request):
    return organization_definition_manage(
        request,
        model=SocialRank,
        form_class=SocialRankForm,
        assignment_model=UserSocialRank,
        assignment_form_class=SocialRankAssignmentForm,
        route_name="organization:social_rank_manage",
        title="Social Ranks",
        singular_title="Social Rank",
        assignment_title="Social Rank Assignment",
        assignment_fields=("social_rank",),
    )


OFFICES_GOVERNANCE_TABS = (
    ("Offices", "organization:office_manage"),
    ("Governance", "organization:governance_manage"),
)


@login_required
@require_http_methods(["GET", "POST"])
def office_manage(request):
    return organization_definition_manage(
        request,
        model=Office,
        form_class=OfficeForm,
        assignment_model=UserOffice,
        assignment_form_class=OfficeAssignmentForm,
        route_name="organization:office_manage",
        title="Offices",
        singular_title="Office",
        assignment_title="Office Appointment",
        assignment_fields=("office", "chapter"),
        tabs=OFFICES_GOVERNANCE_TABS,
    )


@login_required
@require_http_methods(["GET", "POST"])
def governance_manage(request):
    return organization_definition_manage(
        request,
        model=GovernanceBody,
        form_class=GovernanceBodyForm,
        assignment_model=GovernanceMembership,
        assignment_form_class=GovernanceMembershipForm,
        route_name="organization:governance_manage",
        title="Governance Bodies",
        singular_title="Governance Body",
        assignment_title="Governance Membership",
        assignment_fields=("governance_body",),
        tabs=OFFICES_GOVERNANCE_TABS,
        detail_route="organization:governance_detail",
        detail_kwarg="body_id",
    )


@login_required
@require_http_methods(["GET"])
def governance_detail(request, body_id):
    can_view = has_any_permission(
        request.user,
        (
            "organization.view_governancebody",
            "organization.add_governancebody",
            "organization.change_governancebody",
        ),
    )
    if not can_view:
        raise PermissionDenied

    body = get_object_or_404(GovernanceBody, pk=body_id)
    can_edit = has_any_permission(
        request.user, ("organization.change_governancebody",),
    )
    can_view_memberships = has_any_permission(
        request.user,
        (
            "organization.view_governancemembership",
            "organization.add_governancemembership",
            "organization.change_governancemembership",
        ),
    )
    manage_url = reverse("organization:governance_manage")
    sections = []

    if can_view_memberships:
        memberships = GovernanceMembership.objects.filter(
            governance_body=body,
        ).select_related("user").order_by("user__username", "-started_at")
        current = []
        former = []
        for membership in memberships:
            item = {
                "name": membership.user.community_name,
                "details": "Governance member",
                "started_at": membership.started_at,
                "ended_at": membership.ended_at,
            }
            if membership.ended_at is None:
                current.append(item)
            else:
                former.append(item)
        sections = [
            {
                "title": "Current Members",
                "description": "Members currently serving on this governance body.",
                "count": len(current),
                "items": current,
                "empty_message": "No current members recorded.",
            },
            {
                "title": "Former Members",
                "description": "Historical governance memberships.",
                "count": len(former),
                "items": former,
                "empty_message": "No former members recorded.",
            },
        ]

    return render(
        request,
        "administration/organization_detail.html",
        {
            "title": "Governance Bodies",
            "singular_title": "Governance Body",
            "record": body,
            "description": "Governance body information and membership history.",
            "manage_url": manage_url,
            "can_edit": can_edit,
            "edit_url": f"{manage_url}?edit={body.pk}" if can_edit else "",
            "fields": [
                {"label": "Name", "value": body.name},
                {"label": "Description", "value": body.description or "Not provided"},
                {
                    "label": "Available for New Assignments",
                    "value": "Yes" if body.is_assignable else "No",
                },
                {"label": "Created", "value": body.created_at},
                {"label": "Last Updated", "value": body.updated_at},
            ],
            "sections": sections,
        },
    )


ORDERS_TABS = (
    ("Orders", "organization:order_manage"),
    ("Order Ranks", "organization:order_rank_manage"),
)


@login_required
@require_http_methods(["GET", "POST"])
def order_manage(request):
    return organization_definition_manage(
        request,
        model=Order,
        form_class=OrderForm,
        assignment_model=OrderMembership,
        assignment_form_class=OrderMembershipForm,
        route_name="organization:order_manage",
        title="Orders",
        singular_title="Order",
        assignment_title="Order Membership",
        assignment_fields=("order", "order_rank"),
        tabs=ORDERS_TABS,
        detail_route="organization:order_detail",
        detail_kwarg="order_id",
        extra_definition_fields=("uses_ranks",),
    )


@login_required
@require_http_methods(["GET", "POST"])
def order_rank_manage(request):
    can_add = has_any_permission(request.user, ("organization.add_orderrank",))
    can_edit = has_any_permission(request.user, ("organization.change_orderrank",))
    can_view = has_any_permission(request.user, ("organization.view_orderrank",))
    if not (can_view or can_add or can_edit):
        raise PermissionDenied

    manage_url = reverse("organization:order_rank_manage")
    search = request.GET.get("search", "").strip()[:150]
    status = request.GET.get("status", "").strip()
    action = request.GET.get("action", "").strip()
    edit_id = request.GET.get("edit", "").strip()
    instance = None
    old_values = None
    form = None
    form_mode = None
    form_action = ""

    if action == "create":
        if not can_add:
            raise PermissionDenied
        form_mode = "create"
        form_action = f"{manage_url}?action=create"
    elif edit_id:
        if not can_edit:
            raise PermissionDenied
        instance = get_object_or_404(OrderRank, pk=edit_id)
        old_values = {
            "name": instance.name,
            "rank_order": instance.rank_order,
            "is_assignable": instance.is_assignable,
        }
        form_mode = "edit"
        form_action = f"{manage_url}?edit={instance.pk}"

    if request.method == "POST":
        if form_mode is None:
            raise PermissionDenied
        form = OrderRankForm(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            record_audit_event(
                actor=request.user,
                request=request,
                action=(
                    AuditLog.Action.UPDATE if instance is not None
                    else AuditLog.Action.CREATE
                ),
                target_type="Order rank",
                target_id=saved.pk,
                target_label=saved.name,
                old_value=old_values,
                new_value={
                    "name": saved.name,
                    "rank_order": saved.rank_order,
                    "is_assignable": saved.is_assignable,
                },
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )
            messages.success(request, "Order rank saved successfully.")
            return redirect(manage_url)
    elif form_mode:
        form = OrderRankForm(instance=instance)

    ranks = OrderRank.objects.all()
    if search:
        ranks = ranks.filter(name__icontains=search)
    if status == "assignable":
        ranks = ranks.filter(is_assignable=True)
    elif status == "unavailable":
        ranks = ranks.filter(is_assignable=False)
    else:
        status = ""

    page = Paginator(
        ranks.order_by("rank_order", "name", "pk"), 25,
    ).get_page(request.GET.get("page"))
    records = [
        {
            "name": rank.name,
            "status_label": (
                "Available for assignments" if rank.is_assignable
                else "Not accepting new assignments"
            ),
            "description": f"Display order: {rank.rank_order}",
            "detail_url": "",
            "can_edit": can_edit,
            "edit_url": f"{manage_url}?edit={rank.pk}" if can_edit else "",
        }
        for rank in page.object_list
    ]
    query_parameters = request.GET.copy()
    for key in ("page", "action", "edit"):
        query_parameters.pop(key, None)

    return render(
        request,
        "administration/organization_manage.html",
        {
            "title": "Order Ranks",
            "singular_title": "Order Rank",
            "description": "Manage the ranks used by EldVatten's ranked Orders.",
            "manage_url": manage_url,
            "create_url": f"{manage_url}?action=create",
            "can_add": can_add,
            "can_edit": can_edit,
            "form": form,
            "form_mode": form_mode,
            "form_action": form_action,
            "records": records,
            "page": page,
            "search": search,
            "status_filters": [
                {"value": "assignable", "label": "Available for assignments", "selected": status == "assignable"},
                {"value": "unavailable", "label": "Not accepting new assignments", "selected": status == "unavailable"},
            ],
            "filter_query": query_parameters.urlencode(),
            "tabs": [
                {"title": title, "url": reverse(route), "active": route == "organization:order_rank_manage"}
                for title, route in ORDERS_TABS
            ],
        },
    )


@login_required
@require_http_methods(["GET"])
def order_detail(request, order_id):
    can_view = has_any_permission(
        request.user,
        ("organization.view_order", "organization.add_order", "organization.change_order"),
    )
    if not can_view:
        raise PermissionDenied

    order = get_object_or_404(Order, pk=order_id)
    can_edit = has_any_permission(request.user, ("organization.change_order",))
    can_view_memberships = has_any_permission(
        request.user,
        (
            "organization.view_ordermembership",
            "organization.add_ordermembership",
            "organization.change_ordermembership",
        ),
    )
    manage_url = reverse("organization:order_manage")
    sections = []
    if can_view_memberships:
        memberships = OrderMembership.objects.filter(order=order).select_related(
            "user", "order_rank",
        ).order_by("user__username", "-started_at")
        current = []
        former = []
        for membership in memberships:
            item = {
                "name": membership.user.community_name,
                "details": (
                    membership.order_rank.name if membership.order_rank_id
                    else "Order member"
                ),
                "started_at": membership.started_at,
                "ended_at": membership.ended_at,
            }
            if membership.ended_at is None:
                current.append(item)
            else:
                former.append(item)
        sections = [
            {
                "title": "Current Members",
                "description": "Members currently belonging to this Order.",
                "count": len(current),
                "items": current,
                "empty_message": "No current members recorded.",
            },
            {
                "title": "Former Members",
                "description": "Historical Order memberships.",
                "count": len(former),
                "items": former,
                "empty_message": "No former members recorded.",
            },
        ]

    return render(
        request,
        "administration/organization_detail.html",
        {
            "title": "Orders",
            "singular_title": "Order",
            "record": order,
            "description": "Order information, membership, ranks, and history.",
            "manage_url": manage_url,
            "can_edit": can_edit,
            "edit_url": f"{manage_url}?edit={order.pk}" if can_edit else "",
            "fields": [
                {"label": "Name", "value": order.name},
                {"label": "Description", "value": order.description or "Not provided"},
                {"label": "Uses Ranks", "value": "Yes" if order.uses_ranks else "No"},
                {
                    "label": "Available for New Assignments",
                    "value": "Yes" if order.is_assignable else "No",
                },
                {"label": "Created", "value": order.created_at},
                {"label": "Last Updated", "value": order.updated_at},
            ],
            "sections": sections,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def community_group_manage(request):
    return organization_definition_manage(
        request,
        model=CommunityGroup,
        form_class=CommunityGroupForm,
        assignment_model=GroupMembership,
        assignment_form_class=GroupMembershipForm,
        route_name="organization:community_group_manage",
        title="Community Groups",
        singular_title="Community Group",
        assignment_title="Group Membership",
        assignment_fields=("community_group",),
        tabs=(("Community Groups", "organization:community_group_manage"),),
        detail_route="organization:community_group_detail",
        detail_kwarg="group_id",
    )


@login_required
@require_http_methods(["GET"])
def community_group_detail(request, group_id):
    if not has_any_permission(
        request.user,
        (
            "organization.view_communitygroup",
            "organization.add_communitygroup",
            "organization.change_communitygroup",
        ),
    ):
        raise PermissionDenied

    group = get_object_or_404(CommunityGroup, pk=group_id)
    can_edit = has_any_permission(
        request.user, ("organization.change_communitygroup",),
    )
    can_view_memberships = has_any_permission(
        request.user,
        (
            "organization.view_groupmembership",
            "organization.add_groupmembership",
            "organization.change_groupmembership",
        ),
    )

    sections = []
    if can_view_memberships:
        memberships = GroupMembership.objects.filter(
            community_group=group,
        ).select_related("user").order_by("user__username", "-started_at")
        current = []
        former = []
        for membership in memberships:
            item = {
                "name": membership.user.community_name,
                "details": "Community group member",
                "started_at": membership.started_at,
                "ended_at": membership.ended_at,
            }
            if membership.ended_at is None:
                current.append(item)
            else:
                former.append(item)
        sections = [
            {
                "title": "Current Members",
                "description": "Members currently belonging to this group.",
                "count": len(current),
                "items": current,
                "empty_message": "No current members recorded.",
            },
            {
                "title": "Former Members",
                "description": "Historical group memberships.",
                "count": len(former),
                "items": former,
                "empty_message": "No former members recorded.",
            },
        ]

    manage_url = reverse("organization:community_group_manage")
    return render(
        request,
        "administration/organization_detail.html",
        {
            "title": "Community Groups",
            "singular_title": "Community Group",
            "record": group,
            "description": "Community group information, membership, and history.",
            "manage_url": manage_url,
            "can_edit": can_edit,
            "edit_url": f"{manage_url}?edit={group.pk}" if can_edit else "",
            "fields": [
                {"label": "Name", "value": group.name},
                {"label": "Description", "value": group.description or "Not provided"},
                {
                    "label": "Available for New Assignments",
                    "value": "Yes" if group.is_assignable else "No",
                },
                {"label": "Created", "value": group.created_at},
                {"label": "Last Updated", "value": group.updated_at},
            ],
            "sections": sections,
        },
    )
