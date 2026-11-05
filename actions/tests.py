
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus
from accounts.my_eldvatten import get_todo_context
from accounts.needs_attention import get_action_attention_items, get_needs_attention_items
from audit.models import AuditLog
from community.models import (
    ForumBoard,
    ForumBoardTarget,
    ForumCategory,
    ForumThread,
    ForumThreadTarget,
)
from notifications.models import Notification
from organization.models import (
    CommunityGroup,
    GroupMembership,
    Household,
    HouseholdMembership,
)

from .forms import ActionForm
from .models import Action, ActionAssignment, ActionTarget
from .services import resolve_action_target, resolve_action_targets, sync_action_assignments
from .views import ActionTargetFormSet


User = get_user_model()


class ActionTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(
            username="action_member",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )
        cls.other_member = User.objects.create_user(
            username="other_action_member",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )
        cls.manager = User.objects.create_user(
            username="action_manager",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )
        cls.viewer = User.objects.create_user(
            username="action_viewer",
            account_status=AccountStatus.MEMBER,
        )
        cls.add_only = User.objects.create_user(
            username="action_add_only",
            account_status=AccountStatus.MEMBER,
        )
        cls.pending = User.objects.create_user(
            username="action_pending",
            account_status=AccountStatus.PENDING,
        )
        cls.inactive = User.objects.create_user(
            username="action_inactive",
            account_status=AccountStatus.MEMBER,
            is_active=False,
        )

        for codename in ("view_action", "add_action", "change_action", "delete_action"):
            cls.manager.user_permissions.add(
                Permission.objects.get(
                    content_type__app_label="actions",
                    codename=codename,
                )
            )
        cls.viewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="actions",
                codename="view_action",
            )
        )
        cls.add_only.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="actions",
                codename="add_action",
            )
        )

        cls.category = ForumCategory.objects.create(name="Action Test Category")
        cls.board = ForumBoard.objects.create(
            category=cls.category,
            name="Action Test Board",
        )
        cls.visible_thread = ForumThread.objects.create(
            board=cls.board,
            title="Accessible Action Discussion",
            created_by=cls.member,
        )
        cls.restricted_thread = ForumThread.objects.create(
            board=cls.board,
            title="Restricted Leadership Discussion",
            created_by=cls.other_member,
        )
        ForumThreadTarget.objects.create(
            thread=cls.restricted_thread,
            user=cls.other_member,
        )
        cls.restricted_board = ForumBoard.objects.create(
            category=cls.category,
            name="Restricted Action Board",
        )
        ForumBoardTarget.objects.create(
            board=cls.restricted_board,
            user=cls.other_member,
        )
        cls.board_restricted_thread = ForumThread.objects.create(
            board=cls.restricted_board,
            title="Private Board Discussion",
            created_by=cls.other_member,
        )
        cls.archived_thread = ForumThread.objects.create(
            board=cls.board,
            title="Archived Action Discussion",
            created_by=cls.member,
            archived_at=timezone.now(),
        )

        cls.action = Action.objects.create(
            title="Test Action",
            instructions="Complete the assigned task.",
            created_by=cls.manager,
        )
        cls.action.linked_threads.add(
            cls.visible_thread,
            cls.restricted_thread,
            cls.board_restricted_thread,
            cls.archived_thread,
        )
        cls.assignment = ActionAssignment.objects.create(
            action=cls.action,
            user=cls.member,
        )

    def url(self, name, action=None):
        if action is None:
            return reverse("actions:" + name)
        return reverse("actions:" + name, args=[action.pk])

    def make_action(self, title, *, deadline=None, required=False):
        return Action.objects.create(
            title=title,
            deadline=deadline,
            is_required=required,
            created_by=self.manager,
        )

    def assign(self, action, user, *, status=ActionAssignment.Status.NOT_STARTED, active=True):
        assignment = ActionAssignment.objects.create(action=action, user=user)
        if status in (ActionAssignment.Status.OPENED, ActionAssignment.Status.COMPLETED):
            assignment.mark_opened()
        if status == ActionAssignment.Status.COMPLETED:
            assignment.mark_completed()
        if not active:
            assignment.is_active = False
            assignment.unassigned_at = timezone.now()
            assignment.save(update_fields=["is_active", "unassigned_at"])
        return assignment

    def form_data(self, *, title="New Action", rows=None, initial=0, **values):
        rows = [] if rows is None else rows
        prefix = ActionTargetFormSet.get_default_prefix()
        data = {
            "title": title,
            "instructions": "Test instructions.",
            "external_url": "",
            "deadline": "",
            "linked_threads": [],
            f"{prefix}-TOTAL_FORMS": str(len(rows)),
            f"{prefix}-INITIAL_FORMS": str(initial),
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(rows):
            for field, value in row.items():
                data[f"{prefix}-{index}-{field}"] = str(value)
        data.update(values)
        return data

    def member_detail_url(self):
        return self.url("detail", self.action)

    def manage_detail_url(self):
        return self.url("manage_detail", self.action)


class ActionLinkedThreadTests(ActionTestBase):
    def assert_thread_visible(self, response, thread):
        self.assertContains(response, thread.title)
        self.assertContains(
            response,
            reverse("community:thread_detail", args=[thread.pk]),
        )

    def assert_thread_hidden(self, response, thread):
        self.assertNotContains(response, thread.title)
        self.assertNotContains(
            response,
            reverse("community:thread_detail", args=[thread.pk]),
        )

    def test_action_form_uses_linked_threads(self):
        form = ActionForm()
        self.assertIn("linked_threads", form.fields)
        self.assertNotIn("linked_posts", form.fields)

    def test_member_sees_accessible_linked_thread(self):
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assert_thread_visible(response, self.visible_thread)

    def test_member_cannot_see_restricted_thread(self):
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assert_thread_hidden(response, self.restricted_thread)

    def test_member_cannot_see_thread_in_restricted_board(self):
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assert_thread_hidden(response, self.board_restricted_thread)

    def test_member_cannot_see_archived_thread(self):
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assert_thread_hidden(response, self.archived_thread)

    def test_member_cannot_see_thread_in_archived_board(self):
        self.restricted_board.archived_at = timezone.now()
        self.restricted_board.save(update_fields=["archived_at"])
        self.assign(self.action, self.other_member)
        self.client.force_login(self.other_member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assert_thread_hidden(response, self.board_restricted_thread)

    def test_member_cannot_see_thread_in_archived_category(self):
        self.category.archived_at = timezone.now()
        self.category.save(update_fields=["archived_at"])
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assert_thread_hidden(response, self.visible_thread)

    def test_member_context_contains_only_accessible_threads(self):
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(
            {thread.pk for thread in response.context["visible_linked_threads"]},
            {self.visible_thread.pk},
        )

    def test_unassigned_member_cannot_view_action(self):
        self.client.force_login(self.other_member)
        self.assertEqual(self.client.get(self.member_detail_url()).status_code, 404)

    def test_inactive_assignment_cannot_view_action(self):
        self.assignment.is_active = False
        self.assignment.unassigned_at = timezone.now()
        self.assignment.save(update_fields=["is_active", "unassigned_at"])
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.member_detail_url()).status_code, 404)

    def test_anonymous_user_cannot_view_action(self):
        self.assertEqual(self.client.get(self.member_detail_url()).status_code, 302)

    def test_action_manager_sees_accessible_threads(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.manage_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assert_thread_visible(response, self.visible_thread)

    def test_action_manager_cannot_see_restricted_threads(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.manage_detail_url())
        self.assertEqual(response.status_code, 200)
        for thread in (
            self.restricted_thread,
            self.board_restricted_thread,
            self.archived_thread,
        ):
            self.assert_thread_hidden(response, thread)

    def test_manager_context_contains_only_accessible_threads(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.manage_detail_url())
        self.assertEqual(
            {thread.pk for thread in response.context["visible_linked_threads"]},
            {self.visible_thread.pk},
        )

    def test_member_cannot_access_action_management(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.manage_detail_url()).status_code, 403)

    def test_action_without_links_has_no_related_threads_section(self):
        self.action.linked_threads.clear()
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["visible_linked_threads"]), [])
        self.assertNotContains(response, "Related Tavern Threads")

    def test_target_change_updates_visible_threads(self):
        self.client.force_login(self.member)
        before = self.client.get(self.member_detail_url())
        self.assert_thread_hidden(before, self.restricted_thread)
        ForumThreadTarget.objects.filter(thread=self.restricted_thread).delete()
        ForumThreadTarget.objects.create(
            thread=self.restricted_thread,
            user=self.member,
        )
        after = self.client.get(self.member_detail_url())
        self.assert_thread_visible(after, self.restricted_thread)


