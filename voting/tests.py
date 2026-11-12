
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus
from audit.models import AuditLog
from notifications.models import Notification
from organization.models import (
    CommunityGroup,
    GroupMembership,
    Household,
    HouseholdMembership,
)

from .forms import VoteEligibilityTargetForm

from .models import (
    Vote,
    VoteComment,
    VoteEligibleUser,
    VoteEligibilityTarget,
    VoteOption,
    VoteResponse,
)
from .services import (
    calculate_vote_result,
    can_user_vote,
    close_vote,
    get_required_quorum_count,
    get_vote_participation_count,
    get_vote_response_count,
    open_vote,
    resolve_vote_eligibility,
    submit_vote_comment,
    submit_vote_response,
)


User = get_user_model()


class VotingDesktopTemplateTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/votes/")
        self.request.user = AnonymousUser()

    def test_member_list_uses_desktop_navigation(self):
        html = render_to_string(
            "voting/vote_list.html",
            {"vote_rows": []},
            request=self.request,
        )
        self.assertIn("My Votes | EldVatten", html)
        self.assertIn('href="/votes/"', html)
        self.assertIn("app-two-column", html)
        self.assertIn("You do not have any votes.", html)

    def test_management_list_uses_desktop_navigation(self):
        html = render_to_string(
            "voting/vote_manage_list.html",
            {"votes": []},
            request=self.request,
        )
        self.assertIn("Manage Votes | EldVatten", html)
        self.assertIn('href="/votes/manage/"', html)
        self.assertIn("No votes have been created.", html)

    def test_vote_detail_keeps_member_navigation(self):
        vote = SimpleNamespace(
            id=1,
            title="Test Vote",
            status="OPEN",
            get_status_display="Open",
            get_approval_rule_display="Simple Majority",
            description="",
            is_anonymous=False,
            requires_quorum=False,
            requires_all_responses=False,
            opens_at=None,
            closes_at=None,
        )
        html = render_to_string(
            "voting/vote_detail.html",
            {"vote": vote, "can_vote": False, "result": None},
            request=self.request,
        )
        self.assertIn("Test Vote | EldVatten", html)
        self.assertIn("My Votes", html)
        self.assertIn("No quorum requirement.", html)

    def test_delete_confirmation_keeps_form(self):
        vote = SimpleNamespace(id=1, title="Test Vote")
        html = render_to_string(
            "voting/vote_confirm_delete.html",
            {"vote": vote},
            request=self.request,
        )
        self.assertIn("Delete Vote | EldVatten", html)
        self.assertIn('method="post"', html)
        self.assertIn("Cancel", html)


class VotingTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(
            username="vote_manager",
            account_status=AccountStatus.MEMBER,
        )
        cls.viewer = User.objects.create_user(
            username="vote_viewer",
            account_status=AccountStatus.MEMBER,
        )
        cls.add_only = User.objects.create_user(
            username="vote_add_only",
            account_status=AccountStatus.MEMBER,
        )
        cls.member = User.objects.create_user(
            username="vote_member",
            account_status=AccountStatus.MEMBER,
        )
        cls.other_member = User.objects.create_user(
            username="vote_other_member",
            account_status=AccountStatus.MEMBER,
        )
        cls.third_member = User.objects.create_user(
            username="vote_third_member",
            account_status=AccountStatus.MEMBER,
        )
        cls.outsider = User.objects.create_user(
            username="vote_outsider",
            account_status=AccountStatus.MEMBER,
        )
        cls.pending = User.objects.create_user(
            username="vote_pending",
            account_status=AccountStatus.PENDING,
        )
        cls.suspended = User.objects.create_user(
            username="vote_suspended",
            account_status=AccountStatus.SUSPENDED,
        )
        cls.inactive = User.objects.create_user(
            username="vote_inactive",
            account_status=AccountStatus.MEMBER,
            is_active=False,
        )

        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="voting",
                codename__in=(
                    "view_vote",
                    "add_vote",
                    "change_vote",
                    "delete_vote",
                ),
            )
        }

        cls.manager.user_permissions.add(*permissions.values())
        cls.viewer.user_permissions.add(permissions["view_vote"])
        cls.add_only.user_permissions.add(permissions["add_vote"])

        cls.vote = Vote.objects.create(
            title="Ballot A",
            created_by=cls.manager,
            requires_quorum=False,
        )
        cls.yes = VoteOption.objects.create(
            vote=cls.vote,
            label="Yes",
            sort_order=1,
        )
        cls.no = VoteOption.objects.create(
            vote=cls.vote,
            label="No",
            sort_order=2,
        )
        VoteEligibilityTarget.objects.create(
            vote=cls.vote,
            user=cls.member,
        )

    def url(self, name, vote=None):
        if vote is None:
            return reverse("voting:" + name)
        return reverse("voting:" + name, args=[vote.pk])

    def add_target(self, user, vote=None):
        return VoteEligibilityTarget.objects.create(
            vote=vote or self.vote,
            user=user,
        )

    def open_ballot(self, vote=None):
        return open_vote(vote or self.vote)

    def make_vote(self, title, *, users=(), anonymous=False, **values):
        vote = Vote.objects.create(
            title=title,
            created_by=self.manager,
            is_anonymous=anonymous,
            requires_quorum=values.pop("requires_quorum", False),
            **values,
        )
        VoteOption.objects.create(
            vote=vote,
            label="Yes",
            sort_order=1,
        )
        VoteOption.objects.create(
            vote=vote,
            label="No",
            sort_order=2,
        )
        for user in users:
            self.add_target(user, vote)
        return vote

    def form_data(self, title="Browser Vote", *, submit_action="draft"):
        return {
            "title": title,
            "description": "Lorem ipsum dolor sit amet.",
            "approval_rule": Vote.ApprovalRule.SIMPLE_MAJORITY,
            "quorum_numerator": "2",
            "quorum_denominator": "5",
            "opens_at": "",
            "closes_at": "",
            "options-TOTAL_FORMS": "2",
            "options-INITIAL_FORMS": "0",
            "options-MIN_NUM_FORMS": "0",
            "options-MAX_NUM_FORMS": "1000",
            "options-0-label": "Yes",
            "options-0-sort_order": "1",
            "options-1-label": "No",
            "options-1-sort_order": "2",
            "targets-TOTAL_FORMS": "1",
            "targets-INITIAL_FORMS": "0",
            "targets-MIN_NUM_FORMS": "0",
            "targets-MAX_NUM_FORMS": "1000",
            "targets-0-user": str(self.member.pk),
            "submit_action": submit_action,
        }


