from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from audit.models import AuditLog
from audit.services import record_audit_event

from .forms import (
    VoteBallotForm,
    VoteEligibilityTargetFormSet,
    VoteForm,
    VoteOptionFormSet,
)
from .models import (
    Vote,
    VoteComment,
    VoteEligibleUser,
    VoteResponse,
)
from .services import (
    calculate_vote_result,
    can_user_vote,
    close_vote,
    get_required_quorum_count,
    get_vote_participation_count,
    get_vote_response_count,
    get_vote_tally,
    open_vote,
    preview_vote_eligibility,
    submit_vote_comment,
    submit_vote_response,
)


def vote_values(vote):
    return {
        "title": vote.title,
        "description": vote.description,
        "status": vote.status,
        "approval_rule": vote.approval_rule,
        "is_anonymous": vote.is_anonymous,
        "requires_quorum": vote.requires_quorum,
        "quorum_numerator": vote.quorum_numerator,
        "quorum_denominator": vote.quorum_denominator,
        "requires_all_responses": vote.requires_all_responses,
        "opens_at": (
            vote.opens_at.isoformat()
            if vote.opens_at
            else None
        ),
        "closes_at": (
            vote.closes_at.isoformat()
            if vote.closes_at
            else None
        ),
        "opened_at": (
            vote.opened_at.isoformat()
            if vote.opened_at
            else None
        ),
        "closed_at": (
            vote.closed_at.isoformat()
            if vote.closed_at
            else None
        ),
        "created_by_id": vote.created_by_id,
    }


def option_values(option):
    return {
        "vote_id": option.vote_id,
        "label": option.label,
        "sort_order": option.sort_order,
    }


def target_values(target):
    return {
        "vote_id": target.vote_id,
        "user_id": target.user_id,
        "citizenship_class_id": target.citizenship_class_id,
        "social_rank_id": target.social_rank_id,
        "office_id": target.office_id,
        "chapter_id": target.chapter_id,
        "household_id": target.household_id,
        "governance_body_id": target.governance_body_id,
        "order_id": target.order_id,
        "order_rank_id": target.order_rank_id,
        "community_group_id": target.community_group_id,
        "household_leadership_type_id": (
            target.household_leadership_type_id
        ),
    }


def comment_values(comment):
    return {
        "vote_id": comment.vote_id,
        "author_id": comment.author_id,
        "body": comment.body,
    }


def audit_vote_open(request, vote, old_value):
    record_audit_event(
        action=AuditLog.Action.UPDATE,
        target_type="Vote",
        target_id=vote.id,
        target_label=vote.title,
        actor=request.user,
        request=request,
        old_value=old_value,
        new_value=vote_values(vote),
        effective_at=vote.opened_at,
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
        notes="Vote opened and eligibility snapshot created.",
    )

    for eligible_user in vote.eligible_users.select_related(
        "user",
    ):
        record_audit_event(
            action=AuditLog.Action.ASSIGN,
            target_type="VoteEligibleUser",
            target_id=eligible_user.id,
            target_label=vote.title,
            actor=request.user,
            request=request,
            old_value=None,
            new_value={
                "vote_id": vote.id,
                "user_id": eligible_user.user_id,
                "has_responded": False,
            },
            effective_at=eligible_user.added_at,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
            notes="User added to frozen vote eligibility snapshot.",
        )


@login_required
def vote_list(request):
    votes = (
        Vote.objects
        .filter(
            eligible_users__user=request.user,
        )
        .exclude(
            status=Vote.Status.DRAFT,
        )
        .distinct()
        .order_by(
            "closes_at",
            "-opened_at",
        )
    )

    vote_rows = []

    for vote in votes:
        eligibility = VoteEligibleUser.objects.filter(
            vote=vote,
            user=request.user,
        ).first()

        identified_response = None

        if not vote.is_anonymous:
            identified_response = (
                VoteResponse.objects
                .filter(
                    eligibility=eligibility,
                )
                .select_related(
                    "option",
                )
                .first()
            )

        vote_rows.append(
            {
                "vote": vote,
                "eligibility": eligibility,
                "has_responded": (
                    eligibility.has_responded
                    if eligibility
                    else False
                ),
                "response": identified_response,
                "can_vote": can_user_vote(
                    vote,
                    request.user,
                ),
            }
        )

    return render(
        request,
        "voting/vote_list.html",
        {
            "vote_rows": vote_rows,
        },
    )


