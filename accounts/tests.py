
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.formats import date_format

from accounts.forms import AccountStatusForm
from accounts.models import AccountStatus
from accounts.services import (
    change_account_status,
    get_allowed_account_statuses,
    set_account_active,
    set_account_groups,
)
from audit.models import AuditLog
from community.models import (
    ForumBoard,
    ForumBoardTarget,
    ForumCategory,
    ForumPost,
    ForumThread,
    ForumThreadTarget,
)


User = get_user_model()


class MyEldvattenPostsTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(
            username="posts_member",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )

        cls.other_member = User.objects.create_user(
            username="posts_other_member",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )

        cls.category = ForumCategory.objects.create(
            name="Posts Test Category",
        )

        cls.board = ForumBoard.objects.create(
            category=cls.category,
            name="Posts Test Board",
        )

        cls.thread = ForumThread.objects.create(
            board=cls.board,
            title="Member Discussion Thread",
            created_by=cls.member,
        )

        cls.post = ForumPost.objects.create(
            thread=cls.thread,
            author=cls.member,
            body="Unique member message for My Posts tests.",
        )

    def posts_response(self, user=None, user_agent=""):
        self.client.force_login(user or self.member)

        response = self.client.get(
            reverse("my_eldvatten") + "?section=posts",
            HTTP_USER_AGENT=user_agent,
        )

        self.assertEqual(response.status_code, 200)
        return response

    def visible_post_ids(self, response):
        return {
            post.pk
            for post in response.context["my_posts"]
        }

    def assert_post_hidden(self, response, post):
        self.assertNotIn(
            post.pk,
            self.visible_post_ids(response),
        )
        self.assertNotContains(response, escape(post.body))

    def archive(self, object_to_archive):
        object_to_archive.archived_at = timezone.now()
        object_to_archive.save(update_fields=["archived_at"])

    def test_desktop_renders_post_and_direct_link(self):
        response = self.posts_response()

        self.assertTemplateUsed(
            response,
            "accounts/my_eldvatten_desktop.html",
        )
        self.assertTemplateUsed(
            response,
            "accounts/my_eldvatten/posts.html",
        )
        self.assertEqual(
            self.visible_post_ids(response),
            {self.post.pk},
        )
        self.assertContains(response, self.category.name)
        self.assertContains(response, self.board.name)
        self.assertContains(response, self.thread.title)
        self.assertContains(response, escape(self.post.body))
        self.assertContains(
            response,
            reverse(
                "community:thread_detail",
                args=[self.thread.pk],
            ) + f"#post-{self.post.pk}",
        )

    def test_replies_to_other_members_threads_are_included(self):
        other_thread = ForumThread.objects.create(
            board=self.board,
            title="Another Member's Discussion",
            created_by=self.other_member,
        )
        reply = ForumPost.objects.create(
            thread=other_thread,
            author=self.member,
            body="Unique reply to another member's thread.",
        )

        response = self.posts_response()

        self.assertEqual(
            self.visible_post_ids(response),
            {self.post.pk, reply.pk},
        )
        self.assertContains(response, escape(reply.body))

    def test_other_members_posts_are_excluded(self):
        other_post = ForumPost.objects.create(
            thread=self.thread,
            author=self.other_member,
            body="Different author private test content.",
        )

        response = self.posts_response()

        self.assert_post_hidden(response, other_post)
        self.assertIn(self.post.pk, self.visible_post_ids(response))

    def test_posts_are_ordered_newest_first(self):
        older_date = timezone.now() - timedelta(days=2)
        ForumPost.objects.filter(pk=self.post.pk).update(
            created_at=older_date,
        )
        newer_post = ForumPost.objects.create(
            thread=self.thread,
            author=self.member,
            body="Newer member post body.",
        )

        response = self.posts_response()

        self.assertEqual(
            [post.pk for post in response.context["my_posts"]],
            [newer_post.pk, self.post.pk],
        )

    def test_archived_post_is_excluded(self):
        self.archive(self.post)
        self.assert_post_hidden(self.posts_response(), self.post)

    def test_post_in_archived_thread_is_excluded(self):
        self.archive(self.thread)
        self.assert_post_hidden(self.posts_response(), self.post)

    def test_post_in_archived_board_is_excluded(self):
        self.archive(self.board)
        self.assert_post_hidden(self.posts_response(), self.post)

    def test_post_in_archived_category_is_excluded(self):
        self.archive(self.category)
        self.assert_post_hidden(self.posts_response(), self.post)

    def test_thread_target_restricts_own_posts(self):
        ForumThreadTarget.objects.create(
            thread=self.thread,
            user=self.other_member,
        )

        self.assert_post_hidden(self.posts_response(), self.post)

    def test_board_target_restricts_own_posts(self):
        ForumBoardTarget.objects.create(
            board=self.board,
            user=self.other_member,
        )

        self.assert_post_hidden(self.posts_response(), self.post)

    def test_thread_target_including_member_allows_post(self):
        ForumThreadTarget.objects.create(
            thread=self.thread,
            user=self.other_member,
        )
        ForumThreadTarget.objects.create(
            thread=self.thread,
            user=self.member,
        )

        self.assertIn(
            self.post.pk,
            self.visible_post_ids(self.posts_response()),
        )

    def test_updated_thread_targets_change_visibility(self):
        ForumThreadTarget.objects.create(
            thread=self.thread,
            user=self.other_member,
        )

        self.assert_post_hidden(self.posts_response(), self.post)

        ForumThreadTarget.objects.filter(thread=self.thread).delete()
        response = self.posts_response()

        self.assertIn(
            self.post.pk,
            self.visible_post_ids(response),
        )

    def test_suspended_member_does_not_see_own_posts(self):
        self.member.account_status = AccountStatus.SUSPENDED
        self.member.save(update_fields=["account_status"])

        self.assert_post_hidden(self.posts_response(), self.post)

    def test_pending_member_can_see_own_posts(self):
        pending_user = User.objects.create_user(
            username="posts_pending_member",
            password="test-password",
            account_status=AccountStatus.PENDING,
        )
        pending_post = ForumPost.objects.create(
            thread=self.thread,
            author=pending_user,
            body="Pending member's own forum post.",
        )

        response = self.posts_response(user=pending_user)

        self.assertEqual(
            self.visible_post_ids(response),
            {pending_post.pk},
        )
        self.assertContains(response, escape(pending_post.body))

    def test_empty_state_is_displayed_without_posts(self):
        self.post.delete()
        response = self.posts_response()

        self.assertEqual(response.context["my_posts"], [])
        self.assertContains(
            response,
            "You have no accessible posts to display.",
        )

    def test_edited_post_displays_edit_date(self):
        self.post.edited_at = timezone.now()
        self.post.save(update_fields=["edited_at"])

        response = self.posts_response()

        self.assertContains(
            response,
            "Edited " + date_format(
                timezone.localtime(self.post.edited_at),
                "M j, Y",
            ),
        )

    def test_mobile_uses_the_same_posts_template(self):
        response = self.posts_response(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
        )

        self.assertTemplateUsed(
            response,
            "accounts/my_eldvatten_mobile.html",
        )
        self.assertTemplateUsed(
            response,
            "accounts/my_eldvatten/posts.html",
        )
        self.assertContains(response, escape(self.post.body))

    def test_anonymous_user_is_redirected(self):
        response = self.client.get(
            reverse("my_eldvatten") + "?section=posts",
        )

        self.assertEqual(response.status_code, 302)


class AccountManagementTestBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.administrator = User.objects.create_superuser(
            username="account_admin",
            email="admin@example.com",
            password="test-password",
        )

        cls.approver = User.objects.create_user(
            username="account_approver",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )

        cls.manager = User.objects.create_user(
            username="account_manager",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )

        cls.member = User.objects.create_user(
            username="account_member",
            display_name="Test Member",
            email="member@example.com",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )

        cls.pending = User.objects.create_user(
            username="account_pending",
            password="test-password",
            account_status=AccountStatus.PENDING,
        )

        cls.staff = User.objects.create_user(
            username="account_staff",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            is_staff=True,
        )

        cls.other_administrator = (
            User.objects.create_superuser(
                username="account_other_admin",
                email="otheradmin@example.com",
                password="test-password",
            )
        )

        cls.approval_permission = Permission.objects.get(
            content_type__app_label="accounts",
            codename="approve_membership",
        )

        cls.management_permission = Permission.objects.get(
            content_type__app_label="accounts",
            codename="change_user",
        )

        cls.approver.user_permissions.add(
            cls.approval_permission,
        )

        cls.manager.user_permissions.add(
            cls.management_permission,
        )

        cls.first_group = Group.objects.create(
            name="Accounts Test Role One",
        )

        cls.second_group = Group.objects.create(
            name="Accounts Test Role Two",
        )

    def setUp(self):
        self.factory = RequestFactory()

    def make_request(self, actor):
        request = self.factory.post(
            "/administration/accounts/members/",
        )

        request.user = actor

        return request

    def detail_url(self, account):
        return reverse(
            "administration:account_detail",
            kwargs={
                "user_id": account.pk,
            },
        )

    def login_as(self, user):
        self.client.force_login(user)

    def change_status(
        self,
        *,
        actor,
        account,
        status,
    ):
        return change_account_status(
            account=account,
            status=status,
            request=self.make_request(actor),
        )

    def post_status(self, account, status):
        return self.client.post(
            self.detail_url(account),
            {
                "action": "status",
                "account_status": status,
            },
        )


