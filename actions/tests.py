
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus
from community.models import (
    ForumBoard,
    ForumBoardTarget,
    ForumCategory,
    ForumThread,
    ForumThreadTarget,
)

from .forms import ActionForm
from .models import Action, ActionAssignment


User = get_user_model()


class ActionLinkedThreadTests(TestCase):

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

        view_action_permission = Permission.objects.get(
            codename="view_action",
            content_type__app_label="actions",
        )

        cls.manager.user_permissions.add(
            view_action_permission,
        )

        cls.category = ForumCategory.objects.create(
            name="Action Test Category",
        )

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

        cls.board_restricted_thread = (
            ForumThread.objects.create(
                board=cls.restricted_board,
                title="Private Board Discussion",
                created_by=cls.other_member,
            )
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
            status=ActionAssignment.Status.OPENED,
            is_active=True,
        )

    def member_detail_url(self):
        return reverse(
            "actions:detail",
            args=[self.action.pk],
        )

    def manage_detail_url(self):
        return reverse(
            "actions:manage_detail",
            args=[self.action.pk],
        )

    def assert_thread_visible(self, response, thread):
        self.assertContains(
            response,
            thread.title,
        )

        self.assertContains(
            response,
            reverse(
                "community:thread_detail",
                args=[thread.pk],
            ),
        )

    def assert_thread_hidden(self, response, thread):
        self.assertNotContains(
            response,
            thread.title,
        )

        self.assertNotContains(
            response,
            reverse(
                "community:thread_detail",
                args=[thread.pk],
            ),
        )

    def test_action_form_uses_linked_threads(self):
        form = ActionForm()

        self.assertIn(
            "linked_threads",
            form.fields,
        )

        self.assertNotIn(
            "linked_posts",
            form.fields,
        )

    def test_member_sees_accessible_linked_thread(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_visible(
            response,
            self.visible_thread,
        )

    def test_member_cannot_see_restricted_thread(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_hidden(
            response,
            self.restricted_thread,
        )

    def test_member_cannot_see_thread_in_restricted_board(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_hidden(
            response,
            self.board_restricted_thread,
        )

    def test_member_cannot_see_archived_thread(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_hidden(
            response,
            self.archived_thread,
        )

    def test_member_cannot_see_thread_in_archived_board(self):
        self.restricted_board.archived_at = timezone.now()
        self.restricted_board.save(
            update_fields=["archived_at"],
        )

        self.client.force_login(self.other_member)

        ActionAssignment.objects.create(
            action=self.action,
            user=self.other_member,
            status=ActionAssignment.Status.OPENED,
            is_active=True,
        )

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_hidden(
            response,
            self.board_restricted_thread,
        )

    def test_member_cannot_see_thread_in_archived_category(self):
        self.category.archived_at = timezone.now()
        self.category.save(
            update_fields=["archived_at"],
        )

        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_hidden(
            response,
            self.visible_thread,
        )

    def test_member_context_contains_only_accessible_threads(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        visible_thread_ids = {
            thread.pk
            for thread in response.context[
                "visible_linked_threads"
            ]
        }

        self.assertEqual(
            visible_thread_ids,
            {self.visible_thread.pk},
        )

    def test_unassigned_member_cannot_view_action(self):
        self.client.force_login(self.other_member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_inactive_assignment_cannot_view_action(self):
        self.assignment.is_active = False
        self.assignment.save(
            update_fields=["is_active"],
        )

        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            404,
        )

    def test_anonymous_user_cannot_view_action(self):
        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_action_manager_sees_accessible_threads(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            self.manage_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_visible(
            response,
            self.visible_thread,
        )

    def test_action_manager_cannot_see_restricted_threads(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            self.manage_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assert_thread_hidden(
            response,
            self.restricted_thread,
        )

        self.assert_thread_hidden(
            response,
            self.board_restricted_thread,
        )

        self.assert_thread_hidden(
            response,
            self.archived_thread,
        )

    def test_manager_context_contains_only_accessible_threads(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            self.manage_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        visible_thread_ids = {
            thread.pk
            for thread in response.context[
                "visible_linked_threads"
            ]
        }

        self.assertEqual(
            visible_thread_ids,
            {self.visible_thread.pk},
        )

    def test_member_cannot_access_action_management(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.manage_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_action_without_links_has_no_related_threads_section(self):
        self.action.linked_threads.clear()

        self.client.force_login(self.member)

        response = self.client.get(
            self.member_detail_url(),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            list(
                response.context[
                    "visible_linked_threads"
                ]
            ),
            [],
        )

        self.assertNotContains(
            response,
            "Related Tavern Threads",
        )

    def test_target_change_updates_visible_threads(self):
        self.client.force_login(self.member)

        initial_response = self.client.get(
            self.member_detail_url(),
        )

        self.assert_thread_hidden(
            initial_response,
            self.restricted_thread,
        )

        ForumThreadTarget.objects.filter(
            thread=self.restricted_thread,
        ).delete()

        ForumThreadTarget.objects.create(
            thread=self.restricted_thread,
            user=self.member,
        )

        updated_response = self.client.get(
            self.member_detail_url(),
        )

        self.assert_thread_visible(
            updated_response,
            self.restricted_thread,
        )