class ActionMemberTests(ActionTestBase):
    def test_member_list_is_empty_when_no_actions_are_assigned(self):
        self.client.force_login(self.other_member)
        response = self.client.get(self.url("list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You have no assigned actions")
        self.assertEqual(response.context["outstanding_assignments"], [])
        self.assertEqual(response.context["completed_assignments"], [])

    def test_list_excludes_other_users_and_inactive_assignments(self):
        other_action = self.make_action("Other Member Action")
        inactive_action = self.make_action("Inactive Assignment")
        self.assign(other_action, self.other_member)
        self.assign(inactive_action, self.member, active=False)
        self.client.force_login(self.member)
        response = self.client.get(self.url("list"))
        self.assertEqual(
            [row.action_id for row in response.context["outstanding_assignments"]],
            [self.action.id],
        )
        self.assertNotContains(response, "Other Member Action")
        self.assertNotContains(response, "Inactive Assignment")

    def test_list_orders_outstanding_by_deadline_and_completed_by_date(self):
        now = timezone.now()
        later = self.make_action("Later", deadline=now + timedelta(days=5))
        sooner = self.make_action("Sooner", deadline=now + timedelta(days=1))
        completed_old = self.make_action("Completed Earlier")
        completed_new = self.make_action("Completed Later")
        self.assign(later, self.member)
        self.assign(sooner, self.member)
        self.assign(completed_old, self.member, status=ActionAssignment.Status.COMPLETED)
        self.assign(completed_new, self.member, status=ActionAssignment.Status.COMPLETED)
        ActionAssignment.objects.filter(action=completed_old, user=self.member).update(
            opened_at=now - timedelta(days=4),
            completed_at=now - timedelta(days=3),
        )
        self.client.force_login(self.member)
        response = self.client.get(self.url("list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row.action.title for row in response.context["outstanding_assignments"]],
            ["Sooner", "Later", "Test Action"],
        )
        self.assertEqual(
            [row.action.title for row in response.context["completed_assignments"]],
            ["Completed Later", "Completed Earlier"],
        )
        self.assertContains(response, "Outstanding Actions")
        self.assertContains(response, "Completed Actions")

    def test_member_list_rejects_nonmember_and_anonymous(self):
        self.assertEqual(self.client.get(self.url("list")).status_code, 302)
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(self.url("list")).status_code, 403)

    def test_opening_action_updates_status_and_audit_once(self):
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ActionAssignment.Status.OPENED)
        self.assertIsNotNone(self.assignment.opened_at)
        self.assertIsNone(self.assignment.completed_at)
        log = AuditLog.objects.get(
            target_type="ActionAssignment",
            target_id=str(self.assignment.id),
            action=AuditLog.Action.UPDATE,
        )
        self.assertEqual(log.actor, self.member)
        self.assertEqual(log.old_value["status"], ActionAssignment.Status.NOT_STARTED)
        self.assertEqual(log.new_value["status"], ActionAssignment.Status.OPENED)
        self.client.get(self.member_detail_url())
        self.assertEqual(
            AuditLog.objects.filter(
                target_type="ActionAssignment",
                target_id=str(self.assignment.id),
                action=AuditLog.Action.UPDATE,
            ).count(),
            1,
        )

    def test_completion_post_sets_timestamps_and_audits_once(self):
        self.client.force_login(self.member)
        url = self.url("complete", self.action)
        response = self.client.post(url)
        self.assertRedirects(response, self.member_detail_url(), fetch_redirect_response=False)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ActionAssignment.Status.COMPLETED)
        self.assertIsNotNone(self.assignment.opened_at)
        self.assertIsNotNone(self.assignment.completed_at)
        self.assertGreaterEqual(self.assignment.completed_at, self.assignment.opened_at)
        self.assertEqual(
            AuditLog.objects.filter(
                target_type="ActionAssignment",
                target_id=str(self.assignment.id),
                notes="Member completed assigned action.",
            ).count(),
            1,
        )
        self.client.post(url)
        self.assertEqual(
            AuditLog.objects.filter(
                target_type="ActionAssignment",
                target_id=str(self.assignment.id),
                notes="Member completed assigned action.",
            ).count(),
            1,
        )

    def test_completion_cannot_be_sent_by_get(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url("complete", self.action)).status_code, 405)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, ActionAssignment.Status.NOT_STARTED)

    def test_completion_denied_for_other_user_or_inactive_assignment(self):
        self.client.force_login(self.other_member)
        self.assertEqual(self.client.post(self.url("complete", self.action)).status_code, 404)
        self.client.force_login(self.member)
        self.assignment.is_active = False
        self.assignment.unassigned_at = timezone.now()
        self.assignment.save(update_fields=["is_active", "unassigned_at"])
        self.assertEqual(self.client.post(self.url("complete", self.action)).status_code, 404)

    def test_detail_denied_for_nonmember(self):
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(self.member_detail_url()).status_code, 403)

    def test_completed_action_detail_does_not_offer_completion_button(self):
        self.assignment.mark_completed()
        self.client.force_login(self.member)
        response = self.client.get(self.member_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This action is complete")
        self.assertNotContains(response, "Mark Complete")


class ActionManagementTests(ActionTestBase):
    def test_manager_can_view_management_pages(self):
        self.client.force_login(self.viewer)
        response = self.client.get(self.url("manage_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.action.title)
        response = self.client.get(self.manage_detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.action.title)

    def test_management_requires_view_permission(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url("manage_list")).status_code, 403)
        self.assertEqual(self.client.get(self.manage_detail_url()).status_code, 403)

    def test_create_requires_add_and_view_permissions(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url("create")).status_code, 403)
        self.client.force_login(self.add_only)
        self.assertEqual(self.client.get(self.url("create")).status_code, 403)
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(self.url("create")).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url("create")).status_code, 200)

    def test_member_cannot_edit_delete_or_sync(self):
        self.client.force_login(self.member)
        for name in ("edit", "delete"):
            self.assertEqual(self.client.get(self.url(name, self.action)).status_code, 403)
        self.assertEqual(
            self.client.post(self.url("sync_assignments", self.action)).status_code,
            403,
        )

    def test_create_form_only_lists_accessible_threads(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.url("create"))
        self.assertEqual(response.status_code, 200)
        ids = set(response.context["form"].fields["linked_threads"].queryset.values_list("id", flat=True))
        self.assertIn(self.visible_thread.pk, ids)
        for thread in (
            self.restricted_thread,
            self.board_restricted_thread,
            self.archived_thread,
        ):
            self.assertNotIn(thread.pk, ids)
            self.assertNotContains(response, thread.title)
        self.assertContains(response, "data-action-editor")
        self.assertContains(response, "data-action-target-list")

    def test_create_single_member_target_saves_assigns_notifies_and_audits(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url("create"),
            self.form_data(
                title="Created For Member",
                rows=[{"user": self.other_member.pk}],
                is_required="on",
                linked_threads=[str(self.visible_thread.pk)],
            ),
        )
        created = Action.objects.get(title="Created For Member")
        self.assertRedirects(
            response,
            self.url("manage_detail", created),
            fetch_redirect_response=False,
        )
        self.assertEqual(created.created_by, self.manager)
        self.assertTrue(created.is_required)
        self.assertEqual(set(created.linked_threads.values_list("id", flat=True)), {self.visible_thread.pk})
        target = created.targets.get()
        self.assertEqual(target.user, self.other_member)
        assignment = created.assignments.get()
        self.assertEqual(assignment.user, self.other_member)
        self.assertEqual(assignment.status, ActionAssignment.Status.NOT_STARTED)
        self.assertEqual(
            AuditLog.objects.filter(target_type="Action", target_id=str(created.pk), action=AuditLog.Action.CREATE).count(),
            1,
        )
        self.assertEqual(
            AuditLog.objects.filter(target_type="ActionTarget", target_id=str(target.pk), action=AuditLog.Action.CREATE).count(),
            1,
        )
        self.assertEqual(
            AuditLog.objects.filter(target_type="ActionAssignment", target_id=str(assignment.pk), action=AuditLog.Action.ASSIGN).count(),
            1,
        )
        notification = Notification.objects.get(
            user=self.other_member,
            source_type="Action",
            source_id=str(created.pk),
        )
        self.assertEqual(notification.notification_type, Notification.Type.ACTION)
        self.assertEqual(notification.target_url, self.url("detail", created))

    def test_create_rejects_invalid_title_without_saving_any_records(self):
        self.client.force_login(self.manager)
        before = Action.objects.count()
        response = self.client.post(
            self.url("create"),
            self.form_data(title="", rows=[{"user": self.other_member.pk}]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.assertEqual(Action.objects.count(), before)
        self.assertFalse(AuditLog.objects.filter(target_type="Action").exists())

    def test_create_rejects_user_combined_with_organizational_selector(self):
        group = CommunityGroup.objects.create(name="Action Test Group")
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url("create"),
            self.form_data(rows=[{"user": self.member.pk, "community_group": group.pk}]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["target_formset"].errors)
        self.assertFalse(Action.objects.filter(title="New Action").exists())
        self.assertFalse(Notification.objects.filter(source_type="Action").exists())

    def test_create_rejects_inaccessible_thread_choice(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url("create"),
            self.form_data(
                rows=[{"user": self.member.pk}],
                linked_threads=[str(self.restricted_thread.pk)],
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("linked_threads", response.context["form"].errors)
        self.assertFalse(Action.objects.filter(title="New Action").exists())

    def test_edit_preserves_unavailable_previous_thread_links(self):
        self.client.force_login(self.manager)
        previous_links = set(self.action.linked_threads.values_list("id", flat=True))
        response = self.client.post(
            self.url("edit", self.action),
            self.form_data(
                title="Edited Action",
                rows=[],
                initial=0,
                linked_threads=[str(self.visible_thread.pk)],
            ),
        )
        self.assertRedirects(
            response,
            self.manage_detail_url(),
            fetch_redirect_response=False,
        )
        self.action.refresh_from_db()
        self.assertEqual(self.action.title, "Edited Action")
        self.assertEqual(set(self.action.linked_threads.values_list("id", flat=True)), previous_links)
        self.assertEqual(
            AuditLog.objects.filter(
                target_type="Action",
                target_id=str(self.action.pk),
                action=AuditLog.Action.UPDATE,
            ).count(),
            1,
        )

    def test_edit_target_reassigns_members_and_records_changes(self):
        original_target = ActionTarget.objects.create(action=self.action, user=self.member)
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url("edit", self.action),
            self.form_data(
                title=self.action.title,
                initial=1,
                rows=[{"id": original_target.pk, "user": self.other_member.pk}],
                linked_threads=[str(self.visible_thread.pk)],
            ),
        )
        self.assertRedirects(response, self.manage_detail_url(), fetch_redirect_response=False)
        original_target.refresh_from_db()
        self.assertEqual(original_target.user, self.other_member)
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_active)
        self.assertIsNotNone(self.assignment.unassigned_at)
        new_assignment = ActionAssignment.objects.get(action=self.action, user=self.other_member)
        self.assertTrue(new_assignment.is_active)
        self.assertTrue(AuditLog.objects.filter(
            target_type="ActionTarget", target_id=str(original_target.pk), action=AuditLog.Action.UPDATE,
        ).exists())
        self.assertTrue(AuditLog.objects.filter(
            target_type="ActionAssignment", target_id=str(self.assignment.pk), action=AuditLog.Action.REMOVE,
        ).exists())
        self.assertTrue(AuditLog.objects.filter(
            target_type="ActionAssignment", target_id=str(new_assignment.pk), action=AuditLog.Action.ASSIGN,
        ).exists())
        self.assertEqual(Notification.objects.filter(source_type="Action", source_id=str(self.action.pk)).count(), 2)

    def test_edit_can_add_and_delete_target_rows(self):
        initial_target = ActionTarget.objects.create(action=self.action, user=self.member)
        self.client.force_login(self.manager)
        response = self.client.post(
            self.url("edit", self.action),
            self.form_data(
                title=self.action.title,
                initial=1,
                rows=[
                    {"id": initial_target.pk, "user": self.member.pk, "DELETE": "on"},
                    {"user": self.other_member.pk},
                ],
                linked_threads=[str(self.visible_thread.pk)],
            ),
        )
        self.assertRedirects(response, self.manage_detail_url(), fetch_redirect_response=False)
        self.assertFalse(ActionTarget.objects.filter(pk=initial_target.pk).exists())
        self.assertEqual(set(self.action.targets.values_list("user_id", flat=True)), {self.other_member.pk})
        self.assertTrue(AuditLog.objects.filter(
            target_type="ActionTarget", target_id=str(initial_target.pk), action=AuditLog.Action.DELETE,
        ).exists())
        self.assertTrue(ActionAssignment.objects.get(action=self.action, user=self.other_member).is_active)

    def test_get_delete_confirmation_does_not_delete(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.url("delete", self.action))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Action.objects.filter(pk=self.action.pk).exists())

    def test_delete_removes_action_targets_and_assignments_with_audit(self):
        ActionTarget.objects.create(action=self.action, user=self.member)
        action_id = self.action.pk
        self.client.force_login(self.manager)
        response = self.client.post(self.url("delete", self.action))
        self.assertRedirects(response, self.url("manage_list"), fetch_redirect_response=False)
        self.assertFalse(Action.objects.filter(pk=action_id).exists())
        self.assertFalse(ActionTarget.objects.filter(action_id=action_id).exists())
        self.assertFalse(ActionAssignment.objects.filter(action_id=action_id).exists())
        audit = AuditLog.objects.get(target_type="Action", target_id=str(action_id), action=AuditLog.Action.DELETE)
        self.assertEqual(audit.actor, self.manager)
        self.assertEqual(audit.old_value["title"], "Test Action")

    def test_sync_only_allows_post(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url("sync_assignments", self.action)).status_code, 405)

    def test_sync_requires_change_and_view_permissions(self):
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.post(self.url("sync_assignments", self.action)).status_code, 403)
        self.client.force_login(self.add_only)
        self.assertEqual(self.client.post(self.url("sync_assignments", self.action)).status_code, 403)

    def test_create_rolls_back_all_writes_if_synchronization_fails(self):
        self.client.force_login(self.manager)
        with patch("actions.views.sync_action_assignments", side_effect=RuntimeError("Sync failed")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.url("create"),
                    self.form_data(title="Atomic Creation", rows=[{"user": self.other_member.pk}]),
                )
        self.assertFalse(Action.objects.filter(title="Atomic Creation").exists())
        self.assertFalse(AuditLog.objects.filter(target_type="Action", target_label="Atomic Creation").exists())

    def test_edit_rolls_back_all_writes_if_synchronization_fails(self):
        target = ActionTarget.objects.create(action=self.action, user=self.member)
        self.client.force_login(self.manager)
        with patch("actions.views.sync_action_assignments", side_effect=RuntimeError("Sync failed")):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.url("edit", self.action),
                    self.form_data(
                        title="Uncommitted Edit",
                        initial=1,
                        rows=[{"id": target.pk, "user": self.other_member.pk}],
                        linked_threads=[str(self.visible_thread.pk)],
                    ),
                )
        self.action.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(self.action.title, "Test Action")
        self.assertEqual(target.user, self.member)
        self.assertFalse(AuditLog.objects.filter(target_type="Action", target_id=str(self.action.pk)).exists())