class VotingPermissionTests(VotingTestBase):
    def test_anonymous_member_list_requires_login(self):
        response = self.client.get(self.url("vote_list"))
        self.assertEqual(response.status_code, 302)

    def test_member_has_no_management_access(self):
        self.client.force_login(self.member)

        for name in ("vote_manage_list", "vote_create"):
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(self.url(name)).status_code,
                    403,
                )

        for name in (
            "vote_manage_detail",
            "vote_edit",
            "vote_delete",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(
                        self.url(name, self.vote)
                    ).status_code,
                    403,
                )

    def test_view_only_manager_cannot_create_edit_open_close_or_delete(self):
        self.client.force_login(self.viewer)

        self.assertEqual(
            self.client.get(
                self.url("vote_manage_list")
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                self.url("vote_manage_detail", self.vote)
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(self.url("vote_create")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                self.url("vote_edit", self.vote)
            ).status_code,
            403,
        )

        for name in ("vote_open", "vote_close"):
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.post(
                        self.url(name, self.vote)
                    ).status_code,
                    403,
                )

        self.assertEqual(
            self.client.post(
                self.url("vote_delete", self.vote)
            ).status_code,
            403,
        )
        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.DRAFT)

    def test_add_only_can_open_create_form_but_not_manage_existing_votes(self):
        self.client.force_login(self.add_only)

        self.assertEqual(
            self.client.get(self.url("vote_create")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                self.url("vote_manage_list")
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                self.url("vote_manage_detail", self.vote)
            ).status_code,
            403,
        )

    def test_unassigned_member_cannot_open_or_submit_ballot(self):
        self.open_ballot()
        self.client.force_login(self.outsider)

        self.assertEqual(
            self.client.get(
                self.url("vote_detail", self.vote)
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                self.url("vote_submit", self.vote),
                {"option": self.yes.pk},
            ).status_code,
            404,
        )

    def test_draft_ballot_is_not_visible_to_member(self):
        self.client.force_login(self.member)

        self.assertEqual(
            self.client.get(
                self.url("vote_detail", self.vote)
            ).status_code,
            404,
        )
        self.assertNotContains(
            self.client.get(self.url("vote_list")),
            "Ballot A",
        )

    def test_member_list_contains_only_eligible_non_draft_ballots(self):
        self.open_ballot()
        hidden_vote = self.make_vote(
            "Hidden Ballot",
            users=[self.outsider],
        )
        self.open_ballot(hidden_vote)

        self.client.force_login(self.member)
        response = self.client.get(self.url("vote_list"))
        self.assertContains(response, "Ballot A")
        self.assertNotContains(response, "Hidden Ballot")

    def test_inactive_or_nonmember_cannot_cast_even_with_snapshot(self):
        self.open_ballot()

        VoteEligibleUser.objects.create(
            vote=self.vote,
            user=self.suspended,
        )
        VoteEligibleUser.objects.create(
            vote=self.vote,
            user=self.inactive,
        )

        self.assertFalse(
            can_user_vote(self.vote, self.suspended)
        )
        self.assertFalse(
            can_user_vote(self.vote, self.inactive)
        )

        with self.assertRaises(ValidationError):
            submit_vote_response(
                self.vote,
                self.suspended,
                self.yes,
            )

        with self.assertRaises(ValidationError):
            submit_vote_response(
                self.vote,
                self.inactive,
                self.yes,
            )