class AccountStatusPermissionTests(
    AccountManagementTestBase
):

    def test_approver_can_approve_pending_account(self):
        result = self.change_status(
            actor=self.approver,
            account=self.pending,
            status=AccountStatus.MEMBER,
        )

        self.pending.refresh_from_db()

        self.assertEqual(
            result.account_status,
            AccountStatus.MEMBER,
        )

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.MEMBER,
        )

    def test_approver_can_reject_pending_account(self):
        self.change_status(
            actor=self.approver,
            account=self.pending,
            status=AccountStatus.REJECTED,
        )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.REJECTED,
        )

    def test_approver_cannot_disable_pending_account(self):
        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.approver,
                account=self.pending,
                status=AccountStatus.DISABLED,
            )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.PENDING,
        )

    def test_approver_cannot_suspend_member(self):
        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.approver,
                account=self.member,
                status=AccountStatus.SUSPENDED,
            )

        self.member.refresh_from_db()

        self.assertEqual(
            self.member.account_status,
            AccountStatus.MEMBER,
        )

    def test_manager_can_suspend_member(self):
        self.change_status(
            actor=self.manager,
            account=self.member,
            status=AccountStatus.SUSPENDED,
        )

        self.member.refresh_from_db()

        self.assertEqual(
            self.member.account_status,
            AccountStatus.SUSPENDED,
        )

    def test_manager_can_restore_suspended_member(self):
        self.member.account_status = (
            AccountStatus.SUSPENDED
        )

        self.member.save(
            update_fields=["account_status"],
        )

        self.change_status(
            actor=self.manager,
            account=self.member,
            status=AccountStatus.MEMBER,
        )

        self.member.refresh_from_db()

        self.assertEqual(
            self.member.account_status,
            AccountStatus.MEMBER,
        )

    def test_manager_can_return_rejected_to_pending(self):
        self.pending.account_status = (
            AccountStatus.REJECTED
        )

        self.pending.save(
            update_fields=["account_status"],
        )

        self.change_status(
            actor=self.manager,
            account=self.pending,
            status=AccountStatus.PENDING,
        )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.PENDING,
        )

    def test_manager_can_disable_member(self):
        self.change_status(
            actor=self.manager,
            account=self.member,
            status=AccountStatus.DISABLED,
        )

        self.member.refresh_from_db()

        self.assertEqual(
            self.member.account_status,
            AccountStatus.DISABLED,
        )

    def test_invalid_transition_is_rejected(self):
        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.administrator,
                account=self.pending,
                status=AccountStatus.SUSPENDED,
            )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.PENDING,
        )

    def test_ordinary_member_cannot_change_status(self):
        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.member,
                account=self.pending,
                status=AccountStatus.MEMBER,
            )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.PENDING,
        )

    def test_manager_cannot_modify_staff_account(self):
        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.manager,
                account=self.staff,
                status=AccountStatus.SUSPENDED,
            )

        self.staff.refresh_from_db()

        self.assertEqual(
            self.staff.account_status,
            AccountStatus.MEMBER,
        )

    def test_administrator_can_modify_staff_account(self):
        self.change_status(
            actor=self.administrator,
            account=self.staff,
            status=AccountStatus.SUSPENDED,
        )

        self.staff.refresh_from_db()

        self.assertEqual(
            self.staff.account_status,
            AccountStatus.SUSPENDED,
        )

    def test_administrator_cannot_modify_self(self):
        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.administrator,
                account=self.administrator,
                status=AccountStatus.DISABLED,
            )

    def test_administrator_cannot_modify_superuser(self):
        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.administrator,
                account=self.other_administrator,
                status=AccountStatus.DISABLED,
            )

    def test_no_op_status_change_creates_no_audit(self):
        original_count = AuditLog.objects.count()

        self.change_status(
            actor=self.manager,
            account=self.member,
            status=AccountStatus.MEMBER,
        )

        self.assertEqual(
            AuditLog.objects.count(),
            original_count,
        )

    def test_approval_creates_correct_audit_record(self):
        self.change_status(
            actor=self.approver,
            account=self.pending,
            status=AccountStatus.MEMBER,
        )

        log = AuditLog.objects.get(
            target_type="user account",
            target_id=str(self.pending.pk),
            action=AuditLog.Action.APPROVE,
        )

        self.assertEqual(
            log.actor,
            self.approver,
        )

        self.assertEqual(
            log.old_value["account_status"],
            AccountStatus.PENDING,
        )

        self.assertEqual(
            log.new_value["account_status"],
            AccountStatus.MEMBER,
        )

    def test_suspension_creates_correct_audit_record(self):
        self.change_status(
            actor=self.manager,
            account=self.member,
            status=AccountStatus.SUSPENDED,
        )

        log = AuditLog.objects.get(
            target_type="user account",
            target_id=str(self.member.pk),
            action=AuditLog.Action.SUSPEND,
        )

        self.assertEqual(
            log.new_value["account_status"],
            AccountStatus.SUSPENDED,
        )