@login_required
def vote_detail(request, vote_id):
    vote = get_object_or_404(
        Vote.objects.prefetch_related(
            "options",
        ),
        id=vote_id,
    )

    eligibility = VoteEligibleUser.objects.filter(
        vote=vote,
        user=request.user,
    ).first()

    if eligibility is None:
        raise Http404

    if vote.status == Vote.Status.DRAFT:
        raise Http404

    existing_response = None

    if not vote.is_anonymous:
        existing_response = (
            VoteResponse.objects
            .filter(
                eligibility=eligibility,
            )
            .select_related(
                "option",
            )
            .first()
        )

    existing_comment = None

    if not vote.is_anonymous:
        existing_comment = VoteComment.objects.filter(
            vote=vote,
            author=request.user,
        ).first()

    ballot_form = VoteBallotForm(
        vote=vote,
        existing_option=(
            existing_response.option
            if existing_response
            else None
        ),
        existing_comment=(
            existing_comment.body
            if existing_comment
            else ""
        ),
    )

    result = None

    if vote.status == Vote.Status.CLOSED:
        result = calculate_vote_result(vote)

    return render(
        request,
        "voting/vote_detail.html",
        {
            "vote": vote,
            "eligibility": eligibility,
            "existing_response": existing_response,
            "existing_comment": existing_comment,
            "ballot_form": ballot_form,
            "can_vote": can_user_vote(
                vote,
                request.user,
            ),
            "result": result,
        },
    )