class VotingLifecycleTests(VotingTestBase):
    def test_open_creates_frozen_eligibility_and_notifications(self):
        self.add_target(self.other_member)
        opened = self.open_ballot()

        self.assertEqual(opened.status, Vote.Status.OPEN)
        self.assertIsNotNone(opened.opened_at)
        self.assertEqual(
            set(
                opened.eligible_users.values_list(
                    "user_id",
                    flat=True,
                )
            ),
            {self.member.pk, self.other_member.pk},
        )
        self.assertEqual(
            Notification.objects.filter(
                source_type="Vote",
                source_id=str(opened.pk),
            ).count(),
            2,
        )

    def test_open_rejects_missing_options_or_targets(self):
        missing_options = Vote.objects.create(
            title="No Options",
            created_by=self.manager,
        )
        VoteEligibilityTarget.objects.create(
            vote=missing_options,
            user=self.member,
        )

        with self.assertRaises(ValidationError):
            open_vote(missing_options)

        missing_targets = self.make_vote("No Targets")

        with self.assertRaises(ValidationError):
            open_vote(missing_targets)

    def test_open_rejects_target_without_active_members(self):
        vote = self.make_vote(
            "Pending Only",
            users=[self.pending],
        )

        with self.assertRaises(ValidationError):
            open_vote(vote)

        self.assertFalse(
            VoteEligibleUser.objects.filter(vote=vote).exists()
        )

    def test_scheduled_vote_cannot_open_early(self):
        self.vote.opens_at = (
            timezone.now() + timedelta(days=1)
        )
        self.vote.save(update_fields=["opens_at"])

        with self.assertRaises(ValidationError):
            self.open_ballot()

        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.DRAFT)

    def test_open_cannot_run_twice(self):
        self.open_ballot()

        with self.assertRaises(ValidationError):
            self.open_ballot()

        self.assertEqual(
            VoteEligibleUser.objects.filter(
                vote=self.vote
            ).count(),
            1,
        )

    def test_snapshot_does_not_follow_later_target_changes(self):
        self.vote = self.open_ballot()

        self.assertEqual(
            self.vote.status,
            Vote.Status.OPEN,
        )

        self.assertTrue(
            VoteEligibleUser.objects.filter(
                vote=self.vote,
                user=self.member,
            ).exists()
        )

        VoteEligibilityTarget.objects.filter(
            vote=self.vote,
        ).delete()

        self.add_target(self.other_member)

        self.assertEqual(
            resolve_vote_eligibility(self.vote),
            {self.other_member.pk},
        )

        self.assertTrue(
            VoteEligibleUser.objects.filter(
                vote=self.vote,
                user=self.member,
            ).exists()
        )

        self.assertFalse(
            VoteEligibleUser.objects.filter(
                vote=self.vote,
                user=self.other_member,
            ).exists()
        )

        self.assertTrue(
            can_user_vote(self.vote, self.member)
        )

        self.assertFalse(
            can_user_vote(self.vote, self.other_member)
        )

    def test_draft_cannot_close(self):
        with self.assertRaises(ValidationError):
            close_vote(self.vote)

    def test_close_transitions_to_closed_and_blocks_ballots(self):
        self.open_ballot()
        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        result = close_vote(self.vote)

        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.CLOSED)
        self.assertIsNotNone(self.vote.closed_at)
        self.assertTrue(result["approval_requirement_met"])
        self.assertFalse(
            can_user_vote(self.vote, self.member)
        )

        with self.assertRaises(ValidationError):
            close_vote(self.vote)

    def test_all_responses_required_blocks_early_close(self):
        self.vote.requires_all_responses = True
        self.vote.save(
            update_fields=["requires_all_responses"]
        )
        self.add_target(self.other_member)
        self.open_ballot()

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )

        with self.assertRaises(ValidationError):
            close_vote(self.vote)

        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.OPEN)

        submit_vote_response(
            self.vote,
            self.other_member,
            self.yes,
        )
        close_vote(self.vote)

        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.CLOSED)

    def test_expired_ballot_rejects_submission(self):
        self.vote.closes_at = (
            timezone.now() + timedelta(minutes=5)
        )
        self.vote.save(update_fields=["closes_at"])
        self.open_ballot()

        Vote.objects.filter(pk=self.vote.pk).update(
            closes_at=(
                timezone.now() - timedelta(minutes=1)
            )
        )
        self.vote.refresh_from_db()

        self.assertFalse(
            can_user_vote(self.vote, self.member)
        )
        with self.assertRaises(ValidationError):
            submit_vote_response(
                self.vote,
                self.member,
                self.yes,
            )