class AccountStatusFormTests(
    AccountManagementTestBase
):

    def test_approver_sees_only_approval_choices(self):
        form = AccountStatusForm(
            instance=self.pending,
            actor=self.approver,
        )

        choices = {
            value
            for value, label
            in form.fields["account_status"].choices
        }

        self.assertEqual(
            choices,
            {
                AccountStatus.MEMBER,
                AccountStatus.REJECTED,
            },
        )

    def test_manager_sees_permitted_transitions(self):
        form = AccountStatusForm(
            instance=self.member,
            actor=self.manager,
        )

        choices = {
            value
            for value, label
            in form.fields["account_status"].choices
        }

        self.assertEqual(
            choices,
            {
                AccountStatus.SUSPENDED,
                AccountStatus.DISABLED,
            },
        )

    def test_staff_account_has_no_choices_for_manager(self):
        form = AccountStatusForm(
            instance=self.staff,
            actor=self.manager,
        )

        self.assertEqual(
            list(
                form.fields["account_status"].choices
            ),
            [],
        )

    def test_unauthorized_status_fails_form_validation(self):
        form = AccountStatusForm(
            data={
                "account_status":
                    AccountStatus.DISABLED,
            },
            instance=self.pending,
            actor=self.approver,
        )

        self.assertFalse(form.is_valid())

        self.assertIn(
            "account_status",
            form.errors,
        )

    def test_service_rejects_forbidden_status_independently(self):
        allowed = get_allowed_account_statuses(
            actor=self.approver,
            account=self.member,
        )

        self.assertEqual(allowed, set())

        with self.assertRaises(PermissionDenied):
            self.change_status(
                actor=self.approver,
                account=self.member,
                status=AccountStatus.DISABLED,
            )


class AccountActivationTests(
    AccountManagementTestBase
):

    def test_full_admin_can_deactivate_account(self):
        set_account_active(
            account=self.member,
            is_active=False,
            request=self.make_request(
                self.administrator
            ),
        )

        self.member.refresh_from_db()

        self.assertFalse(self.member.is_active)

        self.assertTrue(
            AuditLog.objects.filter(
                target_type="user account",
                target_id=str(self.member.pk),
                new_value__is_active=False,
            ).exists()
        )

    def test_full_admin_can_reactivate_account(self):
        self.member.is_active = False
        self.member.save(
            update_fields=["is_active"],
        )

        set_account_active(
            account=self.member,
            is_active=True,
            request=self.make_request(
                self.administrator
            ),
        )

        self.member.refresh_from_db()

        self.assertTrue(self.member.is_active)

    def test_manager_cannot_deactivate_account(self):
        with self.assertRaises(PermissionDenied):
            set_account_active(
                account=self.member,
                is_active=False,
                request=self.make_request(
                    self.manager
                ),
            )

        self.member.refresh_from_db()

        self.assertTrue(self.member.is_active)

    def test_approver_cannot_deactivate_account(self):
        with self.assertRaises(PermissionDenied):
            set_account_active(
                account=self.member,
                is_active=False,
                request=self.make_request(
                    self.approver
                ),
            )

    def test_administrator_cannot_deactivate_self(self):
        with self.assertRaises(PermissionDenied):
            set_account_active(
                account=self.administrator,
                is_active=False,
                request=self.make_request(
                    self.administrator
                ),
            )

    def test_administrator_cannot_deactivate_superuser(self):
        with self.assertRaises(PermissionDenied):
            set_account_active(
                account=self.other_administrator,
                is_active=False,
                request=self.make_request(
                    self.administrator
                ),
            )

    def test_unchanged_activation_does_not_create_audit(self):
        original_count = AuditLog.objects.count()

        set_account_active(
            account=self.member,
            is_active=True,
            request=self.make_request(
                self.administrator
            ),
        )

        self.assertEqual(
            AuditLog.objects.count(),
            original_count,
        )


