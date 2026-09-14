from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.utils import timezone
from django.http import HttpResponse
from django.urls import resolve, reverse

from accounts.models import AccountStatus
from audit.models import AuditLog
from organization.models import (
    Chapter,
    ChapterStatus,
    CitizenshipClass,
    CitizenshipRecord,
    CommunityGroup,
    GovernanceBody,
    GovernanceMembership,
    GroupMembership,
    Household,
    HouseholdLeadership,
    HouseholdLeadershipType,
    HouseholdMembership,
    Office,
    Order,
    OrderMembership,
    OrderRank,
    SocialRank,
    UserOffice,
    UserSocialRank,
)

from .models import (
    ForumBoard,
    ForumBoardTarget,
    ForumBoardThreadCreationTarget,
    ForumCategory,
    ForumPost,
    ForumPostAttachment,
    ForumPostQuote,
    ForumPostReport,
    ForumThread,
    ForumThreadReadState,
    ForumThreadSubscription,
    ForumThreadTarget,
)

from .views import (
    board_archive,
    board_lock,
    board_restore,
    board_subscribe,
    board_unlock,
    board_unsubscribe,
    category_archive,
    category_restore,
    post_archive,
    post_report,
    post_report_review,
    post_restore,
    thread_archive,
    thread_follow,
    thread_lock,
    thread_merge,
    thread_move,
    thread_move_posts,
    thread_pin,
    thread_restore,
    thread_split,
    thread_unfollow,
    thread_unlock,
    thread_unpin,
)

from .services import (
    archive_forum_board,
    archive_forum_category,
    archive_forum_post,
    archive_forum_thread,
    create_forum_post,
    create_forum_thread,
    edit_forum_post,
    edit_forum_thread,
    get_accessible_boards,
    get_accessible_categories,
    get_accessible_threads,
    mark_thread_read,
    merge_forum_threads,
    move_forum_posts,
    move_forum_thread,
    recalculate_thread_last_post_at,
    restore_forum_board,
    restore_forum_category,
    restore_forum_post,
    restore_forum_thread,
    set_board_locked,
    set_thread_locked,
    set_thread_pinned,
    split_forum_thread,
    thread_creator_controls,
    user_can_access_board,
    user_can_access_thread,
    user_can_add_post,
    user_can_archive_post,
    user_can_archive_thread,
    user_can_change_thread,
    user_can_create_thread,
    user_can_edit_post,
    user_can_manage_forum_boards,
    user_can_manage_forum_categories,
    user_can_read_forum,
    user_can_report_post,
    user_can_restore_post,
    user_can_restore_thread,
    user_can_view_archived_forum,
    user_is_forum_member,
    user_is_forum_moderator,
)
from .views import (
    board_archive,
    board_lock,
    board_restore,
    board_subscribe,
    board_unlock,
    board_unsubscribe,
    category_archive,
    category_restore,
    post_archive,
    post_report,
    post_restore,
    thread_archive,
    thread_follow,
    thread_lock,
    thread_merge,
    thread_move,
    thread_move_posts,
    thread_pin,
    thread_restore,
    thread_split,
    thread_unfollow,
    thread_unlock,
    thread_unpin,
)
from .forms import (
    ForumBoardTargetForm,
    ForumBoardThreadCreationTargetFormSet,
    ForumDraftContentForm,
    ForumPostMoveForm,
    ForumThreadMergeForm,
    ForumThreadMoveForm,
    ForumThreadSplitForm,
)


User = get_user_model()


class ForumPermissionFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.assignment_start = date(2026, 1, 1)

        cls.actor = cls.create_user(
            "permission_actor",
            is_staff=True,
            is_superuser=True,
        )

        cls.member = cls.create_user(
            "member",
        )

        cls.same_chapter_member = cls.create_user(
            "same_chapter_member",
        )

        cls.outside_board_member = cls.create_user(
            "outside_board_member",
        )

        cls.other_member = cls.create_user(
            "other_member",
        )

        cls.pending_user = cls.create_user(
            "pending_user",
            status=AccountStatus.PENDING,
        )

        cls.suspended_user = cls.create_user(
            "suspended_user",
            status=AccountStatus.SUSPENDED,
        )

        cls.disabled_user = cls.create_user(
            "disabled_user",
            status=AccountStatus.DISABLED,
            is_active=False,
        )

        cls.staff_user = cls.create_user(
            "staff_user",
            is_staff=True,
        )

        cls.moderator = cls.create_user(
            "moderator",
            is_staff=True,
        )

        cls.archive_viewer = cls.create_user(
            "archive_viewer",
            is_staff=True,
        )

        cls.board_manager = cls.create_user(
            "board_manager",
            is_staff=True,
        )

        cls.category_manager = cls.create_user(
            "category_manager",
            is_staff=True,
        )

        cls.hard_delete_user = cls.create_user(
            "hard_delete_user",
            is_staff=True,
        )

        cls.grant_permission(
            cls.moderator,
            "moderate_forum",
        )

        cls.grant_permission(
            cls.archive_viewer,
            "view_archived_forum_content",
        )

        cls.grant_permission(
            cls.board_manager,
            "manage_forum_boards",
        )

        cls.grant_permission(
            cls.category_manager,
            "manage_forum_categories",
        )

        cls.grant_permission(
            cls.hard_delete_user,
            "hard_delete_forum_content",
        )

        cls.normal_status = ChapterStatus.objects.create(
            name="Normal",
            allows_new_citizens=True,
        )

        cls.active_citizen = CitizenshipClass.objects.create(
            name="Active Citizen",
        )

        cls.honorary_citizen = CitizenshipClass.objects.create(
            name="Honorary Citizen",
        )

        cls.thegn = SocialRank.objects.create(
            name="Thegn",
        )

        cls.karl = SocialRank.objects.create(
            name="Karl",
        )

        cls.lawspeaker = Office.objects.create(
            name="Lawspeaker",
        )

        cls.vard = Office.objects.create(
            name="Vard",
        )

        cls.fyr_draca = Chapter.objects.create(
            name="Fyr Draca Chapter",
            status=cls.normal_status,
        )

        cls.seattle = Chapter.objects.create(
            name="Seattle Chapter",
            status=cls.normal_status,
        )

        cls.kraken = Household.objects.create(
            name="House Kraken",
        )

        cls.hvit_hrafn = Household.objects.create(
            name="House Hvit Hrafn",
        )

        cls.godi_council = GovernanceBody.objects.create(
            name="Godi Council",
        )

        cls.lagstifstande_council = GovernanceBody.objects.create(
            name="Lagstifstande Council",
        )

        cls.fire_order = Order.objects.create(
            name="Order of Fire",
            uses_ranks=True,
        )

        cls.water_order = Order.objects.create(
            name="Order of Water",
            uses_ranks=True,
        )

        cls.ledar = OrderRank.objects.create(
            name="Ledar",
            rank_order=3,
        )

        cls.larling = OrderRank.objects.create(
            name="Larling",
            rank_order=1,
        )

        cls.test_group = CommunityGroup.objects.create(
            name="Test Custom Group",
        )

        cls.leading_jarl = HouseholdLeadershipType.objects.create(
            name="Leading Jarl",
        )

        cls.assign_profile(
            cls.member,
            citizenship_class=cls.active_citizen,
            social_rank=cls.thegn,
            chapter=cls.fyr_draca,
            household=cls.kraken,
            office=cls.lawspeaker,
            governance_body=cls.godi_council,
            order=cls.fire_order,
            order_rank=cls.ledar,
            community_group=cls.test_group,
            leadership_type=cls.leading_jarl,
        )

        cls.assign_profile(
            cls.same_chapter_member,
            citizenship_class=cls.active_citizen,
            social_rank=cls.karl,
            chapter=cls.fyr_draca,
            household=cls.hvit_hrafn,
            office=cls.vard,
            governance_body=cls.lagstifstande_council,
            order=cls.water_order,
            order_rank=cls.larling,
        )

        cls.assign_profile(
            cls.outside_board_member,
            citizenship_class=cls.active_citizen,
            social_rank=cls.thegn,
            chapter=cls.seattle,
            household=cls.kraken,
            office=cls.lawspeaker,
            governance_body=cls.godi_council,
            order=cls.fire_order,
            order_rank=cls.ledar,
        )

        cls.assign_profile(
            cls.other_member,
            citizenship_class=cls.honorary_citizen,
            social_rank=cls.karl,
            chapter=cls.seattle,
            household=cls.hvit_hrafn,
            office=cls.vard,
            governance_body=cls.lagstifstande_council,
            order=cls.water_order,
            order_rank=cls.larling,
        )

    @classmethod
    def create_user(
        cls,
        username,
        *,
        status=AccountStatus.MEMBER,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    ):
        return User.objects.create_user(
            username=username,
            password="testpassword",
            display_name=username,
            email=f"{username}@example.test",
            account_status=status,
            is_active=is_active,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )

    @classmethod
    def grant_permission(cls, user, codename):
        permission = Permission.objects.get(
            content_type__app_label="community",
            codename=codename,
        )

        user.user_permissions.add(permission)

    @classmethod
    def assignment_values(cls):
        return {
            "started_at": cls.assignment_start,
            "changed_by": cls.actor,
            "notes": "Forum permission test assignment.",
        }

    @classmethod
    def assign_profile(
        cls,
        user,
        *,
        citizenship_class,
        social_rank,
        chapter,
        household,
        office,
        governance_body,
        order,
        order_rank,
        community_group=None,
        leadership_type=None,
    ):
        assignment_values = cls.assignment_values()

        CitizenshipRecord.objects.create(
            user=user,
            citizenship_class=citizenship_class,
            chapter=chapter,
            **assignment_values,
        )

        UserSocialRank.objects.create(
            user=user,
            social_rank=social_rank,
            **assignment_values,
        )

        UserOffice.objects.create(
            user=user,
            office=office,
            chapter=chapter,
            **assignment_values,
        )

        HouseholdMembership.objects.create(
            user=user,
            household=household,
            **assignment_values,
        )

        GovernanceMembership.objects.create(
            user=user,
            governance_body=governance_body,
            **assignment_values,
        )

        OrderMembership.objects.create(
            user=user,
            order=order,
            order_rank=order_rank,
            **assignment_values,
        )

        if community_group is not None:
            GroupMembership.objects.create(
                user=user,
                community_group=community_group,
                **assignment_values,
            )

        if leadership_type is not None:
            HouseholdLeadership.objects.create(
                user=user,
                household=household,
                leadership_type=leadership_type,
                **assignment_values,
            )

    def create_category(
        self,
        name,
        *,
        archived=False,
    ):
        return ForumCategory.objects.create(
            name=name,
            archived_at=(
                timezone.now()
                if archived
                else None
            ),
            archived_by=(
                self.actor
                if archived
                else None
            ),
        )

    def create_board(
        self,
        name,
        *,
        category=None,
        policy=ForumBoard.ThreadCreationPolicy.OPEN,
        locked=False,
        archived=False,
    ):
        if category is None:
            category = self.create_category(
                f"{name} Category"
            )

        return ForumBoard.objects.create(
            category=category,
            name=name,
            thread_creation_policy=policy,
            is_locked=locked,
            locked_at=(
                timezone.now()
                if locked
                else None
            ),
            locked_by=(
                self.actor
                if locked
                else None
            ),
            archived_at=(
                timezone.now()
                if archived
                else None
            ),
            archived_by=(
                self.actor
                if archived
                else None
            ),
        )

    def create_thread(
        self,
        board,
        *,
        title="Test Thread",
        creator=None,
        locked=False,
        archived=False,
    ):
        if creator is None:
            creator = self.member

        return ForumThread.objects.create(
            board=board,
            title=title,
            created_by=creator,
            is_locked=locked,
            locked_at=(
                timezone.now()
                if locked
                else None
            ),
            locked_by=(
                self.actor
                if locked
                else None
            ),
            archived_at=(
                timezone.now()
                if archived
                else None
            ),
            archived_by=(
                self.actor
                if archived
                else None
            ),
        )

    def create_post(
        self,
        thread,
        *,
        author=None,
        body="Test post.",
        archived=False,
    ):
        if author is None:
            author = self.member

        return ForumPost.objects.create(
            thread=thread,
            author=author,
            body=body,
            archived_at=(
                timezone.now()
                if archived
                else None
            ),
            archived_by=(
                self.actor
                if archived
                else None
            ),
        )


class ForumAccountPermissionTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_member_can_read_forum(self):
        self.assertTrue(
            user_can_read_forum(
                self.member
            )
        )

    def test_pending_user_can_read_forum(self):
        self.assertTrue(
            user_can_read_forum(
                self.pending_user
            )
        )

    def test_suspended_user_cannot_read_forum(self):
        self.assertFalse(
            user_can_read_forum(
                self.suspended_user
            )
        )

    def test_disabled_user_cannot_read_forum(self):
        self.assertFalse(
            user_can_read_forum(
                self.disabled_user
            )
        )

    def test_anonymous_user_cannot_read_forum(self):
        self.assertFalse(
            user_can_read_forum(
                AnonymousUser()
            )
        )

    def test_only_member_status_is_forum_member(self):
        self.assertTrue(
            user_is_forum_member(
                self.member
            )
        )

        self.assertFalse(
            user_is_forum_member(
                self.pending_user
            )
        )

        self.assertFalse(
            user_is_forum_member(
                self.suspended_user
            )
        )

        self.assertFalse(
            user_is_forum_member(
                self.disabled_user
            )
        )

    def test_staff_status_alone_is_not_forum_authority(self):
        self.assertTrue(
            self.staff_user.is_staff
        )

        self.assertFalse(
            user_is_forum_moderator(
                self.staff_user
            )
        )

        self.assertFalse(
            user_can_manage_forum_boards(
                self.staff_user
            )
        )

        self.assertFalse(
            user_can_manage_forum_categories(
                self.staff_user
            )
        )

        self.assertFalse(
            user_can_view_archived_forum(
                self.staff_user
            )
        )

    def test_moderator_permission_is_independent(self):
        self.assertTrue(
            user_is_forum_moderator(
                self.moderator
            )
        )

        self.assertFalse(
            user_can_manage_forum_boards(
                self.moderator
            )
        )

        self.assertFalse(
            user_can_manage_forum_categories(
                self.moderator
            )
        )

        self.assertFalse(
            user_can_view_archived_forum(
                self.moderator
            )
        )

    def test_board_manager_permission_is_independent(self):
        self.assertTrue(
            user_can_manage_forum_boards(
                self.board_manager
            )
        )

        self.assertFalse(
            user_is_forum_moderator(
                self.board_manager
            )
        )

        self.assertFalse(
            user_can_manage_forum_categories(
                self.board_manager
            )
        )

    def test_category_manager_permission_is_independent(self):
        self.assertTrue(
            user_can_manage_forum_categories(
                self.category_manager
            )
        )

        self.assertFalse(
            user_is_forum_moderator(
                self.category_manager
            )
        )

        self.assertFalse(
            user_can_manage_forum_boards(
                self.category_manager
            )
        )

    def test_archived_view_permission_is_independent(self):
        self.assertTrue(
            user_can_view_archived_forum(
                self.archive_viewer
            )
        )

        self.assertFalse(
            user_is_forum_moderator(
                self.archive_viewer
            )
        )

        self.assertFalse(
            user_can_manage_forum_boards(
                self.archive_viewer
            )
        )

        self.assertFalse(
            user_can_manage_forum_categories(
                self.archive_viewer
            )
        )

    def test_hard_delete_permission_is_independent(self):
        self.assertTrue(
            self.hard_delete_user.has_perm(
                "community.hard_delete_forum_content"
            )
        )

        self.assertFalse(
            user_is_forum_moderator(
                self.hard_delete_user
            )
        )

        self.assertFalse(
            user_can_manage_forum_boards(
                self.hard_delete_user
            )
        )

        self.assertFalse(
            user_can_manage_forum_categories(
                self.hard_delete_user
            )
        )

        self.assertFalse(
            user_can_view_archived_forum(
                self.hard_delete_user
            )
        )

    def test_superuser_has_all_elevated_forum_authority(self):
        self.assertTrue(
            user_is_forum_moderator(
                self.actor
            )
        )

        self.assertTrue(
            user_can_manage_forum_boards(
                self.actor
            )
        )

        self.assertTrue(
            user_can_manage_forum_categories(
                self.actor
            )
        )

        self.assertTrue(
            user_can_view_archived_forum(
                self.actor
            )
        )

        self.assertTrue(
            self.actor.has_perm(
                "community.hard_delete_forum_content"
            )
        )


class ForumTargetPermissionTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_each_target_selector_grants_matching_user_access(self):
        selector_values = {
            "user": self.member,
            "citizenship_class": self.active_citizen,
            "social_rank": self.thegn,
            "office": self.lawspeaker,
            "chapter": self.fyr_draca,
            "household": self.kraken,
            "governance_body": self.godi_council,
            "order": self.fire_order,
            "order_rank": self.ledar,
            "community_group": self.test_group,
            "household_leadership_type": self.leading_jarl,
        }

        for field_name, value in selector_values.items():
            with self.subTest(
                selector=field_name
            ):
                board = self.create_board(
                    f"{field_name} Board"
                )

                ForumBoardTarget.objects.create(
                    board=board,
                    **{
                        field_name: value,
                    },
                )

                self.assertTrue(
                    user_can_access_board(
                        self.member,
                        board,
                    )
                )

                self.assertFalse(
                    user_can_access_board(
                        self.other_member,
                        board,
                    )
                )

    def test_target_fields_use_and_within_one_row(self):
        board = self.create_board(
            "AND Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            chapter=self.fyr_draca,
            office=self.lawspeaker,
        )

        self.assertTrue(
            user_can_access_board(
                self.member,
                board,
            )
        )

        self.assertFalse(
            user_can_access_board(
                self.same_chapter_member,
                board,
            )
        )

        self.assertFalse(
            user_can_access_board(
                self.outside_board_member,
                board,
            )
        )

    def test_target_rows_use_or_between_rows(self):
        board = self.create_board(
            "OR Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            chapter=self.fyr_draca,
        )

        ForumBoardTarget.objects.create(
            board=board,
            household=self.kraken,
        )

        self.assertTrue(
            user_can_access_board(
                self.member,
                board,
            )
        )

        self.assertTrue(
            user_can_access_board(
                self.same_chapter_member,
                board,
            )
        )

        self.assertTrue(
            user_can_access_board(
                self.outside_board_member,
                board,
            )
        )

        self.assertFalse(
            user_can_access_board(
                self.other_member,
                board,
            )
        )

    def test_board_without_targets_allows_read_eligible_users(self):
        board = self.create_board(
            "Untargeted Board"
        )

        self.assertTrue(
            user_can_access_board(
                self.member,
                board,
            )
        )

        self.assertTrue(
            user_can_access_board(
                self.pending_user,
                board,
            )
        )

        self.assertFalse(
            user_can_access_board(
                self.suspended_user,
                board,
            )
        )

        self.assertFalse(
            user_can_access_board(
                self.disabled_user,
                board,
            )
        )

    def test_specific_pending_user_target_can_be_read(self):
        board = self.create_board(
            "Pending User Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            user=self.pending_user,
        )

        self.assertTrue(
            user_can_access_board(
                self.pending_user,
                board,
            )
        )

        self.assertFalse(
            user_can_access_board(
                self.member,
                board,
            )
        )

    def test_ended_assignment_does_not_match_target(self):
        expired_group = CommunityGroup.objects.create(
            name="Expired Test Group"
        )

        GroupMembership.objects.create(
            user=self.other_member,
            community_group=expired_group,
            started_at=date(2025, 1, 1),
            ended_at=date(2025, 12, 31),
            changed_by=self.actor,
        )

        board = self.create_board(
            "Expired Group Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            community_group=expired_group,
        )

        self.assertFalse(
            user_can_access_board(
                self.other_member,
                board,
            )
        )

    def test_target_requires_at_least_one_selector(self):
        board = self.create_board(
            "Invalid Empty Target Board"
        )

        target = ForumBoardTarget(
            board=board,
        )

        with self.assertRaises(
            ValidationError
        ):
            target.full_clean()

    def test_specific_user_cannot_share_target_with_org_selector(self):
        board = self.create_board(
            "Invalid User Target Board"
        )

        target = ForumBoardTarget(
            board=board,
            user=self.member,
            chapter=self.fyr_draca,
        )

        with self.assertRaises(
            ValidationError
        ):
            target.full_clean()


class ForumBoardAndThreadAccessTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_thread_target_can_narrow_board_access(self):
        board = self.create_board(
            "Narrow Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            chapter=self.fyr_draca,
        )

        thread = self.create_thread(
            board,
            title="Kraken Thread",
        )

        ForumThreadTarget.objects.create(
            thread=thread,
            household=self.kraken,
        )

        self.assertTrue(
            user_can_access_thread(
                self.member,
                thread,
            )
        )

        self.assertFalse(
            user_can_access_thread(
                self.same_chapter_member,
                thread,
            )
        )

    def test_thread_target_cannot_broaden_board_access(self):
        board = self.create_board(
            "Outer Boundary Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            chapter=self.fyr_draca,
        )

        thread = self.create_thread(
            board,
            title="Kraken Target Thread",
        )

        ForumThreadTarget.objects.create(
            thread=thread,
            household=self.kraken,
        )

        self.assertFalse(
            user_can_access_thread(
                self.outside_board_member,
                thread,
            )
        )

    def test_thread_without_targets_inherits_board_access(self):
        board = self.create_board(
            "Inherited Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            chapter=self.fyr_draca,
        )

        thread = self.create_thread(
            board,
            title="Inherited Thread",
        )

        self.assertTrue(
            user_can_access_thread(
                self.member,
                thread,
            )
        )

        self.assertTrue(
            user_can_access_thread(
                self.same_chapter_member,
                thread,
            )
        )

        self.assertFalse(
            user_can_access_thread(
                self.other_member,
                thread,
            )
        )

    def test_moderator_bypasses_active_board_and_thread_targets(self):
        board = self.create_board(
            "Moderator Target Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            user=self.member,
        )

        thread = self.create_thread(
            board,
            title="Moderator Target Thread",
        )

        ForumThreadTarget.objects.create(
            thread=thread,
            user=self.member,
        )

        self.assertTrue(
            user_can_access_thread(
                self.moderator,
                thread,
            )
        )

    def test_moderator_without_archive_permission_cannot_read_archived_board(self):
        board = self.create_board(
            "Archived Moderator Board",
            archived=True,
        )

        self.assertFalse(
            user_can_access_board(
                self.moderator,
                board,
                include_archived=True,
            )
        )

    def test_archive_viewer_can_read_untargeted_archived_board(self):
        board = self.create_board(
            "Archived Viewer Board",
            archived=True,
        )

        self.assertTrue(
            user_can_access_board(
                self.archive_viewer,
                board,
                include_archived=True,
            )
        )

    def test_archive_view_permission_does_not_bypass_targets(self):
        board = self.create_board(
            "Archived Target Board",
            archived=True,
        )

        ForumBoardTarget.objects.create(
            board=board,
            citizenship_class=self.active_citizen,
        )

        self.assertFalse(
            user_can_access_board(
                self.archive_viewer,
                board,
                include_archived=True,
            )
        )

    def test_archived_content_is_hidden_without_include_archived(self):
        board = self.create_board(
            "Hidden Archived Board",
            archived=True,
        )

        self.assertFalse(
            user_can_access_board(
                self.archive_viewer,
                board,
            )
        )

    def test_superuser_can_read_archived_board_when_requested(self):
        board = self.create_board(
            "Superuser Archived Board",
            archived=True,
        )

        self.assertTrue(
            user_can_access_board(
                self.actor,
                board,
                include_archived=True,
            )
        )

    def test_accessible_board_query_does_not_leak_hidden_boards(self):
        visible_category = self.create_category(
            "Visible Category"
        )

        hidden_category = self.create_category(
            "Hidden Category"
        )

        visible_board = self.create_board(
            "Visible Board",
            category=visible_category,
        )

        hidden_board = self.create_board(
            "Hidden Board",
            category=hidden_category,
        )

        ForumBoardTarget.objects.create(
            board=hidden_board,
            citizenship_class=self.honorary_citizen,
        )

        board_ids = set(
            get_accessible_boards(
                self.member
            ).values_list(
                "id",
                flat=True,
            )
        )

        self.assertIn(
            visible_board.pk,
            board_ids,
        )

        self.assertNotIn(
            hidden_board.pk,
            board_ids,
        )

    def test_category_is_hidden_when_it_has_no_accessible_boards(self):
        visible_category = self.create_category(
            "Visible Category"
        )

        hidden_category = self.create_category(
            "Hidden Category"
        )

        self.create_board(
            "Visible Category Board",
            category=visible_category,
        )

        hidden_board = self.create_board(
            "Hidden Category Board",
            category=hidden_category,
        )

        ForumBoardTarget.objects.create(
            board=hidden_board,
            citizenship_class=self.honorary_citizen,
        )

        category_ids = set(
            get_accessible_categories(
                self.member
            ).values_list(
                "id",
                flat=True,
            )
        )

        self.assertIn(
            visible_category.pk,
            category_ids,
        )

        self.assertNotIn(
            hidden_category.pk,
            category_ids,
        )

    def test_accessible_thread_query_does_not_leak_hidden_threads(self):
        board = self.create_board(
            "Thread Query Board"
        )

        visible_thread = self.create_thread(
            board,
            title="Visible Thread",
        )

        hidden_thread = self.create_thread(
            board,
            title="Hidden Thread",
        )

        ForumThreadTarget.objects.create(
            thread=hidden_thread,
            household=self.hvit_hrafn,
        )

        thread_ids = set(
            get_accessible_threads(
                self.member,
                board=board,
            ).values_list(
                "id",
                flat=True,
            )
        )

        self.assertIn(
            visible_thread.pk,
            thread_ids,
        )

        self.assertNotIn(
            hidden_thread.pk,
            thread_ids,
        )


class ForumThreadCreationPermissionTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_member_can_create_thread_in_open_accessible_board(self):
        board = self.create_board(
            "Open Creation Board"
        )

        self.assertTrue(
            user_can_create_thread(
                self.member,
                board,
            )
        )

    def test_pending_user_cannot_create_thread_in_open_board(self):
        board = self.create_board(
            "Pending Creation Board"
        )

        self.assertFalse(
            user_can_create_thread(
                self.pending_user,
                board,
            )
        )

    def test_member_cannot_create_thread_in_inaccessible_board(self):
        board = self.create_board(
            "Restricted Creation Board"
        )

        ForumBoardTarget.objects.create(
            board=board,
            citizenship_class=self.honorary_citizen,
        )

        self.assertFalse(
            user_can_create_thread(
                self.member,
                board,
            )
        )

    def test_matching_member_can_create_thread_in_targeted_board(self):
        board = self.create_board(
            "Targeted Creation Board",
            policy=ForumBoard.ThreadCreationPolicy.TARGETED,
        )

        ForumBoardThreadCreationTarget.objects.create(
            board=board,
            community_group=self.test_group,
        )

        self.assertTrue(
            user_can_create_thread(
                self.member,
                board,
            )
        )

    def test_nonmatching_member_cannot_create_thread_in_targeted_board(self):
        board = self.create_board(
            "Targeted Rejected Board",
            policy=ForumBoard.ThreadCreationPolicy.TARGETED,
        )

        ForumBoardThreadCreationTarget.objects.create(
            board=board,
            community_group=self.test_group,
        )

        self.assertFalse(
            user_can_create_thread(
                self.same_chapter_member,
                board,
            )
        )

    def test_targeted_board_without_creation_targets_denies_member(self):
        board = self.create_board(
            "Empty Targeted Creation Board",
            policy=ForumBoard.ThreadCreationPolicy.TARGETED,
        )

        self.assertFalse(
            user_can_create_thread(
                self.member,
                board,
            )
        )

    def test_staff_flag_alone_does_not_satisfy_staff_only_policy(self):
        board = self.create_board(
            "Staff Flag Board",
            policy=ForumBoard.ThreadCreationPolicy.STAFF_ONLY,
        )

        self.assertFalse(
            user_can_create_thread(
                self.staff_user,
                board,
            )
        )

    def test_board_manager_can_create_thread_in_staff_only_board(self):
        board = self.create_board(
            "Board Manager Staff Board",
            policy=ForumBoard.ThreadCreationPolicy.STAFF_ONLY,
        )

        self.assertTrue(
            user_can_create_thread(
                self.board_manager,
                board,
            )
        )

    def test_moderator_can_create_thread_in_staff_only_board(self):
        board = self.create_board(
            "Moderator Staff Board",
            policy=ForumBoard.ThreadCreationPolicy.STAFF_ONLY,
        )

        self.assertTrue(
            user_can_create_thread(
                self.moderator,
                board,
            )
        )

    def test_locked_board_blocks_ordinary_member(self):
        board = self.create_board(
            "Locked Member Board",
            locked=True,
        )

        self.assertFalse(
            user_can_create_thread(
                self.member,
                board,
            )
        )

    def test_locked_board_blocks_board_manager_thread_creation(self):
        board = self.create_board(
            "Locked Board Manager Board",
            locked=True,
        )

        self.assertFalse(
            user_can_create_thread(
                self.board_manager,
                board,
            )
        )

    def test_moderator_can_bypass_board_lock_for_thread_creation(self):
        board = self.create_board(
            "Locked Moderator Board",
            locked=True,
        )

        self.assertTrue(
            user_can_create_thread(
                self.moderator,
                board,
            )
        )

    def test_archived_board_blocks_thread_creation_for_moderator(self):
        board = self.create_board(
            "Archived Creation Board",
            archived=True,
        )

        self.assertFalse(
            user_can_create_thread(
                self.moderator,
                board,
            )
        )

    def test_archived_category_blocks_thread_creation(self):
        category = self.create_category(
            "Archived Creation Category",
            archived=True,
        )

        board = self.create_board(
            "Board In Archived Category",
            category=category,
        )

        self.assertFalse(
            user_can_create_thread(
                self.member,
                board,
            )
        )

        self.assertFalse(
            user_can_create_thread(
                self.moderator,
                board,
            )
        )


class ForumThreadControlPermissionTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_creator_controls_zero_post_thread(self):
        board = self.create_board(
            "Zero Post Board"
        )

        thread = self.create_thread(
            board,
            title="Zero Post Thread",
            creator=self.member,
        )

        self.assertTrue(
            thread_creator_controls(
                self.member,
                thread,
            )
        )

    def test_creator_controls_thread_with_only_own_posts(self):
        board = self.create_board(
            "Own Posts Board"
        )

        thread = self.create_thread(
            board,
            title="Own Posts Thread",
            creator=self.member,
        )

        self.create_post(
            thread,
            author=self.member,
        )

        self.create_post(
            thread,
            author=self.member,
            body="Second own post.",
        )

        self.assertTrue(
            thread_creator_controls(
                self.member,
                thread,
            )
        )

    def test_other_user_post_removes_creator_control(self):
        board = self.create_board(
            "Communal Board"
        )

        thread = self.create_thread(
            board,
            title="Communal Thread",
            creator=self.member,
        )

        self.create_post(
            thread,
            author=self.member,
        )

        self.create_post(
            thread,
            author=self.other_member,
            body="Other contributor.",
        )

        self.assertFalse(
            thread_creator_controls(
                self.member,
                thread,
            )
        )

    def test_archived_other_user_post_still_removes_creator_control(self):
        board = self.create_board(
            "Archived Contributor Board"
        )

        thread = self.create_thread(
            board,
            title="Archived Contributor Thread",
            creator=self.member,
        )

        self.create_post(
            thread,
            author=self.other_member,
            archived=True,
        )

        self.assertFalse(
            thread_creator_controls(
                self.member,
                thread,
            )
        )

    def test_creator_regains_control_after_other_posts_are_moved(self):
        source_board = self.create_board(
            "Source Creator Board"
        )

        destination_board = self.create_board(
            "Destination Creator Board"
        )

        source_thread = self.create_thread(
            source_board,
            title="Source Creator Thread",
            creator=self.member,
        )

        destination_thread = self.create_thread(
            destination_board,
            title="Destination Creator Thread",
            creator=self.other_member,
        )

        other_post = self.create_post(
            source_thread,
            author=self.other_member,
        )

        self.assertFalse(
            thread_creator_controls(
                self.member,
                source_thread,
            )
        )

        other_post.thread = destination_thread
        other_post.save(
            update_fields=[
                "thread",
            ]
        )

        self.assertTrue(
            thread_creator_controls(
                self.member,
                source_thread,
            )
        )

    def test_creator_can_change_thread_while_in_control(self):
        board = self.create_board(
            "Creator Change Board"
        )

        thread = self.create_thread(
            board,
            title="Creator Change Thread",
            creator=self.member,
        )

        self.create_post(
            thread,
            author=self.member,
        )

        self.assertTrue(
            user_can_change_thread(
                self.member,
                thread,
            )
        )

    def test_board_lock_blocks_creator_thread_changes(self):
        board = self.create_board(
            "Creator Locked Board",
            locked=True,
        )

        thread = self.create_thread(
            board,
            title="Creator Locked Thread",
            creator=self.member,
        )

        self.assertFalse(
            user_can_change_thread(
                self.member,
                thread,
            )
        )

    def test_thread_lock_does_not_remove_creator_metadata_control(self):
        board = self.create_board(
            "Thread Lock Metadata Board"
        )

        thread = self.create_thread(
            board,
            title="Thread Lock Metadata Thread",
            creator=self.member,
            locked=True,
        )

        self.assertTrue(
            user_can_change_thread(
                self.member,
                thread,
            )
        )

    def test_noncreator_member_cannot_change_thread(self):
        board = self.create_board(
            "Noncreator Change Board"
        )

        thread = self.create_thread(
            board,
            title="Noncreator Change Thread",
            creator=self.member,
        )

        self.assertFalse(
            user_can_change_thread(
                self.other_member,
                thread,
            )
        )

    def test_moderator_can_change_communal_thread(self):
        board = self.create_board(
            "Moderator Change Board"
        )

        thread = self.create_thread(
            board,
            title="Moderator Change Thread",
            creator=self.member,
        )

        self.create_post(
            thread,
            author=self.other_member,
        )

        self.assertTrue(
            user_can_change_thread(
                self.moderator,
                thread,
            )
        )

    def test_creator_can_archive_controlled_thread(self):
        board = self.create_board(
            "Creator Archive Board"
        )

        thread = self.create_thread(
            board,
            title="Creator Archive Thread",
            creator=self.member,
        )

        self.assertTrue(
            user_can_archive_thread(
                self.member,
                thread,
            )
        )

    def test_creator_can_restore_controlled_thread(self):
        board = self.create_board(
            "Creator Restore Board"
        )

        thread = self.create_thread(
            board,
            title="Creator Restore Thread",
            creator=self.member,
            archived=True,
        )

        self.assertTrue(
            user_can_restore_thread(
                self.member,
                thread,
            )
        )


class ForumPostPermissionTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_member_can_add_post_to_accessible_unlocked_thread(self):
        board = self.create_board(
            "Posting Board"
        )

        thread = self.create_thread(
            board,
            title="Posting Thread",
        )

        self.assertTrue(
            user_can_add_post(
                self.member,
                thread,
            )
        )

    def test_pending_user_cannot_add_post(self):
        board = self.create_board(
            "Pending Posting Board"
        )

        thread = self.create_thread(
            board,
            title="Pending Posting Thread",
        )

        self.assertFalse(
            user_can_add_post(
                self.pending_user,
                thread,
            )
        )

    def test_thread_lock_blocks_ordinary_post_creation(self):
        board = self.create_board(
            "Thread Lock Posting Board"
        )

        thread = self.create_thread(
            board,
            title="Locked Posting Thread",
            locked=True,
        )

        self.assertFalse(
            user_can_add_post(
                self.member,
                thread,
            )
        )

    def test_board_lock_blocks_ordinary_post_creation(self):
        board = self.create_board(
            "Board Lock Posting Board",
            locked=True,
        )

        thread = self.create_thread(
            board,
            title="Board Lock Posting Thread",
        )

        self.assertFalse(
            user_can_add_post(
                self.member,
                thread,
            )
        )

    def test_moderator_can_post_through_thread_and_board_locks(self):
        board = self.create_board(
            "Moderator Locked Posting Board",
            locked=True,
        )

        thread = self.create_thread(
            board,
            title="Moderator Locked Posting Thread",
            locked=True,
        )

        self.assertTrue(
            user_can_add_post(
                self.moderator,
                thread,
            )
        )

    def test_author_can_edit_own_post(self):
        board = self.create_board(
            "Own Edit Board"
        )

        thread = self.create_thread(
            board,
            title="Own Edit Thread",
        )

        post = self.create_post(
            thread,
            author=self.member,
        )

        self.assertTrue(
            user_can_edit_post(
                self.member,
                post,
            )
        )

    def test_member_cannot_edit_another_users_post(self):
        board = self.create_board(
            "Other Edit Board"
        )

        thread = self.create_thread(
            board,
            title="Other Edit Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
        )

        self.assertFalse(
            user_can_edit_post(
                self.member,
                post,
            )
        )

    def test_thread_lock_blocks_ordinary_post_edit(self):
        board = self.create_board(
            "Locked Edit Board"
        )

        thread = self.create_thread(
            board,
            title="Locked Edit Thread",
            locked=True,
        )

        post = self.create_post(
            thread,
            author=self.member,
        )

        self.assertFalse(
            user_can_edit_post(
                self.member,
                post,
            )
        )

    def test_board_lock_blocks_ordinary_post_edit(self):
        board = self.create_board(
            "Board Locked Edit Board",
            locked=True,
        )

        thread = self.create_thread(
            board,
            title="Board Locked Edit Thread",
        )

        post = self.create_post(
            thread,
            author=self.member,
        )

        self.assertFalse(
            user_can_edit_post(
                self.member,
                post,
            )
        )

    def test_moderator_can_edit_another_users_active_post(self):
        board = self.create_board(
            "Moderator Edit Board"
        )

        thread = self.create_thread(
            board,
            title="Moderator Edit Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
        )

        self.assertTrue(
            user_can_edit_post(
                self.moderator,
                post,
            )
        )

    def test_archived_post_cannot_be_edited(self):
        board = self.create_board(
            "Archived Edit Board"
        )

        thread = self.create_thread(
            board,
            title="Archived Edit Thread",
        )

        post = self.create_post(
            thread,
            author=self.member,
            archived=True,
        )

        self.assertFalse(
            user_can_edit_post(
                self.member,
                post,
            )
        )

        self.assertFalse(
            user_can_edit_post(
                self.moderator,
                post,
            )
        )

    def test_author_can_archive_own_active_post(self):
        board = self.create_board(
            "Post Archive Board"
        )

        thread = self.create_thread(
            board,
            title="Post Archive Thread",
        )

        post = self.create_post(
            thread,
            author=self.member,
        )

        self.assertTrue(
            user_can_archive_post(
                self.member,
                post,
            )
        )

    def test_author_can_restore_own_post_in_active_unlocked_thread(self):
        board = self.create_board(
            "Post Restore Board"
        )

        thread = self.create_thread(
            board,
            title="Post Restore Thread",
        )

        post = self.create_post(
            thread,
            author=self.member,
            archived=True,
        )

        self.assertTrue(
            user_can_restore_post(
                self.member,
                post,
            )
        )

    def test_locked_thread_blocks_ordinary_post_restore(self):
        board = self.create_board(
            "Locked Restore Board"
        )

        thread = self.create_thread(
            board,
            title="Locked Restore Thread",
            locked=True,
        )

        post = self.create_post(
            thread,
            author=self.member,
            archived=True,
        )

        self.assertFalse(
            user_can_restore_post(
                self.member,
                post,
            )
        )

    def test_member_can_report_another_users_visible_post(self):
        board = self.create_board(
            "Report Board"
        )

        thread = self.create_thread(
            board,
            title="Report Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
        )

        self.assertTrue(
            user_can_report_post(
                self.member,
                post,
            )
        )

    def test_member_cannot_report_own_post(self):
        board = self.create_board(
            "Self Report Board"
        )

        thread = self.create_thread(
            board,
            title="Self Report Thread",
        )

        post = self.create_post(
            thread,
            author=self.member,
        )

        self.assertFalse(
            user_can_report_post(
                self.member,
                post,
            )
        )

    def test_member_cannot_report_archived_post(self):
        board = self.create_board(
            "Archived Report Board"
        )

        thread = self.create_thread(
            board,
            title="Archived Report Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
            archived=True,
        )

        self.assertFalse(
            user_can_report_post(
                self.member,
                post,
            )
        )

    def test_pending_user_cannot_report_post(self):
        board = self.create_board(
            "Pending Report Board"
        )

        thread = self.create_thread(
            board,
            title="Pending Report Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
        )

        self.assertFalse(
            user_can_report_post(
                self.pending_user,
                post,
            )
        )


class ForumCreationAndEditServiceTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_create_forum_thread_creates_complete_thread_state(self):
        board = self.create_board(
            "Thread Creation Service Board"
        )

        quote_thread = self.create_thread(
            board,
            title="Quote Source Thread",
            creator=self.member,
        )

        quoted_post = self.create_post(
            quote_thread,
            author=self.member,
            body="Source material.",
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="  Created Thread  ",
            body="  Opening post body.  ",
            target_rows=[
                {
                    "chapter": self.fyr_draca,
                },
            ],
            attachments=[
                {
                    "label": "Reference",
                    "url": "https://example.com/reference",
                },
            ],
            quoted_post_ids=[
                quoted_post.pk,
            ],
        )

        thread.refresh_from_db()

        self.assertEqual(
            thread.title,
            "Created Thread",
        )

        self.assertEqual(
            thread.board,
            board,
        )

        self.assertEqual(
            thread.created_by,
            self.member,
        )

        opening_post = thread.posts.get()

        self.assertEqual(
            opening_post.author,
            self.member,
        )

        self.assertEqual(
            opening_post.body,
            "Opening post body.",
        )

        self.assertEqual(
            thread.last_post_at,
            opening_post.created_at,
        )

        self.assertTrue(
            thread.targets.filter(
                chapter=self.fyr_draca,
            ).exists()
        )

        attachment = opening_post.attachments.get()

        self.assertEqual(
            attachment.label,
            "Reference",
        )

        self.assertEqual(
            attachment.url,
            "https://example.com/reference",
        )

        quote = opening_post.quotes.get()

        self.assertEqual(
            quote.quoted_post,
            quoted_post,
        )

        self.assertTrue(
            ForumThreadSubscription.objects.filter(
                user=self.member,
                thread=thread,
            ).exists()
        )

        read_state = ForumThreadReadState.objects.get(
            user=self.member,
            thread=thread,
        )

        self.assertEqual(
            read_state.last_read_at,
            opening_post.created_at,
        )

    def test_create_forum_post_updates_activity_and_read_state(self):
        board = self.create_board(
            "Post Creation Service Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="Post Creation Thread",
            body="Opening post.",
        )

        ForumThreadSubscription.objects.filter(
            user=self.member,
            thread=thread,
        ).delete()

        self.assertFalse(
            ForumThreadSubscription.objects.filter(
                user=self.other_member,
                thread=thread,
            ).exists()
        )

        post = create_forum_post(
            user=self.other_member,
            thread=thread,
            body="  New reply.  ",
        )

        thread.refresh_from_db()

        self.assertEqual(
            post.body,
            "New reply.",
        )

        self.assertEqual(
            post.author,
            self.other_member,
        )

        self.assertEqual(
            thread.last_post_at,
            post.created_at,
        )

        read_state = ForumThreadReadState.objects.get(
            user=self.other_member,
            thread=thread,
        )

        self.assertEqual(
            read_state.last_read_at,
            post.created_at,
        )

        self.assertFalse(
            ForumThreadSubscription.objects.filter(
                user=self.other_member,
                thread=thread,
            ).exists()
        )

    def test_edit_forum_thread_replaces_targets_without_bumping_activity(self):
        board = self.create_board(
            "Thread Edit Service Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="Original Thread Title",
            body="Opening post.",
            target_rows=[
                {
                    "chapter": self.fyr_draca,
                },
            ],
        )

        original_last_post_at = (
            thread.last_post_at
        )

        edit_forum_thread(
            user=self.member,
            thread=thread,
            title="  Updated Thread Title  ",
            target_rows=[
                {
                    "household": self.kraken,
                },
            ],
        )

        thread.refresh_from_db()

        self.assertEqual(
            thread.title,
            "Updated Thread Title",
        )

        self.assertEqual(
            thread.last_post_at,
            original_last_post_at,
        )

        self.assertEqual(
            thread.targets.count(),
            1,
        )

        self.assertTrue(
            thread.targets.filter(
                household=self.kraken,
            ).exists()
        )

        self.assertFalse(
            thread.targets.filter(
                chapter=self.fyr_draca,
            ).exists()
        )

    def test_edit_forum_post_preserves_created_at_and_thread_activity(self):
        board = self.create_board(
            "Post Edit Service Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="Post Edit Thread",
            body="Original body.",
        )

        post = thread.posts.get()

        original_created_at = post.created_at
        original_last_post_at = thread.last_post_at

        edit_forum_post(
            user=self.member,
            post=post,
            body="  Updated body.  ",
        )

        post.refresh_from_db()
        thread.refresh_from_db()

        self.assertEqual(
            post.body,
            "Updated body.",
        )

        self.assertEqual(
            post.created_at,
            original_created_at,
        )

        self.assertIsNotNone(
            post.edited_at
        )

        self.assertEqual(
            post.edited_by,
            self.member,
        )

        self.assertEqual(
            thread.last_post_at,
            original_last_post_at,
        )


class ForumArchiveAndStateServiceTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_category_archive_does_not_recursively_archive_children(self):
        category = self.create_category(
            "Archive Category"
        )

        board = self.create_board(
            "Archive Category Board",
            category=category,
        )

        thread = self.create_thread(
            board,
            title="Archive Category Thread",
        )

        post = self.create_post(
            thread,
        )

        archive_forum_category(
            user=self.category_manager,
            category=category,
        )

        category.refresh_from_db()
        board.refresh_from_db()
        thread.refresh_from_db()
        post.refresh_from_db()

        self.assertIsNotNone(
            category.archived_at
        )

        self.assertEqual(
            category.archived_by,
            self.category_manager,
        )

        self.assertIsNone(
            board.archived_at
        )

        self.assertIsNone(
            thread.archived_at
        )

        self.assertIsNone(
            post.archived_at
        )

        restore_forum_category(
            user=self.category_manager,
            category=category,
        )

        category.refresh_from_db()

        self.assertIsNone(
            category.archived_at
        )

        self.assertIsNone(
            category.archived_by
        )

    def test_board_archive_does_not_recursively_archive_children(self):
        board = self.create_board(
            "Archive Board"
        )

        thread = self.create_thread(
            board,
            title="Archive Board Thread",
        )

        post = self.create_post(
            thread,
        )

        archive_forum_board(
            user=self.board_manager,
            board=board,
        )

        board.refresh_from_db()
        thread.refresh_from_db()
        post.refresh_from_db()

        self.assertIsNotNone(
            board.archived_at
        )

        self.assertEqual(
            board.archived_by,
            self.board_manager,
        )

        self.assertIsNone(
            thread.archived_at
        )

        self.assertIsNone(
            post.archived_at
        )

        restore_forum_board(
            user=self.board_manager,
            board=board,
        )

        board.refresh_from_db()

        self.assertIsNone(
            board.archived_at
        )

        self.assertIsNone(
            board.archived_by
        )

    def test_thread_archive_does_not_archive_posts(self):
        board = self.create_board(
            "Thread Archive Service Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="Thread Archive Service Thread",
            body="Opening post.",
        )

        post = thread.posts.get()

        archive_forum_thread(
            user=self.member,
            thread=thread,
        )

        thread.refresh_from_db()
        post.refresh_from_db()

        self.assertIsNotNone(
            thread.archived_at
        )

        self.assertEqual(
            thread.archived_by,
            self.member,
        )

        self.assertIsNone(
            post.archived_at
        )

        restore_forum_thread(
            user=self.member,
            thread=thread,
        )

        thread.refresh_from_db()

        self.assertIsNone(
            thread.archived_at
        )

        self.assertIsNone(
            thread.archived_by
        )

    def test_post_archive_and_restore_recalculate_last_post_at(self):
        board = self.create_board(
            "Post Archive Service Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="Post Archive Service Thread",
            body="Opening post.",
        )

        opening_post = thread.posts.get()

        reply = create_forum_post(
            user=self.member,
            thread=thread,
            body="Newest reply.",
        )

        thread.refresh_from_db()

        self.assertEqual(
            thread.last_post_at,
            reply.created_at,
        )

        archive_forum_post(
            user=self.member,
            post=reply,
        )

        reply.refresh_from_db()
        thread.refresh_from_db()

        self.assertIsNotNone(
            reply.archived_at
        )

        self.assertEqual(
            reply.archived_by,
            self.member,
        )

        self.assertEqual(
            thread.last_post_at,
            opening_post.created_at,
        )

        restore_forum_post(
            user=self.member,
            post=reply,
        )

        reply.refresh_from_db()
        thread.refresh_from_db()

        self.assertIsNone(
            reply.archived_at
        )

        self.assertIsNone(
            reply.archived_by
        )

        self.assertEqual(
            thread.last_post_at,
            reply.created_at,
        )

    def test_board_lock_records_and_clears_lock_metadata(self):
        board = self.create_board(
            "Board Lock Service Board"
        )

        set_board_locked(
            user=self.board_manager,
            board=board,
            locked=True,
        )

        board.refresh_from_db()

        self.assertTrue(
            board.is_locked
        )

        self.assertIsNotNone(
            board.locked_at
        )

        self.assertEqual(
            board.locked_by,
            self.board_manager,
        )

        set_board_locked(
            user=self.board_manager,
            board=board,
            locked=False,
        )

        board.refresh_from_db()

        self.assertFalse(
            board.is_locked
        )

        self.assertIsNone(
            board.locked_at
        )

        self.assertIsNone(
            board.locked_by
        )

    def test_thread_pin_records_and_clears_pin_metadata(self):
        board = self.create_board(
            "Thread Pin Service Board"
        )

        thread = self.create_thread(
            board,
            title="Thread Pin Service Thread",
        )

        set_thread_pinned(
            user=self.moderator,
            thread=thread,
            pinned=True,
        )

        thread.refresh_from_db()

        self.assertTrue(
            thread.is_pinned
        )

        self.assertIsNotNone(
            thread.pinned_at
        )

        self.assertEqual(
            thread.pinned_by,
            self.moderator,
        )

        set_thread_pinned(
            user=self.moderator,
            thread=thread,
            pinned=False,
        )

        thread.refresh_from_db()

        self.assertFalse(
            thread.is_pinned
        )

        self.assertIsNone(
            thread.pinned_at
        )

        self.assertIsNone(
            thread.pinned_by
        )

    def test_thread_lock_records_and_clears_lock_metadata(self):
        board = self.create_board(
            "Thread Lock Service Board"
        )

        thread = self.create_thread(
            board,
            title="Thread Lock Service Thread",
        )

        set_thread_locked(
            user=self.moderator,
            thread=thread,
            locked=True,
        )

        thread.refresh_from_db()

        self.assertTrue(
            thread.is_locked
        )

        self.assertIsNotNone(
            thread.locked_at
        )

        self.assertEqual(
            thread.locked_by,
            self.moderator,
        )

        set_thread_locked(
            user=self.moderator,
            thread=thread,
            locked=False,
        )

        thread.refresh_from_db()

        self.assertFalse(
            thread.is_locked
        )

        self.assertIsNone(
            thread.locked_at
        )

        self.assertIsNone(
            thread.locked_by
        )


class ForumMovementServiceTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_move_thread_changes_only_board_relationship(self):
        source_board = self.create_board(
            "Move Thread Source Board"
        )

        destination_board = self.create_board(
            "Move Thread Destination Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=source_board,
            title="Movable Thread",
            body="Opening post.",
            target_rows=[
                {
                    "chapter": self.fyr_draca,
                },
            ],
        )

        opening_post = thread.posts.get()

        original_created_at = (
            thread.created_at
        )

        original_last_post_at = (
            thread.last_post_at
        )

        move_forum_thread(
            user=self.moderator,
            thread=thread,
            destination_board=destination_board,
        )

        thread.refresh_from_db()
        opening_post.refresh_from_db()

        self.assertEqual(
            thread.board,
            destination_board,
        )

        self.assertEqual(
            thread.created_at,
            original_created_at,
        )

        self.assertEqual(
            thread.last_post_at,
            original_last_post_at,
        )

        self.assertEqual(
            opening_post.thread,
            thread,
        )

        self.assertTrue(
            thread.targets.filter(
                chapter=self.fyr_draca,
            ).exists()
        )

    def test_move_posts_preserves_post_metadata_and_owned_records(self):
        source_board = self.create_board(
            "Move Posts Source Board"
        )

        destination_board = self.create_board(
            "Move Posts Destination Board"
        )

        destination_thread = self.create_thread(
            destination_board,
            title="Move Posts Destination Thread",
            creator=self.other_member,
        )

        destination_post = self.create_post(
            destination_thread,
            author=self.other_member,
            body="Destination opening post.",
        )

        recalculate_thread_last_post_at(
            destination_thread
        )

        source_thread = self.create_thread(
            source_board,
            title="Move Posts Source Thread",
            creator=self.member,
        )

        source_post = self.create_post(
            source_thread,
            author=self.member,
            body="Movable post.",
        )

        source_post.edited_at = timezone.now()
        source_post.edited_by = self.actor
        source_post.save(
            update_fields=[
                "edited_at",
                "edited_by",
            ]
        )

        attachment = ForumPostAttachment.objects.create(
            post=source_post,
            label="Moved link",
            url="https://example.com/moved",
        )

        quote = ForumPostQuote.objects.create(
            post=source_post,
            quoted_post=destination_post,
        )

        recalculate_thread_last_post_at(
            source_thread
        )

        source_post.refresh_from_db()

        original_author_id = (
            source_post.author_id
        )

        original_created_at = (
            source_post.created_at
        )

        original_edited_at = (
            source_post.edited_at
        )

        original_edited_by_id = (
            source_post.edited_by_id
        )

        move_forum_posts(
            user=self.moderator,
            posts=[
                source_post,
            ],
            destination_thread=destination_thread,
        )

        source_post.refresh_from_db()
        source_thread.refresh_from_db()
        destination_thread.refresh_from_db()
        attachment.refresh_from_db()
        quote.refresh_from_db()

        self.assertEqual(
            source_post.thread,
            destination_thread,
        )

        self.assertEqual(
            source_post.author_id,
            original_author_id,
        )

        self.assertEqual(
            source_post.created_at,
            original_created_at,
        )

        self.assertEqual(
            source_post.edited_at,
            original_edited_at,
        )

        self.assertEqual(
            source_post.edited_by_id,
            original_edited_by_id,
        )

        self.assertEqual(
            attachment.post,
            source_post,
        )

        self.assertEqual(
            quote.post,
            source_post,
        )

        self.assertEqual(
            quote.quoted_post,
            destination_post,
        )

        self.assertEqual(
            source_thread.posts.count(),
            0,
        )

        self.assertIsNone(
            source_thread.last_post_at
        )

        self.assertIsNone(
            source_thread.archived_at
        )

        self.assertIsNone(
            source_thread.merged_into
        )

        self.assertEqual(
            destination_thread.last_post_at,
            source_post.created_at,
        )

    def test_split_thread_moves_selected_posts_and_copies_targets(self):
        source_board = self.create_board(
            "Split Source Board"
        )

        destination_board = self.create_board(
            "Split Destination Board"
        )

        source_thread = create_forum_thread(
            user=self.member,
            board=source_board,
            title="Split Source Thread",
            body="Opening post.",
            target_rows=[
                {
                    "chapter": self.fyr_draca,
                },
            ],
        )

        opening_post = source_thread.posts.get()

        moved_post = create_forum_post(
            user=self.member,
            thread=source_thread,
            body="Post to split.",
        )

        new_thread = split_forum_thread(
            user=self.moderator,
            source_thread=source_thread,
            posts=[
                moved_post,
            ],
            destination_board=destination_board,
            title="  Split Result  ",
        )

        source_thread.refresh_from_db()
        new_thread.refresh_from_db()
        opening_post.refresh_from_db()
        moved_post.refresh_from_db()

        self.assertEqual(
            new_thread.title,
            "Split Result",
        )

        self.assertEqual(
            new_thread.board,
            destination_board,
        )

        self.assertEqual(
            new_thread.created_by,
            source_thread.created_by,
        )

        self.assertEqual(
            moved_post.thread,
            new_thread,
        )

        self.assertEqual(
            opening_post.thread,
            source_thread,
        )

        self.assertEqual(
            source_thread.last_post_at,
            opening_post.created_at,
        )

        self.assertEqual(
            new_thread.last_post_at,
            moved_post.created_at,
        )

        self.assertTrue(
            new_thread.targets.filter(
                chapter=self.fyr_draca,
            ).exists()
        )

        self.assertIsNone(
            source_thread.archived_at
        )

        self.assertIsNone(
            source_thread.merged_into
        )

    def test_split_all_posts_leaves_source_thread_active_and_empty(self):
        source_board = self.create_board(
            "Split All Source Board"
        )

        destination_board = self.create_board(
            "Split All Destination Board"
        )

        source_thread = create_forum_thread(
            user=self.member,
            board=source_board,
            title="Split All Source Thread",
            body="Only post.",
        )

        only_post = source_thread.posts.get()

        new_thread = split_forum_thread(
            user=self.moderator,
            source_thread=source_thread,
            posts=[
                only_post,
            ],
            destination_board=destination_board,
            title="Split All Result",
        )

        source_thread.refresh_from_db()
        new_thread.refresh_from_db()
        only_post.refresh_from_db()

        self.assertEqual(
            source_thread.posts.count(),
            0,
        )

        self.assertIsNone(
            source_thread.last_post_at
        )

        self.assertIsNone(
            source_thread.archived_at
        )

        self.assertIsNone(
            source_thread.merged_into
        )

        self.assertEqual(
            only_post.thread,
            new_thread,
        )

        self.assertEqual(
            new_thread.last_post_at,
            only_post.created_at,
        )

    def test_merge_threads_moves_posts_and_marks_source_as_merged(self):
        destination_board = self.create_board(
            "Merge Destination Board"
        )

        source_board = self.create_board(
            "Merge Source Board"
        )

        destination_thread = create_forum_thread(
            user=self.other_member,
            board=destination_board,
            title="Merge Destination Thread",
            body="Destination opening post.",
            target_rows=[
                {
                    "household": self.hvit_hrafn,
                },
            ],
        )

        destination_post = (
            destination_thread.posts.get()
        )

        source_thread = create_forum_thread(
            user=self.member,
            board=source_board,
            title="Merge Source Thread",
            body="Source opening post.",
            target_rows=[
                {
                    "chapter": self.fyr_draca,
                },
            ],
        )

        source_post = (
            source_thread.posts.get()
        )

        original_source_created_at = (
            source_post.created_at
        )

        merge_forum_threads(
            user=self.moderator,
            source_thread=source_thread,
            destination_thread=destination_thread,
        )

        source_thread.refresh_from_db()
        destination_thread.refresh_from_db()
        source_post.refresh_from_db()
        destination_post.refresh_from_db()

        self.assertEqual(
            source_post.thread,
            destination_thread,
        )

        self.assertEqual(
            source_post.created_at,
            original_source_created_at,
        )

        self.assertEqual(
            destination_post.thread,
            destination_thread,
        )

        self.assertEqual(
            source_thread.posts.count(),
            0,
        )

        self.assertIsNotNone(
            source_thread.archived_at
        )

        self.assertEqual(
            source_thread.archived_by,
            self.moderator,
        )

        self.assertEqual(
            source_thread.merged_into,
            destination_thread,
        )

        self.assertIsNone(
            source_thread.last_post_at
        )

        self.assertEqual(
            destination_thread.last_post_at,
            source_post.created_at,
        )

        self.assertEqual(
            destination_thread.targets.count(),
            1,
        )

        self.assertTrue(
            destination_thread.targets.filter(
                household=self.hvit_hrafn,
            ).exists()
        )

        self.assertFalse(
            destination_thread.targets.filter(
                chapter=self.fyr_draca,
            ).exists()
        )

        self.assertTrue(
            source_thread.targets.filter(
                chapter=self.fyr_draca,
            ).exists()
        )


class ForumServiceAtomicityTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def test_failed_thread_creation_rolls_back_thread(self):
        board = self.create_board(
            "Atomic Thread Creation Board"
        )

        original_thread_count = (
            ForumThread.objects.count()
        )

        original_post_count = (
            ForumPost.objects.count()
        )

        with self.assertRaises(
            ValidationError
        ):
            create_forum_thread(
                user=self.member,
                board=board,
                title="Invalid Target Thread",
                body="Opening post.",
                target_rows=[
                    {},
                ],
            )

        self.assertEqual(
            ForumThread.objects.count(),
            original_thread_count,
        )

        self.assertEqual(
            ForumPost.objects.count(),
            original_post_count,
        )

    def test_failed_post_attachment_rolls_back_new_post(self):
        board = self.create_board(
            "Atomic Post Creation Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="Atomic Post Creation Thread",
            body="Opening post.",
        )

        original_post_count = (
            thread.posts.count()
        )

        original_last_post_at = (
            thread.last_post_at
        )

        with self.assertRaises(
            ValidationError
        ):
            create_forum_post(
                user=self.other_member,
                thread=thread,
                body="Post with invalid attachment.",
                attachments=[
                    "not-a-valid-url",
                ],
            )

        thread.refresh_from_db()

        self.assertEqual(
            thread.posts.count(),
            original_post_count,
        )

        self.assertEqual(
            thread.last_post_at,
            original_last_post_at,
        )

        self.assertFalse(
            ForumThreadReadState.objects.filter(
                user=self.other_member,
                thread=thread,
            ).exists()
        )

    def test_failed_thread_target_edit_rolls_back_title_and_targets(self):
        board = self.create_board(
            "Atomic Thread Edit Board"
        )

        thread = create_forum_thread(
            user=self.member,
            board=board,
            title="Original Atomic Title",
            body="Opening post.",
            target_rows=[
                {
                    "chapter": self.fyr_draca,
                },
            ],
        )

        with self.assertRaises(
            ValidationError
        ):
            edit_forum_thread(
                user=self.member,
                thread=thread,
                title="Changed Atomic Title",
                target_rows=[
                    {},
                ],
            )

        thread.refresh_from_db()

        self.assertEqual(
            thread.title,
            "Original Atomic Title",
        )

        self.assertEqual(
            thread.targets.count(),
            1,
        )

        self.assertTrue(
            thread.targets.filter(
                chapter=self.fyr_draca,
            ).exists()
        )


class ForumAuditIntegrationTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def setUp(self):
        self.factory = RequestFactory()

    def make_post_request(
        self,
        path,
        user,
        data=None,
    ):
        request = self.factory.post(
            path,
            data=data or {},
        )
        request.user = user

        return request

    def get_audit_event(
        self,
        obj,
        action,
    ):
        return AuditLog.objects.get(
            target_type=obj._meta.verbose_name,
            target_id=str(obj.pk),
            action=action,
        )

    def test_archive_audit_records_context_and_state_change(self):
        category = self.create_category(
            "Audit Metadata Category"
        )

        request_path = (
            "/audit/category/archive/"
        )

        category_archive(
            self.make_post_request(
                request_path,
                self.category_manager,
            ),
            category.pk,
        )

        category.refresh_from_db()

        audit_log = self.get_audit_event(
            category,
            AuditLog.Action.ARCHIVE,
        )

        self.assertEqual(
            audit_log.actor,
            self.category_manager,
        )

        self.assertEqual(
            audit_log.actor_label,
            self.category_manager.display_name,
        )

        self.assertEqual(
            audit_log.target_label,
            str(category),
        )

        self.assertEqual(
            audit_log.source,
            AuditLog.Source.WEB_APP,
        )

        self.assertEqual(
            audit_log.method,
            AuditLog.Method.MANUAL,
        )

        self.assertEqual(
            audit_log.request_path,
            request_path,
        )

        self.assertIsNone(
            audit_log.old_value[
                "archived_at"
            ]
        )

        self.assertIsNone(
            audit_log.old_value[
                "archived_by"
            ]
        )

        self.assertIsNotNone(
            audit_log.new_value[
                "archived_at"
            ]
        )

        self.assertEqual(
            audit_log.new_value[
                "archived_by"
            ],
            self.category_manager.pk,
        )

    def test_archive_and_restore_views_use_semantic_actions(self):
        category = self.create_category(
            "Audit Restore Category"
        )

        board = self.create_board(
            "Audit Archive Board"
        )

        thread = self.create_thread(
            board,
            title="Audit Archive Thread",
            creator=self.member,
        )

        post = self.create_post(
            thread,
            author=self.member,
            body="Audit archive post.",
        )

        category_archive(
            self.make_post_request(
                "/audit/category/archive/",
                self.category_manager,
            ),
            category.pk,
        )

        category_restore(
            self.make_post_request(
                "/audit/category/restore/",
                self.category_manager,
            ),
            category.pk,
        )

        board_archive(
            self.make_post_request(
                "/audit/board/archive/",
                self.board_manager,
            ),
            board.pk,
        )

        board_restore(
            self.make_post_request(
                "/audit/board/restore/",
                self.board_manager,
            ),
            board.pk,
        )

        thread_archive(
            self.make_post_request(
                "/audit/thread/archive/",
                self.member,
            ),
            thread.pk,
        )

        thread_restore(
            self.make_post_request(
                "/audit/thread/restore/",
                self.member,
            ),
            thread.pk,
        )

        post_archive(
            self.make_post_request(
                "/audit/post/archive/",
                self.member,
            ),
            post.pk,
        )

        post_restore(
            self.make_post_request(
                "/audit/post/restore/",
                self.member,
            ),
            post.pk,
        )

        for obj in (
            category,
            board,
            thread,
            post,
        ):
            with self.subTest(
                target=str(obj),
                action="archive",
            ):
                self.assertTrue(
                    AuditLog.objects.filter(
                        target_type=(
                            obj._meta.verbose_name
                        ),
                        target_id=str(obj.pk),
                        action=(
                            AuditLog.Action.ARCHIVE
                        ),
                    ).exists()
                )

            with self.subTest(
                target=str(obj),
                action="restore",
            ):
                self.assertTrue(
                    AuditLog.objects.filter(
                        target_type=(
                            obj._meta.verbose_name
                        ),
                        target_id=str(obj.pk),
                        action=(
                            AuditLog.Action.RESTORE
                        ),
                    ).exists()
                )

    def test_lock_unlock_pin_and_unpin_use_semantic_actions(self):
        board = self.create_board(
            "Audit State Board"
        )

        thread = self.create_thread(
            board,
            title="Audit State Thread",
        )

        board_lock(
            self.make_post_request(
                "/audit/board/lock/",
                self.board_manager,
            ),
            board.pk,
        )

        board_unlock(
            self.make_post_request(
                "/audit/board/unlock/",
                self.board_manager,
            ),
            board.pk,
        )

        thread_lock(
            self.make_post_request(
                "/audit/thread/lock/",
                self.moderator,
            ),
            thread.pk,
        )

        thread_unlock(
            self.make_post_request(
                "/audit/thread/unlock/",
                self.moderator,
            ),
            thread.pk,
        )

        thread_pin(
            self.make_post_request(
                "/audit/thread/pin/",
                self.moderator,
            ),
            thread.pk,
        )

        thread_unpin(
            self.make_post_request(
                "/audit/thread/unpin/",
                self.moderator,
            ),
            thread.pk,
        )

        expected_events = (
            (
                board,
                AuditLog.Action.LOCK,
            ),
            (
                board,
                AuditLog.Action.UNLOCK,
            ),
            (
                thread,
                AuditLog.Action.LOCK,
            ),
            (
                thread,
                AuditLog.Action.UNLOCK,
            ),
            (
                thread,
                AuditLog.Action.PIN,
            ),
            (
                thread,
                AuditLog.Action.UNPIN,
            ),
        )

        for obj, action in expected_events:
            with self.subTest(
                target=str(obj),
                action=action,
            ):
                self.assertTrue(
                    AuditLog.objects.filter(
                        target_type=(
                            obj._meta.verbose_name
                        ),
                        target_id=str(obj.pk),
                        action=action,
                    ).exists()
                )

    def test_move_views_use_move_action(self):
        source_board = self.create_board(
            "Audit Move Source Board"
        )

        destination_board = self.create_board(
            "Audit Move Destination Board"
        )

        thread = self.create_thread(
            source_board,
            title="Audit Move Thread",
        )

        with (
            patch(
                "community.views.ForumThreadMoveForm"
            ) as form_class,
            patch(
                "community.views.move_forum_thread",
                return_value=thread,
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "destination_board":
                    destination_board,
            }

            thread_move(
                self.make_post_request(
                    "/audit/thread/move/",
                    self.moderator,
                ),
                thread.pk,
            )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type=(
                    thread._meta.verbose_name
                ),
                target_id=str(thread.pk),
                action=AuditLog.Action.MOVE,
            ).exists()
        )

        source_thread = self.create_thread(
            source_board,
            title="Audit Post Move Source",
        )

        destination_thread = self.create_thread(
            destination_board,
            title="Audit Post Move Destination",
        )

        post = self.create_post(
            source_thread,
            author=self.member,
            body="Audit post move.",
        )

        with (
            patch(
                "community.views.ForumPostMoveForm"
            ) as form_class,
            patch(
                "community.views.move_forum_posts"
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "posts": [
                    post,
                ],
                "destination_thread":
                    destination_thread,
            }

            thread_move_posts(
                self.make_post_request(
                    "/audit/post/move/",
                    self.moderator,
                ),
                source_thread.pk,
            )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type=(
                    post._meta.verbose_name
                ),
                target_id=str(post.pk),
                action=AuditLog.Action.MOVE,
            ).exists()
        )

    def test_split_view_uses_split_create_and_move_actions(self):
        source_board = self.create_board(
            "Audit Split Source Board"
        )

        destination_board = self.create_board(
            "Audit Split Destination Board"
        )

        source_thread = self.create_thread(
            source_board,
            title="Audit Split Source Thread",
        )

        post = self.create_post(
            source_thread,
            author=self.member,
            body="Audit split post.",
        )

        new_thread = self.create_thread(
            destination_board,
            title="Audit Split Result",
            creator=self.member,
        )

        with (
            patch(
                "community.views.ForumThreadSplitForm"
            ) as form_class,
            patch(
                "community.views.split_forum_thread",
                return_value=new_thread,
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "posts": [
                    post,
                ],
                "destination_board":
                    destination_board,
                "title":
                    new_thread.title,
            }

            thread_split(
                self.make_post_request(
                    "/audit/thread/split/",
                    self.moderator,
                ),
                source_thread.pk,
            )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type=(
                    source_thread
                    ._meta
                    .verbose_name
                ),
                target_id=str(
                    source_thread.pk
                ),
                action=AuditLog.Action.SPLIT,
            ).exists()
        )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type=(
                    new_thread._meta.verbose_name
                ),
                target_id=str(new_thread.pk),
                action=AuditLog.Action.CREATE,
            ).exists()
        )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type=(
                    post._meta.verbose_name
                ),
                target_id=str(post.pk),
                action=AuditLog.Action.MOVE,
            ).exists()
        )

    def test_merge_view_uses_merge_action_for_both_threads(self):
        board = self.create_board(
            "Audit Merge Board"
        )

        source_thread = self.create_thread(
            board,
            title="Audit Merge Source",
        )

        destination_thread = self.create_thread(
            board,
            title="Audit Merge Destination",
        )

        with (
            patch(
                "community.views.ForumThreadMergeForm"
            ) as form_class,
            patch(
                "community.views.merge_forum_threads",
                return_value=destination_thread,
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "destination_thread":
                    destination_thread,
            }

            thread_merge(
                self.make_post_request(
                    "/audit/thread/merge/",
                    self.moderator,
                ),
                source_thread.pk,
            )

        for thread in (
            source_thread,
            destination_thread,
        ):
            with self.subTest(
                thread=thread.pk
            ):
                self.assertTrue(
                    AuditLog.objects.filter(
                        target_type=(
                            thread
                            ._meta
                            .verbose_name
                        ),
                        target_id=str(thread.pk),
                        action=(
                            AuditLog.Action.MERGE
                        ),
                    ).exists()
                )

    def test_post_report_creation_is_audited(self):
        board = self.create_board(
            "Audit Report Board"
        )

        thread = self.create_thread(
            board,
            title="Audit Report Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
            body="Reportable post.",
        )

        report = ForumPostReport.objects.create(
            post=post,
            reporter=self.member,
            reason="Audit test report.",
        )

        with (
            patch(
                "community.views.ForumPostReportForm"
            ) as form_class,
            patch(
                "community.views.create_post_report",
                return_value=report,
            ),
        ):
            form = form_class.return_value
            form.is_valid.return_value = True
            form.cleaned_data = {
                "reason":
                    "Audit test report.",
            }

            post_report(
                self.make_post_request(
                    "/audit/post/report/",
                    self.member,
                ),
                post.pk,
            )

        self.assertTrue(
            AuditLog.objects.filter(
                target_type=(
                    report._meta.verbose_name
                ),
                target_id=str(report.pk),
                action=AuditLog.Action.CREATE,
            ).exists()
        )

    def test_read_follow_and_subscription_state_do_not_create_audit_noise(self):
        board = self.create_board(
            "Audit Noise Board"
        )

        thread = self.create_thread(
            board,
            title="Audit Noise Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
            body="Audit noise post.",
        )

        recalculate_thread_last_post_at(
            thread
        )

        with (
            patch(
                "community.views.subscribe_to_board"
            ),
            patch(
                "community.views.unsubscribe_from_board"
            ),
            patch(
                "community.views.subscribe_to_thread"
            ),
            patch(
                "community.views.unsubscribe_from_thread"
            ),
        ):
            board_subscribe(
                self.make_post_request(
                    "/audit/board/subscribe/",
                    self.member,
                ),
                board.pk,
            )

            board_unsubscribe(
                self.make_post_request(
                    "/audit/board/unsubscribe/",
                    self.member,
                ),
                board.pk,
            )

            thread_follow(
                self.make_post_request(
                    "/audit/thread/follow/",
                    self.member,
                ),
                thread.pk,
            )

            thread_unfollow(
                self.make_post_request(
                    "/audit/thread/unfollow/",
                    self.member,
                ),
                thread.pk,
            )

        mark_thread_read(
            self.member,
            thread,
            newest_post=post,
        )

        self.assertEqual(
            AuditLog.objects.count(),
            0,
        )

    def test_audit_string_preserves_actor_label_after_actor_is_deleted(self):
        historical_actor = self.create_user(
            "historical_actor"
        )

        audit_log = AuditLog.objects.create(
            actor=historical_actor,
            actor_label=(
                historical_actor.display_name
            ),
            action=AuditLog.Action.UPDATE,
            target_type="Forum test object",
            target_id="123",
            target_label="Historical target",
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )

        historical_actor.delete()

        audit_log.refresh_from_db()

        self.assertIsNone(
            audit_log.actor
        )

        self.assertEqual(
            str(audit_log),
            (
                "historical_actor - "
                "Update - "
                "Historical target"
            ),
        )

class ForumFormTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def creation_target_formset_data(
        self,
        **target_values,
    ):
        data = {
            "creation_targets-TOTAL_FORMS": "1",
            "creation_targets-INITIAL_FORMS": "0",
            "creation_targets-MIN_NUM_FORMS": "0",
            "creation_targets-MAX_NUM_FORMS": "1000",
        }

        for field_name, value in target_values.items():
            data[
                f"creation_targets-0-{field_name}"
            ] = (
                value.pk
                if hasattr(value, "pk")
                else value
            )

        return data

    def test_targeted_board_requires_creation_target(self):
        board = self.create_board(
            "Targeted Form Board",
            policy=(
                ForumBoard
                .ThreadCreationPolicy
                .TARGETED
            ),
        )

        formset = (
            ForumBoardThreadCreationTargetFormSet(
                data=(
                    self.creation_target_formset_data()
                ),
                instance=board,
                prefix="creation_targets",
            )
        )

        self.assertFalse(
            formset.is_valid()
        )

        self.assertTrue(
            formset.non_form_errors()
        )

    def test_targeted_board_accepts_creation_target(self):
        board = self.create_board(
            "Targeted Valid Form Board",
            policy=(
                ForumBoard
                .ThreadCreationPolicy
                .TARGETED
            ),
        )

        formset = (
            ForumBoardThreadCreationTargetFormSet(
                data=(
                    self.creation_target_formset_data(
                        chapter=self.fyr_draca,
                    )
                ),
                instance=board,
                prefix="creation_targets",
            )
        )

        self.assertTrue(
            formset.is_valid(),
            formset.errors,
        )

    def test_non_targeted_board_does_not_require_creation_target(self):
        policies = (
            ForumBoard
            .ThreadCreationPolicy
            .OPEN,
            ForumBoard
            .ThreadCreationPolicy
            .STAFF_ONLY,
        )

        for policy in policies:
            with self.subTest(
                policy=policy
            ):
                board = self.create_board(
                    f"{policy} Form Board",
                    policy=policy,
                )

                formset = (
                    ForumBoardThreadCreationTargetFormSet(
                        data=(
                            self.creation_target_formset_data()
                        ),
                        instance=board,
                        prefix="creation_targets",
                    )
                )

                self.assertTrue(
                    formset.is_valid(),
                    formset.errors,
                )

    def test_target_form_rejects_user_combined_with_org_selector(self):
        form = ForumBoardTargetForm(
            data={
                "user": self.member.pk,
                "chapter": self.fyr_draca.pk,
            }
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertTrue(
            form.non_field_errors()
        )

    def test_thread_move_rejects_board_outside_supplied_queryset(self):
        allowed_board = self.create_board(
            "Allowed Move Board"
        )

        excluded_board = self.create_board(
            "Excluded Move Board"
        )

        form = ForumThreadMoveForm(
            data={
                "destination_board":
                    excluded_board.pk,
            },
            board_queryset=(
                ForumBoard.objects.filter(
                    pk=allowed_board.pk
                )
            ),
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "destination_board",
            form.errors,
        )

    def test_thread_merge_rejects_thread_outside_supplied_queryset(self):
        board = self.create_board(
            "Merge Form Board"
        )

        allowed_thread = self.create_thread(
            board,
            title="Allowed Merge Thread",
        )

        excluded_thread = self.create_thread(
            board,
            title="Excluded Merge Thread",
        )

        form = ForumThreadMergeForm(
            data={
                "destination_thread":
                    excluded_thread.pk,
            },
            thread_queryset=(
                ForumThread.objects.filter(
                    pk=allowed_thread.pk
                )
            ),
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "destination_thread",
            form.errors,
        )

    def test_thread_split_rejects_post_outside_supplied_queryset(self):
        source_board = self.create_board(
            "Split Form Source Board"
        )

        destination_board = self.create_board(
            "Split Form Destination Board"
        )

        source_thread = self.create_thread(
            source_board,
            title="Split Form Source Thread",
        )

        allowed_post = self.create_post(
            source_thread,
            author=self.member,
            body="Allowed split post.",
        )

        excluded_post = self.create_post(
            source_thread,
            author=self.member,
            body="Excluded split post.",
        )

        form = ForumThreadSplitForm(
            data={
                "title": "Split Result",
                "destination_board":
                    destination_board.pk,
                "posts": [
                    excluded_post.pk,
                ],
            },
            board_queryset=(
                ForumBoard.objects.filter(
                    pk=destination_board.pk
                )
            ),
            post_queryset=(
                ForumPost.objects.filter(
                    pk=allowed_post.pk
                )
            ),
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "posts",
            form.errors,
        )

    def test_post_move_rejects_objects_outside_supplied_querysets(self):
        source_board = self.create_board(
            "Post Move Form Source Board"
        )

        destination_board = self.create_board(
            "Post Move Form Destination Board"
        )

        source_thread = self.create_thread(
            source_board,
            title="Post Move Form Source Thread",
        )

        allowed_destination = (
            self.create_thread(
                destination_board,
                title=(
                    "Allowed Post Move "
                    "Destination"
                ),
            )
        )

        excluded_destination = (
            self.create_thread(
                destination_board,
                title=(
                    "Excluded Post Move "
                    "Destination"
                ),
            )
        )

        allowed_post = self.create_post(
            source_thread,
            author=self.member,
            body="Allowed move post.",
        )

        excluded_post = self.create_post(
            source_thread,
            author=self.member,
            body="Excluded move post.",
        )

        form = ForumPostMoveForm(
            data={
                "destination_thread":
                    excluded_destination.pk,
                "posts": [
                    excluded_post.pk,
                ],
            },
            thread_queryset=(
                ForumThread.objects.filter(
                    pk=allowed_destination.pk
                )
            ),
            post_queryset=(
                ForumPost.objects.filter(
                    pk=allowed_post.pk
                )
            ),
        )

        self.assertFalse(
            form.is_valid()
        )

        self.assertIn(
            "destination_thread",
            form.errors,
        )

        self.assertIn(
            "posts",
            form.errors,
        )

    def test_draft_form_allows_blank_title_and_body(self):
        form = ForumDraftContentForm(
            data={
                "title": "",
                "body": "",
            }
        )

        self.assertTrue(
            form.is_valid(),
            form.errors,
        )

class ForumRoutingAndViewTests(
    ForumPermissionFixtureMixin,
    TestCase,
):
    def create_report(
        self,
        *,
        reporter=None,
    ):
        if reporter is None:
            reporter = self.member

        board = self.create_board(
            "Route Report Board"
        )

        thread = self.create_thread(
            board,
            title="Route Report Thread",
        )

        post = self.create_post(
            thread,
            author=self.other_member,
            body="Report review test post.",
        )

        return ForumPostReport.objects.create(
            post=post,
            reporter=reporter,
            reason="Review this post.",
        )

    def test_post_report_review_route_resolves_to_correct_view(self):
        report = self.create_report()

        match = resolve(
            reverse(
                "community:post_report_review",
                args=[report.pk],
            )
        )

        self.assertEqual(
            match.func,
            post_report_review,
        )

        self.assertEqual(
            match.kwargs["report_id"],
            report.pk,
        )

    def test_post_report_review_rejects_get(self):
        report = self.create_report()

        self.client.force_login(
            self.moderator
        )

        response = self.client.get(
            reverse(
                "community:post_report_review",
                args=[report.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            405,
        )

        report.refresh_from_db()

        self.assertEqual(
            report.status,
            ForumPostReport.Status.OPEN,
        )

    def test_post_report_review_rejects_non_moderator(self):
        report = self.create_report()

        self.client.force_login(
            self.member
        )

        response = self.client.post(
            reverse(
                "community:post_report_review",
                args=[report.pk],
            ),
            {
                "status":
                    ForumPostReport
                    .Status
                    .RESOLVED,
                "resolution_note":
                    "Should not be allowed.",
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        report.refresh_from_db()

        self.assertEqual(
            report.status,
            ForumPostReport.Status.OPEN,
        )

        self.assertIsNone(
            report.reviewed_by
        )

    def test_moderator_can_resolve_report(self):
        report = self.create_report()

        self.client.force_login(
            self.moderator
        )

        response = self.client.post(
            reverse(
                "community:post_report_review",
                args=[report.pk],
            ),
            {
                "status":
                    ForumPostReport
                    .Status
                    .RESOLVED,
                "resolution_note":
                    "Reviewed and resolved.",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        report.refresh_from_db()

        self.assertEqual(
            report.status,
            ForumPostReport.Status.RESOLVED,
        )

        self.assertEqual(
            report.reviewed_by,
            self.moderator,
        )

        self.assertIsNotNone(
            report.reviewed_at
        )

        self.assertEqual(
            report.resolution_note,
            "Reviewed and resolved.",
        )

        audit_log = AuditLog.objects.get(
            target_type=(
                report._meta.verbose_name
            ),
            target_id=str(report.pk),
            action=AuditLog.Action.UPDATE,
        )

        self.assertEqual(
            audit_log.actor,
            self.moderator,
        )

        self.assertEqual(
            audit_log.old_value["status"],
            ForumPostReport.Status.OPEN,
        )

        self.assertEqual(
            audit_log.new_value["status"],
            ForumPostReport.Status.RESOLVED,
        )

    def test_moderator_can_dismiss_report(self):
        report = self.create_report()

        self.client.force_login(
            self.moderator
        )

        response = self.client.post(
            reverse(
                "community:post_report_review",
                args=[report.pk],
            ),
            {
                "status":
                    ForumPostReport
                    .Status
                    .DISMISSED,
                "resolution_note":
                    "No moderation action required.",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        report.refresh_from_db()

        self.assertEqual(
            report.status,
            ForumPostReport.Status.DISMISSED,
        )

        self.assertEqual(
            report.reviewed_by,
            self.moderator,
        )

        self.assertEqual(
            report.resolution_note,
            "No moderation action required.",
        )

    def test_invalid_report_review_status_does_not_change_report(self):
        report = self.create_report()

        self.client.force_login(
            self.moderator
        )

        response = self.client.post(
            reverse(
                "community:post_report_review",
                args=[report.pk],
            ),
            {
                "status": "INVALID",
                "resolution_note":
                    "Invalid status test.",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        report.refresh_from_db()

        self.assertEqual(
            report.status,
            ForumPostReport.Status.OPEN,
        )

        self.assertIsNone(
            report.reviewed_at
        )

        self.assertIsNone(
            report.reviewed_by
        )

        self.assertFalse(
            AuditLog.objects.filter(
                target_type=(
                    report._meta.verbose_name
                ),
                target_id=str(report.pk),
                action=AuditLog.Action.UPDATE,
            ).exists()
        )

    def test_merged_thread_redirects_to_accessible_destination(self):
        board = self.create_board(
            "Merged Redirect Board"
        )

        source_thread = self.create_thread(
            board,
            title="Merged Redirect Source",
            archived=True,
        )

        destination_thread = self.create_thread(
            board,
            title="Merged Redirect Destination",
        )

        source_thread.merged_into = (
            destination_thread
        )

        source_thread.save(
            update_fields=[
                "merged_into",
            ]
        )

        self.client.force_login(
            self.member
        )

        response = self.client.get(
            reverse(
                "community:thread_detail",
                args=[source_thread.pk],
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "community:thread_detail",
                args=[destination_thread.pk],
            ),
            fetch_redirect_response=False,
        )

    def test_merged_thread_does_not_leak_inaccessible_destination(self):
        board = self.create_board(
            "Protected Merge Board"
        )

        source_thread = self.create_thread(
            board,
            title="Protected Merge Source",
            archived=True,
        )

        destination_thread = self.create_thread(
            board,
            title="Protected Merge Destination",
        )

        ForumThreadTarget.objects.create(
            thread=destination_thread,
            user=self.other_member,
        )

        source_thread.merged_into = (
            destination_thread
        )

        source_thread.save(
            update_fields=[
                "merged_into",
            ]
        )

        self.client.force_login(
            self.member
        )

        response = self.client.get(
            reverse(
                "community:thread_detail",
                args=[source_thread.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertFalse(
            response.has_header(
                "Location"
            )
        )

    def test_archive_viewer_can_open_archived_board_directly(self):
        board = self.create_board(
            "Archived Direct Board",
            archived=True,
        )

        self.client.force_login(
            self.archive_viewer
        )

        with patch(
            "community.views.render",
            return_value=HttpResponse(
                "Archived board"
            ),
        ):
            response = self.client.get(
                reverse(
                    "community:board_detail",
                    args=[board.pk],
                )
            )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_member_cannot_open_archived_board_directly(self):
        board = self.create_board(
            "Hidden Archived Direct Board",
            archived=True,
        )

        self.client.force_login(
            self.member
        )

        response = self.client.get(
            reverse(
                "community:board_detail",
                args=[board.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_board_restore_redirects_to_board_when_parent_is_active(self):
        board = self.create_board(
            "Restored Active Parent Board",
            archived=True,
        )

        self.client.force_login(
            self.board_manager
        )

        response = self.client.post(
            reverse(
                "community:board_restore",
                args=[board.pk],
            )
        )

        board.refresh_from_db()

        self.assertIsNone(
            board.archived_at
        )

        self.assertRedirects(
            response,
            reverse(
                "community:board_detail",
                args=[board.pk],
            ),
            fetch_redirect_response=False,
        )

    def test_board_restore_redirects_to_index_when_parent_remains_archived(self):
        category = self.create_category(
            "Archived Restore Parent",
            archived=True,
        )

        board = self.create_board(
            "Restored Hidden Parent Board",
            category=category,
            archived=True,
        )

        self.client.force_login(
            self.board_manager
        )

        response = self.client.post(
            reverse(
                "community:board_restore",
                args=[board.pk],
            )
        )

        board.refresh_from_db()

        self.assertIsNone(
            board.archived_at
        )

        self.assertRedirects(
            response,
            reverse(
                "community:forum_index"
            ),
            fetch_redirect_response=False,
        )