class VotingEligibilityTests(VotingTestBase):
    def test_direct_targets_exclude_pending_and_inactive_accounts(self):
        self.add_target(self.pending)
        self.add_target(self.inactive)

        self.assertEqual(
            resolve_vote_eligibility(self.vote),
            {self.member.pk},
        )

    def test_group_target_matches_current_membership_only(self):
        group = CommunityGroup.objects.create(
            name="Voting Group"
        )
        GroupMembership.objects.create(
            user=self.other_member,
            community_group=group,
            started_at=timezone.localdate(),
            changed_by=self.manager,
        )
        GroupMembership.objects.create(
            user=self.third_member,
            community_group=group,
            started_at=(
                timezone.localdate() - timedelta(days=10)
            ),
            ended_at=(
                timezone.localdate() - timedelta(days=1)
            ),
            changed_by=self.manager,
        )
        VoteEligibilityTarget.objects.create(
            vote=self.vote,
            community_group=group,
        )

        self.assertEqual(
            resolve_vote_eligibility(self.vote),
            {self.member.pk, self.other_member.pk},
        )

    def test_combined_organization_selectors_use_intersection(self):
        group = CommunityGroup.objects.create(
            name="Voting Group"
        )
        house = Household.objects.create(
            name="Voting Household"
        )

        for user in (self.member, self.other_member):
            GroupMembership.objects.create(
                user=user,
                community_group=group,
                started_at=timezone.localdate(),
                changed_by=self.manager,
            )

        HouseholdMembership.objects.create(
            user=self.other_member,
            household=house,
            started_at=timezone.localdate(),
            changed_by=self.manager,
        )
        VoteEligibilityTarget.objects.create(
            vote=self.vote,
            community_group=group,
            household=house,
        )
        VoteEligibilityTarget.objects.filter(
            vote=self.vote,
            user=self.member,
        ).delete()

        self.assertEqual(
            resolve_vote_eligibility(self.vote),
            {self.other_member.pk},
        )

    def test_empty_or_mixed_direct_target_is_invalid(self):
        with self.assertRaises(ValidationError):
            VoteEligibilityTarget(
                vote=self.vote
            ).full_clean()

        group = CommunityGroup.objects.create(
            name="Voting Group"
        )
        with self.assertRaises(ValidationError):
            VoteEligibilityTarget(
                vote=self.vote,
                user=self.member,
                community_group=group,
            ).full_clean()