class AccountGroupManagementTests(
    AccountManagementTestBase
):

    def test_full_admin_can_assign_group(self):
        set_account_groups(
            account=self.member,
            groups=[self.first_group],
            request=self.make_request(
                self.administrator
            ),
        )

        self.assertTrue(
            self.member.groups.filter(
                pk=self.first_group.pk,
            ).exists()
        )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type="application role",
                target_id=str(self.member.pk),
                action=AuditLog.Action.ASSIGN,
            ).exists()
        )

    def test_full_admin_can_remove_group(self):
        self.member.groups.add(
            self.first_group
        )

        set_account_groups(
            account=self.member,
            groups=[],
            request=self.make_request(
                self.administrator
            ),
        )

        self.assertFalse(
            self.member.groups.filter(
                pk=self.first_group.pk,
            ).exists()
        )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type="application role",
                target_id=str(self.member.pk),
                action=AuditLog.Action.REMOVE,
            ).exists()
        )

    def test_manager_cannot_assign_group(self):
        with self.assertRaises(PermissionDenied):
            set_account_groups(
                account=self.member,
                groups=[self.first_group],
                request=self.make_request(
                    self.manager
                ),
            )

        self.assertFalse(
            self.member.groups.exists()
        )

    def test_approver_cannot_assign_group(self):
        with self.assertRaises(PermissionDenied):
            set_account_groups(
                account=self.member,
                groups=[self.first_group],
                request=self.make_request(
                    self.approver
                ),
            )

    def test_administrator_cannot_change_own_groups(self):
        with self.assertRaises(PermissionDenied):
            set_account_groups(
                account=self.administrator,
                groups=[self.first_group],
                request=self.make_request(
                    self.administrator
                ),
            )

    def test_administrator_cannot_change_superuser_groups(self):
        with self.assertRaises(PermissionDenied):
            set_account_groups(
                account=self.other_administrator,
                groups=[self.first_group],
                request=self.make_request(
                    self.administrator
                ),
            )

    def test_invalid_group_is_rejected(self):
        invalid_group = Group(
            pk=999999,
            name="Nonexistent Role",
        )

        with self.assertRaises(PermissionDenied):
            set_account_groups(
                account=self.member,
                groups=[invalid_group],
                request=self.make_request(
                    self.administrator
                ),
            )

        self.assertFalse(
            self.member.groups.exists()
        )

    def test_group_changes_do_not_set_staff_or_superuser(self):
        set_account_groups(
            account=self.member,
            groups=[self.first_group],
            request=self.make_request(
                self.administrator
            ),
        )

        self.member.refresh_from_db()

        self.assertFalse(self.member.is_staff)
        self.assertFalse(self.member.is_superuser)

    def test_unchanged_groups_do_not_create_audit(self):
        self.member.groups.add(
            self.first_group
        )

        original_count = AuditLog.objects.count()

        set_account_groups(
            account=self.member,
            groups=[self.first_group],
            request=self.make_request(
                self.administrator
            ),
        )

        self.assertEqual(
            AuditLog.objects.count(),
            original_count,
        )