@login_required
@transaction.atomic
def vote_submit(request, vote_id):
    if request.method != "POST":
        return redirect(
            "voting:vote_detail",
            vote_id=vote_id,
        )

    vote = get_object_or_404(
        Vote,
        id=vote_id,
    )

    eligibility = VoteEligibleUser.objects.filter(
        vote=vote,
        user=request.user,
    ).first()

    if eligibility is None:
        raise Http404

    existing_response = None

    if not vote.is_anonymous:
        existing_response = (
            VoteResponse.objects
            .filter(
                eligibility=eligibility,
            )
            .select_related(
                "option",
            )
            .first()
        )

    existing_comment = VoteComment.objects.filter(
        vote=vote,
        author=request.user,
    ).first()

    form = VoteBallotForm(
        request.POST,
        vote=vote,
        existing_option=(
            existing_response.option
            if existing_response
            else None
        ),
        existing_comment=(
            existing_comment.body
            if existing_comment
            else ""
        ),
    )

    if not form.is_valid():
        return render(
            request,
            "voting/vote_detail.html",
            {
                "vote": vote,
                "eligibility": eligibility,
                "existing_response": existing_response,
                "existing_comment": (
                    None
                    if vote.is_anonymous
                    else existing_comment
                ),
                "ballot_form": form,
                "can_vote": can_user_vote(
                    vote,
                    request.user,
                ),
                "result": None,
            },
        )

    option = form.cleaned_data["option"]
    comment_body = form.cleaned_data["comment"].strip()

    previous_option = None

    if existing_response is not None:
        previous_option = existing_response.option

    if comment_body:
        old_comment_value = (
            comment_values(existing_comment)
            if existing_comment
            else None
        )

        try:
            comment, comment_created = submit_vote_comment(
                vote,
                request.user,
                comment_body,
            )

        except ValidationError as error:
            form.add_error(
                "comment",
                error,
            )

            return render(
                request,
                "voting/vote_detail.html",
                {
                    "vote": vote,
                    "eligibility": eligibility,
                    "existing_response": existing_response,
                    "existing_comment": (
                        None
                        if vote.is_anonymous
                        else existing_comment
                    ),
                    "ballot_form": form,
                    "can_vote": can_user_vote(
                        vote,
                        request.user,
                    ),
                    "result": None,
                },
            )

        record_audit_event(
            action=(
                AuditLog.Action.CREATE
                if comment_created
                else AuditLog.Action.UPDATE
            ),
            target_type="VoteComment",
            target_id=comment.id,
            target_label=vote.title,
            actor=request.user,
            request=request,
            old_value=old_comment_value,
            new_value=comment_values(comment),
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    elif existing_comment is not None:
        if vote.is_anonymous:
            raise ValidationError(
                "An anonymous vote comment cannot be changed after submission."
            )

        old_comment_value = comment_values(
            existing_comment
        )

        comment_id = existing_comment.id

        existing_comment.delete()

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="VoteComment",
            target_id=comment_id,
            target_label=vote.title,
            actor=request.user,
            request=request,
            old_value=old_comment_value,
            new_value=None,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

    try:
        response, created = submit_vote_response(
            vote,
            request.user,
            option,
        )

    except ValidationError as error:
        transaction.set_rollback(True)

        form.add_error(
            None,
            error,
        )

        return render(
            request,
            "voting/vote_detail.html",
            {
                "vote": vote,
                "eligibility": eligibility,
                "existing_response": existing_response,
                "existing_comment": (
                    None
                    if vote.is_anonymous
                    else existing_comment
                ),
                "ballot_form": form,
                "can_vote": can_user_vote(
                    vote,
                    request.user,
                ),
                "result": None,
            },
        )

    if vote.is_anonymous:
        record_audit_event(
            action=AuditLog.Action.CREATE,
            target_type="VoteParticipation",
            target_id=vote.id,
            target_label=vote.title,
            actor=request.user,
            request=request,
            old_value=None,
            new_value={
                "vote_id": vote.id,
                "responded": True,
                "anonymous": True,
            },
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
            notes="Anonymous ballot submitted.",
        )

        messages.success(
            request,
            "Your anonymous ballot has been submitted.",
        )

    else:
        record_audit_event(
            action=(
                AuditLog.Action.CREATE
                if created
                else AuditLog.Action.UPDATE
            ),
            target_type="VoteResponse",
            target_id=response.id,
            target_label=vote.title,
            actor=request.user,
            request=request,
            old_value=(
                {
                    "vote_id": vote.id,
                    "option_id": previous_option.id,
                    "option": previous_option.label,
                }
                if previous_option
                else None
            ),
            new_value={
                "vote_id": vote.id,
                "option_id": option.id,
                "option": option.label,
            },
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        if created:
            messages.success(
                request,
                "Your vote has been submitted.",
            )

        else:
            messages.success(
                request,
                "Your vote has been updated.",
            )

    return redirect(
        "voting:vote_detail",
        vote_id=vote.id,
    )


@permission_required(
    "voting.view_vote",
    raise_exception=True,
)
def vote_manage_list(request):
    votes = Vote.objects.select_related(
        "created_by",
    ).order_by(
        "-created_at",
    )

    return render(
        request,
        "voting/vote_manage_list.html",
        {
            "votes": votes,
        },
    )


@permission_required(
    "voting.view_vote",
    raise_exception=True,
)
def vote_manage_detail(request, vote_id):
    vote = get_object_or_404(
        Vote.objects.select_related(
            "created_by",
        ).prefetch_related(
            "options",
            "eligibility_targets",
            "eligible_users__user",
            "comments__author",
        ),
        id=vote_id,
    )

    eligibility_preview = None

    if vote.status == Vote.Status.DRAFT:
        eligibility_preview = preview_vote_eligibility(
            vote
        )

    eligible_users = (
        vote.eligible_users
        .select_related(
            "user",
        )
        .order_by(
            "user__display_name",
            "user__username",
        )
    )

    comments = (
        vote.comments
        .select_related(
            "author",
        )
        .order_by(
            "created_at",
        )
    )

    identified_responses = None

    if not vote.is_anonymous:
        identified_responses = (
            VoteResponse.objects
            .filter(
                option__vote=vote,
            )
            .select_related(
                "option",
                "eligibility",
                "eligibility__user",
            )
            .order_by(
                "eligibility__user__display_name",
                "eligibility__user__username",
            )
        )

    result = calculate_vote_result(vote)

    return render(
        request,
        "voting/vote_manage_detail.html",
        {
            "vote": vote,
            "eligibility_preview": eligibility_preview,
            "eligible_users": eligible_users,
            "identified_responses": identified_responses,
            "comments": comments,
            "tally": get_vote_tally(vote),
            "eligible_count": vote.eligible_users.count(),
            "participation_count": (
                get_vote_participation_count(vote)
            ),
            "response_count": (
                get_vote_response_count(vote)
            ),
            "required_quorum": (
                get_required_quorum_count(vote)
            ),
            "result": result,
        },
    )


@permission_required(
    "voting.add_vote",
    raise_exception=True,
)
@transaction.atomic
def vote_create(request):
    if request.method == "POST":
        form = VoteForm(
            request.POST,
        )

        vote = Vote(
            created_by=request.user,
        )

        option_formset = VoteOptionFormSet(
            request.POST,
            instance=vote,
            prefix="options",
        )

        target_formset = VoteEligibilityTargetFormSet(
            request.POST,
            instance=vote,
            prefix="targets",
        )

        if (
            form.is_valid()
            and option_formset.is_valid()
            and target_formset.is_valid()
        ):
            submit_action = request.POST.get(
                "submit_action",
                "draft",
            )

            vote = form.save(
                commit=False,
            )

            vote.created_by = request.user
            vote.status = Vote.Status.DRAFT
            vote.opened_at = None
            vote.closed_at = None

            vote.full_clean()
            vote.save()

            option_formset.instance = vote
            target_formset.instance = vote

            options = option_formset.save()
            targets = target_formset.save()

            record_audit_event(
                action=AuditLog.Action.CREATE,
                target_type="Vote",
                target_id=vote.id,
                target_label=vote.title,
                actor=request.user,
                request=request,
                old_value=None,
                new_value=vote_values(vote),
                source=AuditLog.Source.WEB_APP,
                method=AuditLog.Method.MANUAL,
            )

            for option in options:
                record_audit_event(
                    action=AuditLog.Action.CREATE,
                    target_type="VoteOption",
                    target_id=option.id,
                    target_label=str(option),
                    actor=request.user,
                    request=request,
                    old_value=None,
                    new_value=option_values(option),
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )

            for target in targets:
                record_audit_event(
                    action=AuditLog.Action.CREATE,
                    target_type="VoteEligibilityTarget",
                    target_id=target.id,
                    target_label=str(target),
                    actor=request.user,
                    request=request,
                    old_value=None,
                    new_value=target_values(target),
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )

            if submit_action == "open":
                old_value = vote_values(vote)

                try:
                    vote = open_vote(vote)

                except ValidationError as error:
                    messages.error(
                        request,
                        f"Vote was saved as a draft but could not be opened: {error}",
                    )

                    return redirect(
                        "voting:vote_edit",
                        vote_id=vote.id,
                    )

                audit_vote_open(
                    request,
                    vote,
                    old_value,
                )

                messages.success(
                    request,
                    "Vote created and opened.",
                )

            else:
                messages.success(
                    request,
                    "Vote saved as a draft.",
                )

            return redirect(
                "voting:vote_manage_detail",
                vote_id=vote.id,
            )

    else:
        vote = Vote(
            created_by=request.user,
        )

        form = VoteForm(
            instance=vote,
        )

        option_formset = VoteOptionFormSet(
            instance=vote,
            prefix="options",
        )

        target_formset = VoteEligibilityTargetFormSet(
            instance=vote,
            prefix="targets",
        )

    return render(
        request,
        "voting/vote_form.html",
        {
            "form": form,
            "option_formset": option_formset,
            "target_formset": target_formset,
            "vote": None,
        },
    )


@permission_required(
    "voting.change_vote",
    raise_exception=True,
)
@transaction.atomic
def vote_edit(request, vote_id):
    vote = get_object_or_404(
        Vote,
        id=vote_id,
    )

    old_vote_value = vote_values(vote)

    old_options = {
        option.id: option_values(option)
        for option in vote.options.all()
    }

    old_targets = {
        target.id: target_values(target)
        for target in vote.eligibility_targets.all()
    }

    was_draft = vote.status == Vote.Status.DRAFT

    if request.method == "POST":
        form = VoteForm(
            request.POST,
            instance=vote,
        )

        if was_draft:
            option_formset = VoteOptionFormSet(
                request.POST,
                instance=vote,
                prefix="options",
            )

            target_formset = VoteEligibilityTargetFormSet(
                request.POST,
                instance=vote,
                prefix="targets",
            )

            formsets_valid = (
                option_formset.is_valid()
                and target_formset.is_valid()
            )

        else:
            option_formset = None
            target_formset = None
            formsets_valid = True

        if form.is_valid() and formsets_valid:
            submit_action = request.POST.get(
                "submit_action",
                "save",
            )

            vote = form.save(
                commit=False,
            )

            vote.full_clean()
            vote.save()

            if was_draft:
                option_formset.save()
                target_formset.save()

            new_vote_value = vote_values(vote)

            if old_vote_value != new_vote_value:
                record_audit_event(
                    action=AuditLog.Action.UPDATE,
                    target_type="Vote",
                    target_id=vote.id,
                    target_label=vote.title,
                    actor=request.user,
                    request=request,
                    old_value=old_vote_value,
                    new_value=new_vote_value,
                    source=AuditLog.Source.WEB_APP,
                    method=AuditLog.Method.MANUAL,
                )

            if was_draft:
                new_options = {
                    option.id: option_values(option)
                    for option in vote.options.all()
                }

                new_targets = {
                    target.id: target_values(target)
                    for target in vote.eligibility_targets.all()
                }

                for option_id, value in new_options.items():
                    if option_id not in old_options:
                        record_audit_event(
                            action=AuditLog.Action.CREATE,
                            target_type="VoteOption",
                            target_id=option_id,
                            target_label=value["label"],
                            actor=request.user,
                            request=request,
                            old_value=None,
                            new_value=value,
                            source=AuditLog.Source.WEB_APP,
                            method=AuditLog.Method.MANUAL,
                        )

                    elif old_options[option_id] != value:
                        record_audit_event(
                            action=AuditLog.Action.UPDATE,
                            target_type="VoteOption",
                            target_id=option_id,
                            target_label=value["label"],
                            actor=request.user,
                            request=request,
                            old_value=old_options[
                                option_id
                            ],
                            new_value=value,
                            source=AuditLog.Source.WEB_APP,
                            method=AuditLog.Method.MANUAL,
                        )

                for option_id, value in old_options.items():
                    if option_id not in new_options:
                        record_audit_event(
                            action=AuditLog.Action.DELETE,
                            target_type="VoteOption",
                            target_id=option_id,
                            target_label=value["label"],
                            actor=request.user,
                            request=request,
                            old_value=value,
                            new_value=None,
                            source=AuditLog.Source.WEB_APP,
                            method=AuditLog.Method.MANUAL,
                        )

                for target_id, value in new_targets.items():
                    if target_id not in old_targets:
                        record_audit_event(
                            action=AuditLog.Action.CREATE,
                            target_type="VoteEligibilityTarget",
                            target_id=target_id,
                            target_label=vote.title,
                            actor=request.user,
                            request=request,
                            old_value=None,
                            new_value=value,
                            source=AuditLog.Source.WEB_APP,
                            method=AuditLog.Method.MANUAL,
                        )

                    elif old_targets[target_id] != value:
                        record_audit_event(
                            action=AuditLog.Action.UPDATE,
                            target_type="VoteEligibilityTarget",
                            target_id=target_id,
                            target_label=vote.title,
                            actor=request.user,
                            request=request,
                            old_value=old_targets[
                                target_id
                            ],
                            new_value=value,
                            source=AuditLog.Source.WEB_APP,
                            method=AuditLog.Method.MANUAL,
                        )

                for target_id, value in old_targets.items():
                    if target_id not in new_targets:
                        record_audit_event(
                            action=AuditLog.Action.DELETE,
                            target_type="VoteEligibilityTarget",
                            target_id=target_id,
                            target_label=vote.title,
                            actor=request.user,
                            request=request,
                            old_value=value,
                            new_value=None,
                            source=AuditLog.Source.WEB_APP,
                            method=AuditLog.Method.MANUAL,
                        )

            if (
                was_draft
                and submit_action == "open"
            ):
                before_open_value = vote_values(vote)

                try:
                    vote = open_vote(vote)

                except ValidationError as error:
                    messages.error(
                        request,
                        f"Vote changes were saved, but the vote could not be opened: {error}",
                    )

                    return redirect(
                        "voting:vote_edit",
                        vote_id=vote.id,
                    )

                audit_vote_open(
                    request,
                    vote,
                    before_open_value,
                )

                messages.success(
                    request,
                    "Vote updated and opened.",
                )

            else:
                messages.success(
                    request,
                    "Vote updated.",
                )

            return redirect(
                "voting:vote_manage_detail",
                vote_id=vote.id,
            )

    else:
        form = VoteForm(
            instance=vote,
        )

        if vote.status == Vote.Status.DRAFT:
            option_formset = VoteOptionFormSet(
                instance=vote,
                prefix="options",
            )

            target_formset = VoteEligibilityTargetFormSet(
                instance=vote,
                prefix="targets",
            )

        else:
            option_formset = None
            target_formset = None

    return render(
        request,
        "voting/vote_form.html",
        {
            "form": form,
            "option_formset": option_formset,
            "target_formset": target_formset,
            "vote": vote,
        },
    )


@permission_required(
    "voting.change_vote",
    raise_exception=True,
)
def vote_open(request, vote_id):
    if request.method != "POST":
        return redirect(
            "voting:vote_manage_detail",
            vote_id=vote_id,
        )

    vote = get_object_or_404(
        Vote,
        id=vote_id,
    )

    old_value = vote_values(vote)

    try:
        opened_vote = open_vote(vote)

    except ValidationError as error:
        messages.error(
            request,
            str(error),
        )

        return redirect(
            "voting:vote_manage_detail",
            vote_id=vote.id,
        )

    audit_vote_open(
        request,
        opened_vote,
        old_value,
    )

    messages.success(
        request,
        "Vote opened.",
    )

    return redirect(
        "voting:vote_manage_detail",
        vote_id=opened_vote.id,
    )


@permission_required(
    "voting.change_vote",
    raise_exception=True,
)
def vote_close(request, vote_id):
    if request.method != "POST":
        return redirect(
            "voting:vote_manage_detail",
            vote_id=vote_id,
        )

    vote = get_object_or_404(
        Vote,
        id=vote_id,
    )

    old_value = vote_values(vote)

    try:
        result = close_vote(vote)

    except ValidationError as error:
        messages.error(
            request,
            str(error),
        )

        return redirect(
            "voting:vote_manage_detail",
            vote_id=vote.id,
        )

    vote.refresh_from_db()

    record_audit_event(
        action=AuditLog.Action.UPDATE,
        target_type="Vote",
        target_id=vote.id,
        target_label=vote.title,
        actor=request.user,
        request=request,
        old_value=old_value,
        new_value=vote_values(vote),
        effective_at=vote.closed_at,
        source=AuditLog.Source.WEB_APP,
        method=AuditLog.Method.MANUAL,
        notes=(
            "Vote closed. "
            f"Result: {result['reason']}"
        ),
    )

    messages.success(
        request,
        "Vote closed.",
    )

    return redirect(
        "voting:vote_manage_detail",
        vote_id=vote.id,
    )


@permission_required(
    "voting.delete_vote",
    raise_exception=True,
)
def vote_delete(request, vote_id):
    vote = get_object_or_404(
        Vote,
        id=vote_id,
    )

    if request.method == "POST":
        old_value = vote_values(vote)

        vote_id_value = vote.id
        vote_label = vote.title

        record_audit_event(
            action=AuditLog.Action.DELETE,
            target_type="Vote",
            target_id=vote_id_value,
            target_label=vote_label,
            actor=request.user,
            request=request,
            old_value=old_value,
            new_value=None,
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        vote.delete()

        messages.success(
            request,
            "Vote deleted.",
        )

        return redirect(
            "voting:vote_manage_list",
        )

    return render(
        request,
        "voting/vote_confirm_delete.html",
        {
            "vote": vote,
        },
    )