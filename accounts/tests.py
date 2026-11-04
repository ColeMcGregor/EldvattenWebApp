from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from django.utils.formats import date_format

from accounts.models import AccountStatus
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
            body="My reply to another member's thread.",
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