class VotingBallotTests(VotingTestBase):
    def test_identified_ballot_can_be_updated_without_duplicate(self):
        self.open_ballot()

        first, created = submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        self.assertTrue(created)

        second, created = submit_vote_response(
            self.vote,
            self.member,
            self.no,
        )
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.option_id, self.no.pk)
        self.assertEqual(
            VoteResponse.objects.filter(
                option__vote=self.vote
            ).count(),
            1,
        )
        self.assertTrue(
            VoteEligibleUser.objects.get(
                vote=self.vote,
                user=self.member,
            ).has_responded
        )

    def test_anonymous_ballot_has_no_identity_or_timestamps(self):
        vote = self.make_vote(
            "Anonymous Ballot",
            users=[self.member],
            anonymous=True,
        )
        open_vote(vote)
        option = vote.options.first()

        response, created = submit_vote_response(
            vote,
            self.member,
            option,
        )

        self.assertTrue(created)
        self.assertIsNone(response.eligibility_id)
        self.assertIsNone(response.submitted_at)
        self.assertIsNone(response.updated_at)
        self.assertTrue(
            VoteEligibleUser.objects.get(
                vote=vote,
                user=self.member,
            ).has_responded
        )

        with self.assertRaises(ValidationError):
            submit_vote_response(
                vote,
                self.member,
                option,
            )

        self.assertEqual(
            VoteResponse.objects.filter(
                option__vote=vote
            ).count(),
            1,
        )

    def test_anonymous_ballot_cannot_be_linked_to_eligibility(self):
        vote = self.make_vote(
            "Anonymous Ballot",
            users=[self.member],
            anonymous=True,
        )
        open_vote(vote)

        response = VoteResponse(
            eligibility=VoteEligibleUser.objects.get(
                vote=vote,
                user=self.member,
            ),
            option=vote.options.first(),
        )

        with self.assertRaises(ValidationError):
            response.full_clean()

    def test_response_option_must_belong_to_same_vote(self):
        self.open_ballot()
        another = self.make_vote(
            "Other Ballot",
            users=[self.member],
        )

        with self.assertRaises(ValidationError):
            submit_vote_response(
                self.vote,
                self.member,
                another.options.first(),
            )

        self.assertEqual(
            get_vote_response_count(self.vote),
            0,
        )

    def test_http_identified_ballot_submission_records_audit(self):
        self.open_ballot()
        self.client.force_login(self.member)

        response = self.client.post(
            self.url("vote_submit", self.vote),
            {
                "option": self.yes.pk,
                "comment": "",
            },
        )
        self.assertRedirects(
            response,
            self.url("vote_detail", self.vote),
        )
        self.assertEqual(
            VoteResponse.objects.get(
                eligibility__user=self.member
            ).option_id,
            self.yes.pk,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                target_type="VoteResponse",
                action=AuditLog.Action.CREATE,
                actor=self.member,
            ).exists()
        )

        response = self.client.post(
            self.url("vote_submit", self.vote),
            {
                "option": self.no.pk,
                "comment": "",
            },
        )
        self.assertRedirects(
            response,
            self.url("vote_detail", self.vote),
        )
        self.assertEqual(
            VoteResponse.objects.get(
                eligibility__user=self.member
            ).option_id,
            self.no.pk,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                target_type="VoteResponse",
                action=AuditLog.Action.UPDATE,
                actor=self.member,
            ).exists()
        )

    def test_http_anonymous_ballot_audit_does_not_contain_choice(self):
        vote = self.make_vote(
            "Anonymous Ballot",
            users=[self.member],
            anonymous=True,
        )
        open_vote(vote)
        option = vote.options.first()
        self.client.force_login(self.member)

        response = self.client.post(
            self.url("vote_submit", vote),
            {
                "option": option.pk,
                "comment": "",
            },
        )
        self.assertRedirects(
            response,
            self.url("vote_detail", vote),
        )

        entry = AuditLog.objects.get(
            target_type="VoteParticipation",
            actor=self.member,
        )
        self.assertNotIn("option", entry.new_value)
        self.assertNotIn("option_id", entry.new_value)
        self.assertFalse(
            AuditLog.objects.filter(
                target_type="VoteResponse",
                actor=self.member,
            ).exists()
        )

        repeat = self.client.post(
            self.url("vote_submit", vote),
            {
                "option": option.pk,
                "comment": "",
            },
        )
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(
            VoteResponse.objects.filter(
                option__vote=vote
            ).count(),
            1,
        )

    def test_bad_option_does_not_create_response(self):
        self.open_ballot()
        self.client.force_login(self.member)

        response = self.client.post(
            self.url("vote_submit", self.vote),
            {
                "option": "not-an-option",
                "comment": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            get_vote_response_count(self.vote),
            0,
        )

    def test_private_comment_is_visible_to_reviewer_not_other_voters(self):
        self.add_target(self.other_member)
        self.open_ballot()
        submit_vote_comment(
            self.vote,
            self.member,
            "Private reviewer text",
        )

        self.client.force_login(self.other_member)
        response = self.client.get(
            self.url("vote_detail", self.vote)
        )
        self.assertNotContains(
            response,
            "Private reviewer text",
        )

        self.client.force_login(self.manager)
        response = self.client.get(
            self.url("vote_manage_detail", self.vote)
        )
        self.assertContains(
            response,
            "Private reviewer text",
        )

    def test_identified_comment_can_be_updated_and_removed(self):
        self.open_ballot()
        self.client.force_login(self.member)

        self.client.post(
            self.url("vote_submit", self.vote),
            {
                "option": self.yes.pk,
                "comment": "First comment",
            },
        )
        self.assertEqual(
            VoteComment.objects.get(
                vote=self.vote,
                author=self.member,
            ).body,
            "First comment",
        )

        self.client.post(
            self.url("vote_submit", self.vote),
            {
                "option": self.no.pk,
                "comment": "Updated comment",
            },
        )
        self.assertEqual(
            VoteComment.objects.get(
                vote=self.vote,
                author=self.member,
            ).body,
            "Updated comment",
        )

        self.client.post(
            self.url("vote_submit", self.vote),
            {
                "option": self.no.pk,
                "comment": "",
            },
        )
        self.assertFalse(
            VoteComment.objects.filter(
                vote=self.vote,
                author=self.member,
            ).exists()
        )

    def test_anonymous_comment_cannot_be_changed_after_submission(self):
        vote = self.make_vote(
            "Anonymous Ballot",
            users=[self.member],
            anonymous=True,
        )
        open_vote(vote)
        option = vote.options.first()
        self.client.force_login(self.member)

        self.client.post(
            self.url("vote_submit", vote),
            {
                "option": option.pk,
                "comment": "One-time reviewer comment",
            },
        )
        self.assertEqual(
            VoteComment.objects.filter(vote=vote).count(),
            1,
        )

        with self.assertRaises(ValidationError):
            submit_vote_comment(
                vote,
                self.member,
                "Changed later",
            )


class VotingResultTests(VotingTestBase):
    def test_quorum_count_rounds_up(self):
        self.vote.requires_quorum = True
        self.vote.quorum_numerator = 2
        self.vote.quorum_denominator = 3
        self.vote.save()

        self.add_target(self.other_member)
        self.add_target(self.third_member)
        self.open_ballot()

        self.assertEqual(
            get_required_quorum_count(self.vote),
            2,
        )

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        self.assertFalse(
            calculate_vote_result(self.vote)["quorum_met"]
        )

        submit_vote_response(
            self.vote,
            self.other_member,
            self.yes,
        )
        self.assertTrue(
            calculate_vote_result(self.vote)["quorum_met"]
        )

    def test_simple_majority_passes(self):
        self.add_target(self.other_member)
        self.add_target(self.third_member)
        self.open_ballot()

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.other_member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.third_member,
            self.no,
        )

        result = calculate_vote_result(self.vote)

        self.assertTrue(result["approval_requirement_met"])
        self.assertEqual(
            result["winner"]["option_id"],
            self.yes.pk,
        )
        self.assertEqual(
            get_vote_participation_count(self.vote),
            3,
        )
        self.assertEqual(
            get_vote_response_count(self.vote),
            3,
        )

    def test_equal_split_is_tie(self):
        self.add_target(self.other_member)
        self.open_ballot()

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.other_member,
            self.no,
        )

        result = calculate_vote_result(self.vote)

        self.assertFalse(result["approval_requirement_met"])
        self.assertEqual(
            result["reason"],
            "The vote ended in a tie.",
        )

    def test_unique_plurality_without_majority_fails(self):
        self.add_target(self.other_member)
        self.add_target(self.third_member)
        self.add_target(self.outsider)

        VoteOption.objects.create(
            vote=self.vote,
            label="Abstain",
            sort_order=3,
        )
        self.open_ballot()

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.other_member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.third_member,
            self.no,
        )

        abstain = self.vote.options.get(label="Abstain")
        submit_vote_response(
            self.vote,
            self.outsider,
            abstain,
        )

        result = calculate_vote_result(self.vote)

        self.assertFalse(result["approval_requirement_met"])
        self.assertEqual(
            result["reason"],
            "No option received a simple majority.",
        )

    def test_unanimous_approval_passes_when_all_responses_match(self):
        self.vote.approval_rule = (
            Vote.ApprovalRule.UNANIMOUS
        )
        self.vote.save(update_fields=["approval_rule"])
        self.add_target(self.other_member)
        self.open_ballot()

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.other_member,
            self.yes,
        )

        self.assertTrue(
            calculate_vote_result(
                self.vote
            )["approval_requirement_met"]
        )

    def test_unanimous_approval_fails_when_votes_differ(self):
        self.vote.approval_rule = (
            Vote.ApprovalRule.UNANIMOUS
        )
        self.vote.save(update_fields=["approval_rule"])
        self.add_target(self.other_member)
        self.add_target(self.third_member)
        self.open_ballot()

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.other_member,
            self.yes,
        )
        submit_vote_response(
            self.vote,
            self.third_member,
            self.no,
        )

        result = calculate_vote_result(self.vote)

        self.assertFalse(result["approval_requirement_met"])
        self.assertEqual(
            result["reason"],
            "The vote did not reach unanimous agreement.",
        )

    def test_required_all_responses_prevents_result_until_all_vote(self):
        self.vote.requires_all_responses = True
        self.vote.save(
            update_fields=["requires_all_responses"]
        )
        self.add_target(self.other_member)
        self.open_ballot()

        submit_vote_response(
            self.vote,
            self.member,
            self.yes,
        )

        result = calculate_vote_result(self.vote)

        self.assertFalse(result["approval_requirement_met"])
        self.assertEqual(
            result["reason"],
            "All required responses have not been received.",
        )

    def test_no_response_has_no_winner(self):
        self.open_ballot()
        result = calculate_vote_result(self.vote)

        self.assertFalse(result["has_winner"])
        self.assertEqual(
            result["reason"],
            "No responses were submitted.",
        )

    def test_invalid_quorum_values_are_rejected(self):
        self.vote.quorum_denominator = 0

        with self.assertRaises(ValidationError):
            self.vote.full_clean()

        self.vote.quorum_denominator = 3
        self.vote.quorum_numerator = 4

        with self.assertRaises(ValidationError):
            self.vote.full_clean()