class ActionServiceTests(ActionTestBase):
    def add_group_member(self, group, user):
        return GroupMembership.objects.create(
            user=user,
            community_group=group,
            started_at=timezone.localdate(),
            changed_by=self.manager,
        )

    def test_direct_target_matches_only_active_members(self):
        for user, matches in (
            (self.member, {self.member.pk}),
            (self.pending, set()),
            (self.inactive, set()),
        ):
            with self.subTest(user=user.username):
                target = ActionTarget(action=self.action, user=user)
                self.assertEqual(resolve_action_target(target), matches)

    def test_group_target_matches_only_active_group_members(self):
        group = CommunityGroup.objects.create(name="Action Group")
        self.add_group_member(group, self.member)
        self.add_group_member(group, self.other_member)
        self.add_group_member(group, self.pending)
        target = ActionTarget.objects.create(action=self.action, community_group=group)
        self.assertEqual(
            resolve_action_target(target),
            {self.member.pk, self.other_member.pk},
        )

    def test_multiple_selectors_in_one_target_use_intersection(self):
        group = CommunityGroup.objects.create(name="Action Group")
        household = Household.objects.create(name="Action Household")
        self.add_group_member(group, self.member)
        self.add_group_member(group, self.other_member)
        HouseholdMembership.objects.create(
            user=self.member,
            household=household,
            started_at=timezone.localdate(),
            changed_by=self.manager,
        )
        target = ActionTarget.objects.create(
            action=self.action,
            community_group=group,
            household=household,
        )
        self.assertEqual(resolve_action_target(target), {self.member.pk})

    def test_separate_targets_are_combined_without_duplicate_assignments(self):
        group = CommunityGroup.objects.create(name="Action Group")
        self.add_group_member(group, self.member)
        self.add_group_member(group, self.other_member)
        ActionTarget.objects.create(action=self.action, user=self.member)
        ActionTarget.objects.create(action=self.action, community_group=group)
        self.assertEqual(
            resolve_action_targets(self.action),
            {self.member.pk, self.other_member.pk},
        )
        activated, deactivated = sync_action_assignments(self.action, actor=self.manager)
        self.assertEqual(len(activated), 1)
        self.assertEqual(deactivated, [])
        self.assertEqual(
            set(self.action.assignments.values_list("user_id", flat=True)),
            {self.member.pk, self.other_member.pk},
        )
        activated_again, removed_again = sync_action_assignments(self.action, actor=self.manager)
        self.assertEqual(activated_again, [])
        self.assertEqual(removed_again, [])
        self.assertEqual(self.action.assignments.count(), 2)
        self.assertEqual(
            Notification.objects.filter(source_type="Action", source_id=str(self.action.pk)).count(),
            1,
        )

    def test_sync_deactivates_and_reactivates_existing_assignment(self):
        target = ActionTarget.objects.create(action=self.action, user=self.member)
        self.assignment.mark_opened()
        original_assigned_at = self.assignment.assigned_at
        activated, removed = sync_action_assignments(self.action, actor=self.manager)
        self.assertEqual(activated, [])
        self.assertEqual(removed, [])
        target.delete()
        activated, removed = sync_action_assignments(self.action, actor=self.manager)
        self.assertEqual(activated, [])
        self.assertEqual(len(removed), 1)
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_active)
        self.assertIsNotNone(self.assignment.unassigned_at)
        self.assertEqual(self.assignment.status, ActionAssignment.Status.OPENED)
        ActionTarget.objects.create(action=self.action, user=self.member)
        activated, removed = sync_action_assignments(self.action, actor=self.manager)
        self.assertEqual(len(activated), 1)
        self.assertEqual(removed, [])
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_active)
        self.assertIsNone(self.assignment.unassigned_at)
        self.assertEqual(self.assignment.status, ActionAssignment.Status.OPENED)
        self.assertEqual(self.assignment.assigned_at, original_assigned_at)
        self.assertEqual(
            list(Notification.objects.filter(
                user=self.member, source_type="Action", source_id=str(self.action.pk)
            ).values_list("title", flat=True)),
            ["New action: Test Action", "Action assignment removed: Test Action"],
        )

    def test_sync_no_targets_removes_active_assignments(self):
        activated, removed = sync_action_assignments(self.action, actor=self.manager)
        self.assertEqual(activated, [])
        self.assertEqual([a.pk for a in removed], [self.assignment.pk])
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.is_active)
        self.assertIsNotNone(self.assignment.unassigned_at)

    def test_target_model_rejects_empty_or_mixed_selectors(self):
        group = CommunityGroup.objects.create(name="Action Group")
        with self.assertRaises(ValidationError):
            ActionTarget(action=self.action).full_clean()
        with self.assertRaises(ValidationError):
            ActionTarget(
                action=self.action, user=self.member, community_group=group,
            ).full_clean()

    def test_assignment_model_rejects_inconsistent_status_timestamps(self):
        now = timezone.now()
        for kwargs in (
            {"status": ActionAssignment.Status.OPENED},
            {"status": ActionAssignment.Status.COMPLETED, "opened_at": now},
            {"status": ActionAssignment.Status.NOT_STARTED, "opened_at": now},
            {"is_active": False},
            {
                "status": ActionAssignment.Status.COMPLETED,
                "opened_at": now,
                "completed_at": now - timedelta(minutes=1),
            },
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValidationError):
                    ActionAssignment(
                        action=self.action,
                        user=self.other_member,
                        **kwargs,
                    ).full_clean()


