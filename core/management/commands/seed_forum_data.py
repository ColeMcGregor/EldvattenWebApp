from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import AccountStatus
from community.models import (
    ForumBoard,
    ForumBoardSubscription,
    ForumBoardTarget,
    ForumBoardThreadCreationTarget,
    ForumCategory,
    ForumDraft,
    ForumPost,
    ForumPostAttachment,
    ForumPostQuote,
    ForumPostReport,
    ForumThread,
    ForumThreadReadState,
    ForumThreadSubscription,
    ForumThreadTarget,
)
from organization.models import CommunityGroup


User = get_user_model()


SEED_PREFIX = "[DEV]"

TEST_GROUP_NAME = "Test Custom Group"

FILLER_TEXT = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Lorem ipsum dolor sit amet."
)


class Command(BaseCommand):
    help = (
        "Create deterministic development Forum data for "
        "UI and feature testing."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_forum_data can only run when DEBUG is enabled."
            )

        users = self.get_required_users()
        test_group = self.get_required_group()

        self.clear_existing_seed_data()

        now = timezone.now()

        categories = self.create_categories(
            users=users,
            now=now,
        )

        boards = self.create_boards(
            categories=categories,
            users=users,
            test_group=test_group,
            now=now,
        )

        threads = self.create_threads(
            boards=boards,
            users=users,
            test_group=test_group,
            now=now,
        )

        posts = self.create_posts(
            threads=threads,
            users=users,
            now=now,
        )

        self.create_post_features(
            posts=posts,
            users=users,
        )

        self.create_read_states(
            threads=threads,
            users=users,
            now=now,
        )

        self.create_subscriptions(
            boards=boards,
            threads=threads,
            users=users,
        )

        self.create_drafts(
            boards=boards,
            threads=threads,
            users=users,
        )

        self.update_thread_last_post_times(
            threads=threads,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Forum development data seeded successfully."
            )
        )

        self.stdout.write(
            "Categories: "
            f"{ForumCategory.objects.filter(name__startswith=SEED_PREFIX).count()}"
        )

        self.stdout.write(
            "Boards: "
            f"{ForumBoard.objects.filter(category__name__startswith=SEED_PREFIX).count()}"
        )

        self.stdout.write(
            "Threads: "
            f"{ForumThread.objects.filter(board__category__name__startswith=SEED_PREFIX).count()}"
        )

        self.stdout.write(
            "Posts: "
            f"{ForumPost.objects.filter(thread__board__category__name__startswith=SEED_PREFIX).count()}"
        )

        self.stdout.write("")
        self.stdout.write("Useful accounts:")
        self.stdout.write("  testuser01 - normal member")
        self.stdout.write("  testuser02 - normal member")
        self.stdout.write(
            "  testuser40 - forum administrator/moderator"
        )
        self.stdout.write(
            "  testuser41 - forum administrator/moderator"
        )

    def get_required_users(self):
        required_usernames = {
            "member": "testuser01",
            "member_two": "testuser02",
            "member_three": "testuser04",
            "member_four": "testuser05",
            "member_five": "testuser07",
            "moderator": "testuser40",
            "administrator": "testuser41",
            "staff_only": "testuser52",
        }

        users = {}

        for key, username in required_usernames.items():
            try:
                user = User.objects.get(
                    username=username
                )
            except User.DoesNotExist as error:
                raise CommandError(
                    f"Required development user {username} "
                    "does not exist. Run seed_dev_data first."
                ) from error

            if (
                user.account_status
                != AccountStatus.MEMBER
            ):
                raise CommandError(
                    f"Required development user {username} "
                    "must have MEMBER account status."
                )

            if not user.is_active:
                raise CommandError(
                    f"Required development user {username} "
                    "must be active."
                )

            users[key] = user

        return users

    def get_required_group(self):
        try:
            return CommunityGroup.objects.get(
                name=TEST_GROUP_NAME
            )
        except CommunityGroup.DoesNotExist as error:
            raise CommandError(
                f"{TEST_GROUP_NAME} does not exist. "
                "Run seed_dev_data first."
            ) from error

    def clear_existing_seed_data(self):
        categories = ForumCategory.objects.filter(
            name__startswith=SEED_PREFIX
        )

        boards = ForumBoard.objects.filter(
            category__in=categories
        )

        threads = ForumThread.objects.filter(
            board__in=boards
        )

        ForumPost.objects.filter(
            thread__in=threads
        ).delete()

        threads.delete()
        boards.delete()
        categories.delete()

    def create_categories(
        self,
        *,
        users,
        now,
    ):
        general = ForumCategory.objects.create(
            name=f"{SEED_PREFIX} General",
            description=FILLER_TEXT,
            display_order=10,
        )

        activities = ForumCategory.objects.create(
            name=f"{SEED_PREFIX} Activities",
            description=FILLER_TEXT,
            display_order=20,
        )

        restricted = ForumCategory.objects.create(
            name=f"{SEED_PREFIX} Restricted",
            description=FILLER_TEXT,
            display_order=30,
        )

        empty = ForumCategory.objects.create(
            name=f"{SEED_PREFIX} Empty Category",
            description=FILLER_TEXT,
            display_order=40,
        )

        archived = ForumCategory.objects.create(
            name=f"{SEED_PREFIX} Archived Category",
            description=FILLER_TEXT,
            display_order=50,
            archived_at=(
                now
                - timedelta(days=30)
            ),
            archived_by=users["administrator"],
        )

        return {
            "general": general,
            "activities": activities,
            "restricted": restricted,
            "empty": empty,
            "archived": archived,
        }

    def create_boards(
        self,
        *,
        categories,
        users,
        test_group,
        now,
    ):
        camp_planning = ForumBoard.objects.create(
            category=categories["general"],
            name="Camp Planning",
            description=FILLER_TEXT,
            display_order=10,
        )

        general_discussion = ForumBoard.objects.create(
            category=categories["general"],
            name="General Discussion",
            description=FILLER_TEXT,
            display_order=20,
        )

        empty_board = ForumBoard.objects.create(
            category=categories["general"],
            name="Empty Board",
            description=FILLER_TEXT,
            display_order=30,
        )

        staff_announcements = ForumBoard.objects.create(
            category=categories["general"],
            name="Staff Announcements",
            description=FILLER_TEXT,
            display_order=40,
            thread_creation_policy=(
                ForumBoard
                .ThreadCreationPolicy
                .STAFF_ONLY
            ),
        )

        event_discussion = ForumBoard.objects.create(
            category=categories["activities"],
            name="Event Discussion",
            description=FILLER_TEXT,
            display_order=10,
        )

        arts_and_sciences = ForumBoard.objects.create(
            category=categories["activities"],
            name="Arts and Sciences",
            description=FILLER_TEXT,
            display_order=20,
        )

        locked_board = ForumBoard.objects.create(
            category=categories["activities"],
            name="Locked Board",
            description=FILLER_TEXT,
            display_order=30,
            is_locked=True,
            locked_at=(
                now
                - timedelta(days=5)
            ),
            locked_by=users["moderator"],
        )

        archived_board = ForumBoard.objects.create(
            category=categories["activities"],
            name="Archived Board",
            description=FILLER_TEXT,
            display_order=40,
            archived_at=(
                now
                - timedelta(days=20)
            ),
            archived_by=users["administrator"],
        )

        test_group_board = ForumBoard.objects.create(
            category=categories["restricted"],
            name="Test Group Board",
            description=FILLER_TEXT,
            display_order=10,
        )

        ForumBoardTarget.objects.create(
            board=test_group_board,
            community_group=test_group,
        )

        targeted_creation = ForumBoard.objects.create(
            category=categories["restricted"],
            name="Targeted Thread Creation",
            description=FILLER_TEXT,
            display_order=20,
            thread_creation_policy=(
                ForumBoard
                .ThreadCreationPolicy
                .TARGETED
            ),
        )

        ForumBoardThreadCreationTarget.objects.create(
            board=targeted_creation,
            community_group=test_group,
        )

        archived_category_board = (
            ForumBoard.objects.create(
                category=categories["archived"],
                name="Archived Category Board",
                description=FILLER_TEXT,
                display_order=10,
            )
        )

        return {
            "camp_planning": camp_planning,
            "general_discussion": general_discussion,
            "empty_board": empty_board,
            "staff_announcements": staff_announcements,
            "event_discussion": event_discussion,
            "arts_and_sciences": arts_and_sciences,
            "locked_board": locked_board,
            "archived_board": archived_board,
            "test_group_board": test_group_board,
            "targeted_creation": targeted_creation,
            "archived_category_board": (
                archived_category_board
            ),
        }

    def create_threads(
        self,
        *,
        boards,
        users,
        test_group,
        now,
    ):
        prepping_tents = self.create_thread(
            board=boards["camp_planning"],
            title="Prepping Tents",
            created_by=users["member"],
            created_at=(
                now
                - timedelta(days=12)
            ),
            is_pinned=True,
            pinned_by=users["moderator"],
            pinned_at=(
                now
                - timedelta(days=11)
            ),
        )

        camp_setup = self.create_thread(
            board=boards["camp_planning"],
            title="Camp Setup",
            created_by=users["member_two"],
            created_at=(
                now
                - timedelta(days=9)
            ),
        )

        carpool_planning = self.create_thread(
            board=boards["camp_planning"],
            title="Carpool Planning",
            created_by=users["member_three"],
            created_at=(
                now
                - timedelta(days=8)
            ),
            is_locked=True,
            locked_by=users["moderator"],
            locked_at=(
                now
                - timedelta(days=2)
            ),
        )

        empty_thread = self.create_thread(
            board=boards["camp_planning"],
            title="Empty Thread",
            created_by=users["member_four"],
            created_at=(
                now
                - timedelta(days=6)
            ),
        )

        welcome = self.create_thread(
            board=boards["general_discussion"],
            title="Welcome Thread",
            created_by=users["administrator"],
            created_at=(
                now
                - timedelta(days=15)
            ),
            is_pinned=True,
            pinned_by=users["administrator"],
            pinned_at=(
                now
                - timedelta(days=15)
            ),
            is_locked=True,
            locked_by=users["administrator"],
            locked_at=(
                now
                - timedelta(days=15)
            ),
        )

        targeted_thread = self.create_thread(
            board=boards["general_discussion"],
            title="User Target Test",
            created_by=users["member_two"],
            created_at=(
                now
                - timedelta(days=5)
            ),
        )

        ForumThreadTarget.objects.create(
            thread=targeted_thread,
            user=users["member_two"],
        )

        event_planning = self.create_thread(
            board=boards["event_discussion"],
            title="Event Planning",
            created_by=users["member_four"],
            created_at=(
                now
                - timedelta(days=10)
            ),
        )

        archived_thread = self.create_thread(
            board=boards["event_discussion"],
            title="Archived Thread",
            created_by=users["member_five"],
            created_at=(
                now
                - timedelta(days=25)
            ),
            archived_at=(
                now
                - timedelta(days=18)
            ),
            archived_by=users["moderator"],
        )

        arts_thread = self.create_thread(
            board=boards["arts_and_sciences"],
            title="Project Discussion",
            created_by=users["member_three"],
            created_at=(
                now
                - timedelta(days=7)
            ),
        )

        locked_board_thread = self.create_thread(
            board=boards["locked_board"],
            title="Thread in Locked Board",
            created_by=users["administrator"],
            created_at=(
                now
                - timedelta(days=7)
            ),
        )

        archived_board_thread = self.create_thread(
            board=boards["archived_board"],
            title="Thread in Archived Board",
            created_by=users["administrator"],
            created_at=(
                now
                - timedelta(days=22)
            ),
        )

        test_group_thread = self.create_thread(
            board=boards["test_group_board"],
            title="Restricted Group Discussion",
            created_by=users["member"],
            created_at=(
                now
                - timedelta(days=4)
            ),
        )

        targeted_creation_thread = (
            self.create_thread(
                board=boards["targeted_creation"],
                title="Targeted Creation Test",
                created_by=users["member"],
                created_at=(
                    now
                    - timedelta(days=3)
                ),
            )
        )

        group_targeted_thread = self.create_thread(
            board=boards["general_discussion"],
            title="Group Target Test",
            created_by=users["member"],
            created_at=(
                now
                - timedelta(days=3)
            ),
        )

        ForumThreadTarget.objects.create(
            thread=group_targeted_thread,
            community_group=test_group,
        )

        archived_category_thread = (
            self.create_thread(
                board=boards[
                    "archived_category_board"
                ],
                title="Archived Category Thread",
                created_by=users["administrator"],
                created_at=(
                    now
                    - timedelta(days=35)
                ),
            )
        )

        return {
            "prepping_tents": prepping_tents,
            "camp_setup": camp_setup,
            "carpool_planning": carpool_planning,
            "empty_thread": empty_thread,
            "welcome": welcome,
            "targeted_thread": targeted_thread,
            "event_planning": event_planning,
            "archived_thread": archived_thread,
            "arts_thread": arts_thread,
            "locked_board_thread": (
                locked_board_thread
            ),
            "archived_board_thread": (
                archived_board_thread
            ),
            "test_group_thread": (
                test_group_thread
            ),
            "targeted_creation_thread": (
                targeted_creation_thread
            ),
            "group_targeted_thread": (
                group_targeted_thread
            ),
            "archived_category_thread": (
                archived_category_thread
            ),
        }

    def create_thread(
        self,
        *,
        board,
        title,
        created_by,
        created_at,
        is_pinned=False,
        pinned_by=None,
        pinned_at=None,
        is_locked=False,
        locked_by=None,
        locked_at=None,
        archived_at=None,
        archived_by=None,
    ):
        thread = ForumThread.objects.create(
            board=board,
            title=title,
            created_by=created_by,
            is_pinned=is_pinned,
            pinned_by=pinned_by,
            pinned_at=pinned_at,
            is_locked=is_locked,
            locked_by=locked_by,
            locked_at=locked_at,
            archived_at=archived_at,
            archived_by=archived_by,
        )

        ForumThread.objects.filter(
            pk=thread.pk
        ).update(
            created_at=created_at,
            updated_at=created_at,
        )

        thread.created_at = created_at
        thread.updated_at = created_at

        return thread

    def create_posts(
        self,
        *,
        threads,
        users,
        now,
    ):
        posts = {}

        posts["prepping_tents"] = []

        authors = [
            users["member"],
            users["member_two"],
            users["member_three"],
            users["member_four"],
            users["member_five"],
        ]

        for index in range(18):
            post_time = (
                now
                - timedelta(days=11)
                + timedelta(
                    hours=index * 12
                )
            )

            post = self.create_post(
                thread=threads["prepping_tents"],
                author=authors[
                    index % len(authors)
                ],
                body=(
                    f"Development post {index + 1}.\n\n"
                    f"{FILLER_TEXT}"
                ),
                created_at=post_time,
            )

            posts["prepping_tents"].append(
                post
            )

        archived_post = posts["prepping_tents"][6]

        archived_at = (
            archived_post.created_at
            + timedelta(hours=1)
        )

        ForumPost.objects.filter(
            pk=archived_post.pk
        ).update(
            archived_at=archived_at,
            archived_by=users["moderator"],
        )

        archived_post.archived_at = archived_at
        archived_post.archived_by = (
            users["moderator"]
        )

        posts["camp_setup"] = [
            self.create_post(
                thread=threads["camp_setup"],
                author=users["member_two"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=8)
                ),
            ),
            self.create_post(
                thread=threads["camp_setup"],
                author=users["member"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=2)
                ),
            ),
        ]

        posts["carpool_planning"] = [
            self.create_post(
                thread=threads[
                    "carpool_planning"
                ],
                author=users["member_three"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=7)
                ),
            ),
            self.create_post(
                thread=threads[
                    "carpool_planning"
                ],
                author=users["member_four"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=3)
                ),
            ),
        ]

        posts["welcome"] = [
            self.create_post(
                thread=threads["welcome"],
                author=users["administrator"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=15)
                ),
            )
        ]

        posts["targeted_thread"] = [
            self.create_post(
                thread=threads[
                    "targeted_thread"
                ],
                author=users["member_two"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=4)
                ),
            )
        ]

        posts["event_planning"] = [
            self.create_post(
                thread=threads[
                    "event_planning"
                ],
                author=users["member_four"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=9)
                ),
            ),
            self.create_post(
                thread=threads[
                    "event_planning"
                ],
                author=users["member_five"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=6)
                ),
            ),
            self.create_post(
                thread=threads[
                    "event_planning"
                ],
                author=users["member"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=1)
                ),
            ),
        ]

        posts["archived_thread"] = [
            self.create_post(
                thread=threads[
                    "archived_thread"
                ],
                author=users["member_five"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=24)
                ),
            )
        ]

        posts["arts_thread"] = [
            self.create_post(
                thread=threads[
                    "arts_thread"
                ],
                author=users["member_three"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=6)
                ),
            ),
            self.create_post(
                thread=threads[
                    "arts_thread"
                ],
                author=users["member_two"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(hours=18)
                ),
            ),
        ]

        posts["locked_board_thread"] = [
            self.create_post(
                thread=threads[
                    "locked_board_thread"
                ],
                author=users["administrator"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=6)
                ),
            )
        ]

        posts["archived_board_thread"] = [
            self.create_post(
                thread=threads[
                    "archived_board_thread"
                ],
                author=users["administrator"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=21)
                ),
            )
        ]

        posts["test_group_thread"] = [
            self.create_post(
                thread=threads[
                    "test_group_thread"
                ],
                author=users["member"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=3)
                ),
            )
        ]

        posts["targeted_creation_thread"] = [
            self.create_post(
                thread=threads[
                    "targeted_creation_thread"
                ],
                author=users["member"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=2)
                ),
            )
        ]

        posts["group_targeted_thread"] = [
            self.create_post(
                thread=threads[
                    "group_targeted_thread"
                ],
                author=users["member"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=2)
                ),
            )
        ]

        posts["archived_category_thread"] = [
            self.create_post(
                thread=threads[
                    "archived_category_thread"
                ],
                author=users["administrator"],
                body=FILLER_TEXT,
                created_at=(
                    now
                    - timedelta(days=34)
                ),
            )
        ]

        return posts

    def create_post(
        self,
        *,
        thread,
        author,
        body,
        created_at,
    ):
        post = ForumPost.objects.create(
            thread=thread,
            author=author,
            body=body,
        )

        ForumPost.objects.filter(
            pk=post.pk
        ).update(
            created_at=created_at,
        )

        post.created_at = created_at

        return post

    def create_post_features(
        self,
        *,
        posts,
        users,
    ):
        quoted_post = posts[
            "prepping_tents"
        ][2]

        quoting_post = posts[
            "prepping_tents"
        ][10]

        ForumPostQuote.objects.create(
            post=quoting_post,
            quoted_post=quoted_post,
        )

        quoting_post.body = (
            "Quoted from Test User 04:\n"
            "> Lorem ipsum dolor sit amet.\n\n"
            f"{FILLER_TEXT}"
        )

        quoting_post.edited_at = (
            quoting_post.created_at
            + timedelta(minutes=5)
        )

        quoting_post.edited_by = (
            users["member"]
        )

        quoting_post.save(
            update_fields=[
                "body",
                "edited_at",
                "edited_by",
            ]
        )

        ForumPostAttachment.objects.create(
            post=posts["event_planning"][0],
            label="Development Link",
            url=(
                "https://example.com/"
                "eldvatten-forum-test"
            ),
            display_order=0,
        )

        ForumPostAttachment.objects.create(
            post=posts[
                "prepping_tents"
            ][4],
            label="Tent Reference",
            url=(
                "https://example.com/"
                "tent-reference"
            ),
            display_order=0,
        )

        ForumPostReport.objects.create(
            post=posts["event_planning"][0],
            reporter=users["member"],
            reason=(
                "Development report for "
                "moderation UI testing."
            ),
            status=(
                ForumPostReport.Status.OPEN
            ),
        )

    def create_read_states(
        self,
        *,
        threads,
        users,
        now,
    ):
        ForumThreadReadState.objects.create(
            user=users["member"],
            thread=threads["prepping_tents"],
            last_read_at=now,
        )

        ForumThreadReadState.objects.create(
            user=users["member"],
            thread=threads["camp_setup"],
            last_read_at=(
                now
                - timedelta(days=6)
            ),
        )

        ForumThreadReadState.objects.create(
            user=users["member_two"],
            thread=threads["welcome"],
            last_read_at=(
                now
                - timedelta(days=20)
            ),
        )

        ForumThreadReadState.objects.create(
            user=users["member_two"],
            thread=threads["event_planning"],
            last_read_at=now,
        )

    def create_subscriptions(
        self,
        *,
        boards,
        threads,
        users,
    ):
        ForumBoardSubscription.objects.create(
            user=users["member"],
            board=boards["camp_planning"],
        )

        ForumBoardSubscription.objects.create(
            user=users["member_two"],
            board=boards["event_discussion"],
        )

        for thread in threads.values():
            if (
                thread.created_by_id is not None
                and thread.archived_at is None
                and thread.board.archived_at
                is None
                and thread.board.category
                .archived_at is None
            ):
                ForumThreadSubscription.objects.get_or_create(
                    user=thread.created_by,
                    thread=thread,
                )

        ForumThreadSubscription.objects.get_or_create(
            user=users["member"],
            thread=threads["camp_setup"],
        )

        ForumThreadSubscription.objects.get_or_create(
            user=users["member_two"],
            thread=threads["prepping_tents"],
        )

    def create_drafts(
        self,
        *,
        boards,
        threads,
        users,
    ):
        ForumDraft.objects.create(
            user=users["member"],
            draft_type=(
                ForumDraft.DraftType.THREAD
            ),
            board=boards["camp_planning"],
            title="Development Thread Draft",
            body=FILLER_TEXT,
            target_data=[],
            attachment_links=[
                {
                    "label": "Draft Link",
                    "url": (
                        "https://example.com/"
                        "draft-thread-link"
                    ),
                    "display_order": 0,
                }
            ],
            quoted_post_ids=[],
        )

        ForumDraft.objects.create(
            user=users["member_two"],
            draft_type=(
                ForumDraft.DraftType.POST
            ),
            thread=threads["prepping_tents"],
            title="",
            body=FILLER_TEXT,
            target_data=[],
            attachment_links=[],
            quoted_post_ids=[],
        )

    def update_thread_last_post_times(
        self,
        *,
        threads,
    ):
        for thread in threads.values():
            newest_active_post = (
                ForumPost.objects
                .filter(
                    thread=thread,
                    archived_at__isnull=True,
                )
                .order_by(
                    "-created_at",
                    "-id",
                )
                .first()
            )

            last_post_at = (
                newest_active_post.created_at
                if newest_active_post
                is not None
                else None
            )

            ForumThread.objects.filter(
                pk=thread.pk
            ).update(
                last_post_at=last_post_at
            )