class VotingManagementViewTests(VotingTestBase):
    def test_manager_can_create_draft_with_options_and_targets(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            self.url("vote_create"),
            self.form_data(),
        )
        self.assertEqual(response.status_code, 302)

        vote = Vote.objects.get(title="Browser Vote")

        self.assertEqual(vote.status, Vote.Status.DRAFT)
        self.assertEqual(vote.options.count(), 2)
        self.assertEqual(
            vote.eligibility_targets.count(),
            1,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                target_type="Vote",
                target_id=str(vote.pk),
                action=AuditLog.Action.CREATE,
            ).exists()
        )

    def test_manager_can_create_and_open_vote(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            self.url("vote_create"),
            self.form_data(submit_action="open"),
        )
        self.assertEqual(response.status_code, 302)

        vote = Vote.objects.get(title="Browser Vote")

        self.assertEqual(vote.status, Vote.Status.OPEN)
        self.assertTrue(
            VoteEligibleUser.objects.filter(
                vote=vote,
                user=self.member,
            ).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                target_type="VoteEligibleUser",
                action=AuditLog.Action.ASSIGN,
                actor=self.manager,
            ).exists()
        )

    def test_invalid_create_does_not_save_partial_vote(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            self.url("vote_create"),
            self.form_data(title=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.count(), 1)

    def test_manager_open_and_close_write_audit(self):
        self.client.force_login(self.manager)

        self.assertEqual(
            self.client.get(
                self.url("vote_open", self.vote)
            ).status_code,
            302,
        )
        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.DRAFT)

        response = self.client.post(
            self.url("vote_open", self.vote)
        )
        self.assertEqual(response.status_code, 302)

        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.OPEN)
        self.assertTrue(
            AuditLog.objects.filter(
                target_type="Vote",
                target_id=str(self.vote.pk),
                notes=(
                    "Vote opened and eligibility snapshot created."
                ),
            ).exists()
        )

        response = self.client.post(
            self.url("vote_close", self.vote)
        )
        self.assertEqual(response.status_code, 302)

        self.vote.refresh_from_db()
        self.assertEqual(self.vote.status, Vote.Status.CLOSED)
        self.assertTrue(
            AuditLog.objects.filter(
                target_type="Vote",
                target_id=str(self.vote.pk),
                notes__startswith="Vote closed.",
            ).exists()
        )

    def test_view_only_manager_does_not_see_mutation_controls(self):
        self.client.force_login(self.viewer)

        response = self.client.get(
            self.url("vote_manage_detail", self.vote)
        )

        self.assertNotContains(
            response,
            'action="' + self.url("vote_open", self.vote) + '"',
        )
        self.assertNotContains(
            response,
            "Delete Vote",
        )

    def test_draft_edit_offers_option_and_target_formsets(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            self.url("vote_edit", self.vote)
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(
            response.context["option_formset"]
        )
        self.assertIsNotNone(
            response.context["target_formset"]
        )

    def test_open_vote_edit_does_not_offer_option_or_target_formsets(self):
        self.open_ballot()
        self.client.force_login(self.manager)

        response = self.client.get(
            self.url("vote_edit", self.vote)
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            response.context["option_formset"]
        )
        self.assertIsNone(
            response.context["target_formset"]
        )
        self.assertTrue(
            response.context["form"]
            .fields["is_anonymous"]
            .disabled
        )

    def test_delete_vote_requires_post_and_writes_audit(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            self.url("vote_delete", self.vote)
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Vote.objects.filter(pk=self.vote.pk).exists()
        )

        response = self.client.post(
            self.url("vote_delete", self.vote)
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Vote.objects.filter(pk=self.vote.pk).exists()
        )
        self.assertTrue(
            AuditLog.objects.filter(
                target_type="Vote",
                target_id=str(self.vote.pk),
                action=AuditLog.Action.DELETE,
            ).exists()
        )


class VotingPostgresConcurrencyTests(TransactionTestCase):
    def test_two_simultaneous_anonymous_submissions_store_one_ballot(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row locking")

        manager = User.objects.create_user(
            username="concurrent_vote_manager",
            account_status=AccountStatus.MEMBER,
        )
        member = User.objects.create_user(
            username="concurrent_vote_member",
            account_status=AccountStatus.MEMBER,
        )
        vote = Vote.objects.create(
            title="Concurrent Anonymous Ballot",
            created_by=manager,
            is_anonymous=True,
            requires_quorum=False,
        )
        option = VoteOption.objects.create(
            vote=vote,
            label="Yes",
        )
        VoteEligibilityTarget.objects.create(
            vote=vote,
            user=member,
        )
        open_vote(vote)

        barrier = Barrier(2)

        def attempt_submission():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    submit_vote_response(
                        vote,
                        member,
                        option,
                    )
                    return "accepted"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(
                executor.map(
                    lambda _: attempt_submission(),
                    range(2),
                )
            )

        self.assertCountEqual(
            outcomes,
            ["accepted", "rejected"],
        )
        self.assertEqual(
            VoteResponse.objects.filter(
                option__vote=vote
            ).count(),
            1,
        )
        self.assertTrue(
            VoteEligibleUser.objects.get(
                vote=vote,
                user=member,
            ).has_responded
        )

class VotingCommunityNameTests(VotingTestBase):
    def set_name(self, user, *, eldvatten_name="", display_name="",
                 first_name="", last_name=""):
        user.eldvatten_name = eldvatten_name
        user.display_name = display_name
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=[
            "eldvatten_name", "display_name", "first_name", "last_name",
        ])

    def test_eligibility_target_selector_uses_eldvatten_name_and_username(self):
        self.set_name(
            self.member, eldvatten_name="Astrid", display_name="Personal Name",
        )
        form = VoteEligibilityTargetForm()
        label = form.fields["user"].label_from_instance(self.member)
        self.assertEqual(label, "Astrid (@vote_member)")
        self.assertNotIn("Personal Name", label)

    def test_selector_follows_fallback_hierarchy(self):
        field = VoteEligibilityTargetForm().fields["user"]
        cases = (
            ({"eldvatten_name": "  " , "display_name": "Display Name"},
             "Display Name (@vote_member)"),
            ({"display_name": "", "first_name": "First", "last_name": "Last"},
             "First Last (@vote_member)"),
            ({"first_name": "", "last_name": ""}, "@vote_member"),
        )
        for changes, expected in cases:
            with self.subTest(expected=expected):
                self.set_name(self.member, **changes)
                self.assertEqual(field.label_from_instance(self.member), expected)

    def test_eligibility_selector_orders_by_community_names(self):
        self.set_name(self.member, eldvatten_name="Zelda")
        self.set_name(self.other_member, eldvatten_name="Astrid")
        self.set_name(self.third_member, eldvatten_name="Maren")
        field = VoteEligibilityTargetForm().fields["user"]
        selected = list(field.queryset.filter(
            pk__in=[self.member.pk, self.other_member.pk, self.third_member.pk]
        ).values_list("pk", flat=True))
        self.assertEqual(selected, [
            self.other_member.pk, self.third_member.pk, self.member.pk,
        ])

    def test_draft_management_previews_eldvatten_name(self):
        self.set_name(self.member, eldvatten_name="Astrid")
        self.client.force_login(self.manager)
        response = self.client.get(self.url("vote_manage_detail", self.vote))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Astrid")
        self.assertEqual(
            {user.pk for user in response.context["eligibility_preview"]},
            {self.member.pk},
        )

    def test_open_vote_displays_frozen_voters_using_community_names(self):
        self.add_target(self.other_member)
        self.set_name(self.member, eldvatten_name="Zelda")
        self.set_name(self.other_member, eldvatten_name="Astrid")
        self.open_ballot()
        self.client.force_login(self.manager)
        response = self.client.get(self.url("vote_manage_detail", self.vote))
        self.assertEqual(response.status_code, 200)
        eligible = list(response.context["eligible_users"])
        self.assertEqual([entry.user_id for entry in eligible], [
            self.other_member.pk, self.member.pk,
        ])
        self.assertContains(response, "Astrid")
        self.assertContains(response, "Zelda")

    def test_identified_ballot_uses_community_name_but_keeps_user_id(self):
        self.set_name(self.member, eldvatten_name="Astrid")
        self.open_ballot()
        submit_vote_response(self.vote, self.member, self.yes)
        self.client.force_login(self.manager)
        response = self.client.get(self.url("vote_manage_detail", self.vote))
        self.assertEqual(response.status_code, 200)
        identified = list(response.context["identified_responses"])
        self.assertEqual(len(identified), 1)
        self.assertEqual(identified[0].eligibility.user_id, self.member.pk)
        self.assertEqual(identified[0].option_id, self.yes.pk)
        self.assertContains(response, "Astrid")

    def test_anonymous_ballot_does_not_expose_identified_responses(self):
        self.set_name(self.member, eldvatten_name="Astrid")
        vote = self.make_vote(
            "Anonymous Name Test", users=[self.member], anonymous=True,
        )
        open_vote(vote)
        submit_vote_response(vote, self.member, vote.options.first())
        self.client.force_login(self.manager)
        response = self.client.get(self.url("vote_manage_detail", vote))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["identified_responses"])
        ballot = VoteResponse.objects.get(option__vote=vote)
        self.assertIsNone(ballot.eligibility_id)
        self.assertIsNone(ballot.submitted_at)
        self.assertIsNone(ballot.updated_at)

    def test_renaming_member_does_not_change_frozen_voter_eligibility(self):
        self.vote = self.open_ballot()
        eligible = VoteEligibleUser.objects.get(vote=self.vote, user=self.member)
        self.set_name(self.member, eldvatten_name="Renamed Member")
        self.assertTrue(can_user_vote(self.vote, self.member))
        eligible.refresh_from_db()
        self.assertEqual(eligible.user_id, self.member.pk)
        response, created = submit_vote_response(
            self.vote, self.member, self.yes,
        )
        self.assertTrue(created)
        self.assertEqual(response.eligibility_id, eligible.pk)

    def test_private_vote_comments_show_community_name_to_reviewer(self):
        self.set_name(
            self.member, eldvatten_name="Astrid", display_name="Legal Label",
        )
        self.open_ballot()
        submit_vote_comment(self.vote, self.member, "Review comment")
        self.client.force_login(self.manager)
        response = self.client.get(self.url("vote_manage_detail", self.vote))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Astrid")
        self.assertContains(response, "Review comment")
        self.assertNotContains(response, "Legal Label")

    def test_community_name_is_html_escaped_in_management_page(self):
        self.set_name(self.member, eldvatten_name="<script>alert(1)</script>")
        self.client.force_login(self.manager)
        response = self.client.get(self.url("vote_manage_detail", self.vote))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