class ActionAttentionTests(ActionTestBase):
    def test_attention_includes_only_active_outstanding_user_actions(self):
        due = self.make_action("Due Action", deadline=timezone.now() + timedelta(hours=1))
        done = self.make_action("Done Action")
        inactive = self.make_action("Inactive Action")
        someone_else = self.make_action("Someone Else Action")
        self.assign(due, self.member)
        self.assign(done, self.member, status=ActionAssignment.Status.COMPLETED)
        self.assign(inactive, self.member, active=False)
        self.assign(someone_else, self.other_member)
        items = get_action_attention_items(self.member)
        self.assertEqual([item["title"] for item in items], ["Due Action", "Test Action"])
        self.assertEqual(items[0]["target_url"], self.url("detail", due))
        self.assertEqual(items[0]["date_label"], "Due")
        self.assertEqual(items[0]["type"], "action")
        self.assertEqual(items[1]["attention_date"], None)

    def test_attention_changes_after_action_completion(self):
        self.assertEqual(len(get_action_attention_items(self.member)), 1)
        self.assignment.mark_completed()
        self.assertEqual(get_action_attention_items(self.member), [])

    def test_combined_attention_includes_actions(self):
        items = get_needs_attention_items(self.member)
        action_items = [item for item in items if item["type"] == "action"]
        self.assertEqual(len(action_items), 1)
        self.assertEqual(action_items[0]["title"], self.action.title)

    def test_my_eldvatten_todo_excludes_completed_and_inactive_actions(self):
        done = self.make_action("Completed To-Do")
        inactive = self.make_action("Inactive To-Do")
        self.assign(done, self.member, status=ActionAssignment.Status.COMPLETED)
        self.assign(inactive, self.member, active=False)
        todo = get_todo_context(self.member)
        self.assertEqual(
            [assignment.action_id for assignment in todo["todo_actions"]],
            [self.action.id],
        )

    def test_tavern_rail_uses_combined_attention_context(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("community:forum_index"))
        self.assertEqual(response.status_code, 200)
        action_items = [
            item for item in response.context["needs_attention_items"]
            if item["type"] == "action"
        ]
        self.assertEqual(len(action_items), 1)
        self.assertEqual(action_items[0]["target_url"], self.member_detail_url())
        self.assertContains(response, "Needs Attention")
        self.assertContains(response, self.action.title)