class AccountManagementViewTests(
    AccountManagementTestBase
):

    def test_anonymous_directory_access_redirects(self):
        response = self.client.get(
            reverse("administration:account_list")
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_member_cannot_access_management(self):
        self.login_as(self.member)

        response = self.client.get(
            reverse("administration:account_list")
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_approver_can_access_directory(self):
        self.login_as(self.approver)

        response = self.client.get(
            reverse("administration:account_list")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "administration/accounts.html",
        )

    def test_manager_can_access_account_detail(self):
        self.login_as(self.manager)

        response = self.client.get(
            self.detail_url(self.pending)
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTemplateUsed(
            response,
            "administration/account_detail.html",
        )

    def test_member_cannot_access_account_detail(self):
        self.login_as(self.member)

        response = self.client.get(
            self.detail_url(self.pending)
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_directory_search_finds_username(self):
        self.login_as(self.administrator)

        response = self.client.get(
            reverse("administration:account_list"),
            {
                "search": "account_pending",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        account_ids = {
            account.pk
            for account in response.context["accounts"]
        }

        self.assertIn(
            self.pending.pk,
            account_ids,
        )

        self.assertNotIn(
            self.member.pk,
            account_ids,
        )

    def test_directory_search_finds_email(self):
        self.login_as(self.administrator)

        response = self.client.get(
            reverse("administration:account_list"),
            {
                "search": "member@example.com",
            },
        )

        account_ids = {
            account.pk
            for account in response.context["accounts"]
        }

        self.assertEqual(
            account_ids,
            {self.member.pk},
        )

    def test_directory_filters_pending_accounts(self):
        self.login_as(self.administrator)

        response = self.client.get(
            reverse("administration:account_list"),
            {
                "status": AccountStatus.PENDING,
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            all(
                account.account_status
                == AccountStatus.PENDING
                for account in response.context["accounts"]
            )
        )

    def test_directory_filters_superusers(self):
        self.login_as(self.administrator)

        response = self.client.get(
            reverse("administration:account_list"),
            {
                "role": "superuser",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertTrue(
            all(
                account.is_superuser
                for account in response.context["accounts"]
            )
        )

    def test_directory_paginates_accounts(self):
        User.objects.bulk_create([
            User(
                username=f"pagination_user_{index}",
                account_status=AccountStatus.MEMBER,
            )
            for index in range(30)
        ])

        self.login_as(self.administrator)

        response = self.client.get(
            reverse("administration:account_list")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            len(response.context["accounts"]),
            25,
        )

        self.assertTrue(
            response.context["page"].has_next()
        )

    def test_approver_can_approve_through_http(self):
        self.login_as(self.approver)

        response = self.post_status(
            self.pending,
            AccountStatus.MEMBER,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.MEMBER,
        )

    def test_approver_cannot_disable_through_http(self):
        self.login_as(self.approver)

        response = self.post_status(
            self.pending,
            AccountStatus.DISABLED,
        )

        self.assertNotEqual(
            response.status_code,
            302,
        )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.PENDING,
        )

    def test_member_cannot_submit_status_change(self):
        self.login_as(self.member)

        response = self.post_status(
            self.pending,
            AccountStatus.MEMBER,
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.pending.refresh_from_db()

        self.assertEqual(
            self.pending.account_status,
            AccountStatus.PENDING,
        )

    def test_manager_cannot_submit_activation_change(self):
        self.login_as(self.manager)

        response = self.client.post(
            self.detail_url(self.member),
            {
                "action": "activation",
                "is_active": "",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.member.refresh_from_db()

        self.assertTrue(self.member.is_active)

    def test_manager_cannot_submit_group_change(self):
        self.login_as(self.manager)

        response = self.client.post(
            self.detail_url(self.member),
            {
                "action": "groups",
                "groups": [
                    str(self.first_group.pk),
                ],
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertFalse(
            self.member.groups.exists()
        )

    def test_full_admin_can_update_activation_through_http(self):
        self.login_as(self.administrator)

        response = self.client.post(
            self.detail_url(self.member),
            {
                "action": "activation",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.member.refresh_from_db()

        self.assertFalse(self.member.is_active)

    def test_full_admin_can_assign_role_through_http(self):
        self.login_as(self.administrator)

        response = self.client.post(
            self.detail_url(self.member),
            {
                "action": "groups",
                "groups": [
                    str(self.first_group.pk),
                ],
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertTrue(
            self.member.groups.filter(
                pk=self.first_group.pk,
            ).exists()
        )

    def test_unknown_management_action_is_rejected(self):
        self.login_as(self.administrator)

        response = self.client.post(
            self.detail_url(self.member),
            {
                "action": "unknown",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_account_detail_displays_audit_history(self):
        self.change_status(
            actor=self.manager,
            account=self.member,
            status=AccountStatus.SUSPENDED,
        )

        self.login_as(self.administrator)

        response = self.client.get(
            self.detail_url(self.member)
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            len(
                response.context[
                    "account_audit_logs"
                ]
            ),
            1,
        )

    def test_delegated_approver_cannot_view_audit_history(self):
        self.change_status(
            actor=self.manager,
            account=self.member,
            status=AccountStatus.SUSPENDED,
        )

        self.login_as(self.approver)

        response = self.client.get(
            self.detail_url(self.member)
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            response.context[
                "account_audit_logs"
            ]
        )
