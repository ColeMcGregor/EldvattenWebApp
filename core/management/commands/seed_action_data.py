
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import AccountStatus
from actions.models import (
    Action,
    ActionAssignment,
    ActionTarget,
)
from actions.services import resolve_action_targets
from community.models import ForumThread
from notifications.models import Notification
from organization.models import (
    Chapter,
    CitizenshipClass,
    CommunityGroup,
    GovernanceBody,
    Household,
    HouseholdLeadershipType,
    Office,
    Order,
    OrderRank,
    SocialRank,
)


User = get_user_model()

SEED_PREFIX = "[DEV ACTION]"
TEST_GROUP_NAME = "Test Custom Group"

FILLER_TEXT = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. "
)

ACTION_PERMISSIONS = (
    "view_action",
    "add_action",
    "change_action",
    "delete_action",
)

PERMISSION_TEST_USERS = {
    "testuser40": ACTION_PERMISSIONS,
    "testuser41": ("view_action",),
    "testuser42": ("add_action",),
}

REQUIRED_USERS = {
    "suTest": AccountStatus.MEMBER,
    "testuser01": AccountStatus.MEMBER,
    "testuser02": AccountStatus.MEMBER,
    "testuser03": AccountStatus.PENDING,
    "testuser04": AccountStatus.MEMBER,
    "testuser05": AccountStatus.MEMBER,
    "testuser06": AccountStatus.SUSPENDED,
    "testuser07": AccountStatus.MEMBER,
    "testuser09": AccountStatus.DISABLED,
    "testuser16": AccountStatus.MEMBER,
    "testuser19": AccountStatus.MEMBER,
    "testuser22": AccountStatus.MEMBER,
    "testuser40": AccountStatus.MEMBER,
    "testuser41": AccountStatus.MEMBER,
    "testuser42": AccountStatus.MEMBER,
}

REFERENCE_MODELS = {
    "community_group": (
        CommunityGroup,
        ("Test Custom Group",),
    ),
    "chapter": (
        Chapter,
        ("Fyr Draca Chapter", "Seattle Chapter"),
    ),
    "citizenship_class": (
        CitizenshipClass,
        ("Active Citizen",),
    ),
    "social_rank": (
        SocialRank,
        ("Godi",),
    ),
    "household": (
        Household,
        ("House Kraken", "House Hvit Hrafn"),
    ),
    "governance_body": (
        GovernanceBody,
        ("Godi Council",),
    ),
    "order": (
        Order,
        ("Order of Air",),
    ),
    "order_rank": (
        OrderRank,
        ("Larling", "Gesallen"),
    ),
    "office": (
        Office,
        ("Lawspeaker",),
    ),
    "household_leadership_type": (
        HouseholdLeadershipType,
        ("Leading Jarl",),
    ),
}


class Command(BaseCommand):
    help = (
        "Create repeatable development Actions for assignment, "
        "targeting, completion, permission, and interface testing."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_action_data can only run when DEBUG is enabled."
            )

        self.now = timezone.now()
        self.users = self.get_required_users()
        self.references = self.get_required_references()
        self.validate_group_membership()
        self.threads = self.get_available_threads()

        self.configure_action_permissions()
        self.clear_existing_seed_data()

        self.created_actions = []

        self.create_personal_actions()
        self.create_targeted_actions()
        self.create_lifecycle_actions()
        self.create_edge_case_actions()

        seeded_actions = Action.objects.filter(
            title__startswith=SEED_PREFIX,
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                "Action development data seeded successfully."
            )
        )

        self.stdout.write(
            f"Actions: {seeded_actions.count()}"
        )

        self.stdout.write(
            "Targets: "
            f"{ActionTarget.objects.filter(action__in=seeded_actions).count()}"
        )

        assignments = ActionAssignment.objects.filter(
            action__in=seeded_actions,
        )

        self.stdout.write(
            f"Assignments: {assignments.count()}"
        )

        self.stdout.write(
            "Outstanding active assignments: "
            f"{assignments.filter(is_active=True).exclude(status=ActionAssignment.Status.COMPLETED).count()}"
        )

        self.stdout.write(
            "Completed active assignments: "
            f"{assignments.filter(is_active=True, status=ActionAssignment.Status.COMPLETED).count()}"
        )

        self.stdout.write(
            "Inactive assignments: "
            f"{assignments.filter(is_active=False).count()}"
        )

        self.stdout.write(
            "Linked Tavern threads: "
            f"{sum(action.linked_threads.count() for action in self.created_actions)}"
        )

        self.stdout.write("")
        self.stdout.write("Useful accounts:")
        self.stdout.write("  suTest     - superuser")
        self.stdout.write("  testuser01 - main Action test member")
        self.stdout.write("  testuser02 - second member")
        self.stdout.write("  testuser16 - organizational target member")
        self.stdout.write("  testuser40 - Action manager")
        self.stdout.write("  testuser41 - Action viewer")
        self.stdout.write("  testuser42 - add-only Action user")
        self.stdout.write("  testuser03 - pending account")
        self.stdout.write("  testuser06 - suspended account")
        self.stdout.write("  testuser09 - disabled account")

        self.stdout.write("")
        self.stdout.write(
            "Run this command again to replace the seeded Actions."
        )

    def get_required_users(self):
        users = {}

        for username, expected_status in REQUIRED_USERS.items():
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist as error:
                raise CommandError(
                    f"Required user {username} does not exist. "
                    "Run seed_dev_data first."
                ) from error

            if user.account_status != expected_status:
                raise CommandError(
                    f"{username} has account status "
                    f"{user.account_status}, expected {expected_status}. "
                    "Run seed_dev_data first."
                )

            if (
                expected_status == AccountStatus.MEMBER
                and not user.is_active
            ):
                raise CommandError(
                    f"{username} must be active."
                )

            users[username] = user

        if not users["suTest"].is_superuser:
            raise CommandError(
                "suTest must be a superuser. Run seed_dev_data first."
            )

        return users

    def get_required_references(self):
        references = {}

        for field_name, configuration in REFERENCE_MODELS.items():
            model, names = configuration
            records = {}

            for name in names:
                try:
                    records[name] = model.objects.get(name=name)
                except model.DoesNotExist as error:
                    raise CommandError(
                        f"Required {field_name} '{name}' does not exist. "
                        "Run seed_dev_data first."
                    ) from error

            references[field_name] = records

        return references

    def validate_group_membership(self):
        from organization.models import GroupMembership

        group = self.references["community_group"][
            TEST_GROUP_NAME
        ]

        for username in ("testuser01", "testuser16", "testuser19"):
            if not GroupMembership.objects.filter(
                user=self.users[username],
                community_group=group,
                ended_at__isnull=True,
            ).exists():
                raise CommandError(
                    f"{username} must belong to {TEST_GROUP_NAME}. "
                    "Run seed_dev_data first."
                )

    def configure_action_permissions(self):
        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="actions",
                codename__in=ACTION_PERMISSIONS,
            )
        }

        missing = set(ACTION_PERMISSIONS) - set(permissions)

        if missing:
            raise CommandError(
                "Missing Action permissions: "
                + ", ".join(sorted(missing))
                + ". Run migrations first."
            )

        for username, codenames in PERMISSION_TEST_USERS.items():
            user = self.users[username]

            user.user_permissions.remove(
                *permissions.values()
            )

            user.user_permissions.add(
                *(permissions[name] for name in codenames)
            )

    def get_available_threads(self):
        desired_titles = {
            "Prepping Tents",
            "Camp Setup",
            "Carpool Planning",
        }

        threads = {}

        queryset = (
            ForumThread.objects
            .filter(
                title__in=desired_titles,
                board__category__name__startswith="[DEV]",
                archived_at__isnull=True,
                board__archived_at__isnull=True,
                board__category__archived_at__isnull=True,
            )
            .select_related("board")
            .order_by("id")
        )

        for thread in queryset:
            threads.setdefault(thread.title, thread)

        if len(threads) < len(desired_titles):
            self.stdout.write(
                self.style.WARNING(
                    "Some development Tavern threads are missing. "
                    "Run seed_forum_data first to enable all "
                    "Action thread-link fixtures."
                )
            )

        return threads

    def clear_existing_seed_data(self):
        seeded_ids = list(
            Action.objects
            .filter(title__startswith=SEED_PREFIX)
            .values_list("id", flat=True)
        )

        if not seeded_ids:
            return

        Notification.objects.filter(
            source_type="Action",
            source_id__in=[str(pk) for pk in seeded_ids],
        ).delete()

        Action.objects.filter(
            id__in=seeded_ids,
        ).delete()

    def make_target(self, action, selectors):
        values = {}

        for field_name, reference_name in selectors.items():
            if field_name == "user":
                if reference_name not in self.users:
                    raise CommandError(
                        f"Unknown seed user: {reference_name}"
                    )

                values["user"] = self.users[reference_name]
                continue

            if field_name not in self.references:
                raise CommandError(
                    f"Unsupported Action target field: {field_name}"
                )

            try:
                values[field_name] = self.references[
                    field_name
                ][reference_name]
            except KeyError as error:
                raise CommandError(
                    f"Unknown {field_name}: {reference_name}"
                ) from error

        target = ActionTarget(
            action=action,
            **values,
        )

        target.full_clean()
        target.save()

        return target

    def make_assignment(
        self,
        action,
        user,
        *,
        status=ActionAssignment.Status.NOT_STARTED,
        active=True,
        completed_days_ago=1,
    ):
        opened_at = None
        completed_at = None

        if status == ActionAssignment.Status.OPENED:
            opened_at = self.now - timedelta(days=2)
            assigned_at = opened_at - timedelta(days=5)

        elif status == ActionAssignment.Status.COMPLETED:
            completed_at = self.now - timedelta(
                days=completed_days_ago,
            )
            opened_at = completed_at - timedelta(days=1)
            assigned_at = opened_at - timedelta(days=5)

        elif status == ActionAssignment.Status.NOT_STARTED:
            assigned_at = self.now - timedelta(days=2)

        else:
            raise CommandError(
                f"Unsupported assignment status: {status}"
            )

        assignment = ActionAssignment(
            action=action,
            user=user,
            status=status,
            is_active=active,
            opened_at=opened_at,
            completed_at=completed_at,
            unassigned_at=(
                None
                if active
                else self.now - timedelta(hours=4)
            ),
        )

        assignment.full_clean()
        assignment.save()

        ActionAssignment.objects.filter(
            pk=assignment.pk,
        ).update(
            assigned_at=assigned_at,
        )

        return assignment

    def create_action(
        self,
        title,
        *,
        due=None,
        targets=(),
        states=None,
        inactive=None,
        required=False,
        instructions=None,
        external_url="",
        threads=(),
        creator="suTest",
        completed_days_ago=1,
        allow_empty=False,
    ):
        states = states or {}
        inactive = inactive or {}

        action = Action(
            title=f"{SEED_PREFIX} {title}",
            instructions=(
                FILLER_TEXT
                if instructions is None
                else instructions
            ),
            external_url=external_url,
            deadline=(
                self.now + due
                if due is not None
                else None
            ),
            is_required=required,
            created_by=self.users[creator],
        )

        action.full_clean()
        action.save()

        for selectors in targets:
            self.make_target(action, selectors)

        linked_threads = [
            self.threads[title]
            for title in threads
            if title in self.threads
        ]

        if linked_threads:
            action.linked_threads.add(*linked_threads)

        resolved_user_ids = resolve_action_targets(action)

        if targets and not resolved_user_ids and not allow_empty:
            raise CommandError(
                f"No active members matched {action.title}."
            )

        resolved_usernames = set(
            User.objects
            .filter(pk__in=resolved_user_ids)
            .values_list("username", flat=True)
        )

        unknown_states = (
            set(states) - resolved_usernames
        )

        if unknown_states:
            raise CommandError(
                f"Assignment state references users not selected "
                f"by {action.title}: "
                + ", ".join(sorted(unknown_states))
            )

        for user_id in sorted(resolved_user_ids):
            user = User.objects.get(pk=user_id)

            self.make_assignment(
                action,
                user,
                status=states.get(
                    user.username,
                    ActionAssignment.Status.NOT_STARTED,
                ),
                completed_days_ago=completed_days_ago,
            )

        for username, status in inactive.items():
            if username not in self.users:
                raise CommandError(
                    f"Unknown inactive assignment user: {username}"
                )

            if self.users[username].pk in resolved_user_ids:
                raise CommandError(
                    f"Inactive assignment still matches "
                    f"the targets for {action.title}: {username}"
                )

            self.make_assignment(
                action,
                self.users[username],
                status=status,
                active=False,
                completed_days_ago=completed_days_ago,
            )

        self.created_actions.append(action)
        return action

    def create_personal_actions(self):
        td = timedelta
        status = ActionAssignment.Status

        individual = ({"user": "testuser01"},)

        self.create_action(
            "Overdue - Required - Not Started",
            due=td(days=-4),
            targets=individual,
            required=True,
        )

        self.create_action(
            "Overdue - Optional - Opened",
            due=td(days=-1),
            targets=individual,
            states={"testuser01": status.OPENED},
        )

        self.create_action(
            "Due Today - Required",
            due=td(hours=3),
            targets=individual,
            required=True,
        )

        self.create_action(
            "Due Tomorrow - Required",
            due=td(days=1),
            targets=individual,
            required=True,
        )

        self.create_action(
            "Due in Three Days",
            due=td(days=3),
            targets=individual,
        )

        self.create_action(
            "Due Next Week",
            due=td(days=7),
            targets=individual,
        )

        self.create_action(
            "Due in Thirty Days",
            due=td(days=30),
            targets=individual,
            required=True,
        )

        self.create_action(
            "No Deadline - Required",
            targets=individual,
            required=True,
        )

        self.create_action(
            "No Deadline - Optional",
            targets=individual,
        )

        self.create_action(
            "Completed - Recent",
            due=td(days=-2),
            targets=individual,
            states={"testuser01": status.COMPLETED},
            required=True,
        )

        self.create_action(
            "Completed - Older",
            due=td(days=-25),
            targets=individual,
            states={"testuser01": status.COMPLETED},
            completed_days_ago=30,
        )

        self.create_action(
            "Completed - No Deadline",
            targets=individual,
            states={"testuser01": status.COMPLETED},
        )

        long_title = (
            "Long Title - "
            + "Lorem ipsum dolor sit amet. " * 8
        )[:200 - len(SEED_PREFIX) - 1]

        self.create_action(
            long_title,
            due=td(days=5),
            targets=individual,
        )

        self.create_action(
            "Long Instructions",
            due=td(days=6),
            targets=individual,
            instructions=FILLER_TEXT * 12,
        )

        self.create_action(
            "External URL",
            due=td(days=8),
            targets=individual,
            external_url="https://example.com/action-instructions",
        )

        self.create_action(
            "Linked Tavern - One Thread",
            due=td(days=9),
            targets=individual,
            threads=("Prepping Tents",),
        )

        self.create_action(
            "Linked Tavern - Multiple Threads",
            due=td(days=10),
            targets=individual,
            threads=(
                "Prepping Tents",
                "Camp Setup",
                "Carpool Planning",
            ),
        )

    def create_targeted_actions(self):
        td = timedelta
        status = ActionAssignment.Status

        self.create_action(
            "Individual - Member Two Only",
            due=td(days=2),
            targets=({"user": "testuser02"},),
        )

        self.create_action(
            "Individual - Member Three Only",
            due=td(days=3),
            targets=({"user": "testuser04"},),
        )

        self.create_action(
            "Individual - Member Four Only",
            due=td(days=4),
            targets=({"user": "testuser05"},),
        )

        self.create_action(
            "Multiple Individual Targets",
            due=td(days=5),
            required=True,
            targets=(
                {"user": "testuser01"},
                {"user": "testuser02"},
                {"user": "testuser04"},
            ),
        )

        self.create_action(
            "Community Group - Test Custom Group",
            due=td(days=6),
            targets=(
                {"community_group": TEST_GROUP_NAME},
            ),
        )

        self.create_action(
            "Chapter - Fyr Draca",
            due=td(days=7),
            targets=(
                {"chapter": "Fyr Draca Chapter"},
            ),
        )

        self.create_action(
            "Chapter - Seattle",
            due=td(days=8),
            targets=(
                {"chapter": "Seattle Chapter"},
            ),
        )

        self.create_action(
            "Citizenship - Active Citizens",
            due=td(days=9),
            targets=(
                {"citizenship_class": "Active Citizen"},
            ),
        )

        self.create_action(
            "Social Rank - Godi",
            due=td(days=10),
            targets=(
                {"social_rank": "Godi"},
            ),
        )

        self.create_action(
            "Household - Kraken",
            due=td(days=11),
            targets=(
                {"household": "House Kraken"},
            ),
        )

        self.create_action(
            "Governance - Godi Council",
            due=td(days=12),
            targets=(
                {"governance_body": "Godi Council"},
            ),
        )

        self.create_action(
            "Order - Air",
            due=td(days=13),
            targets=(
                {"order": "Order of Air"},
            ),
        )

        self.create_action(
            "Order Rank - Gesallen",
            due=td(days=14),
            targets=(
                {"order_rank": "Gesallen"},
            ),
        )

        self.create_action(
            "Office - Lawspeaker",
            due=td(days=15),
            targets=(
                {"office": "Lawspeaker"},
            ),
        )

        self.create_action(
            "Household Leadership - Leading Jarl",
            due=td(days=16),
            targets=(
                {
                    "household_leadership_type": "Leading Jarl",
                },
            ),
        )

        self.create_action(
            "Intersection - Group and Chapter",
            due=td(days=17),
            targets=(
                {
                    "community_group": TEST_GROUP_NAME,
                    "chapter": "Fyr Draca Chapter",
                },
            ),
        )

        self.create_action(
            "Intersection - Office and Chapter",
            due=td(days=18),
            targets=(
                {
                    "office": "Lawspeaker",
                    "chapter": "Fyr Draca Chapter",
                },
            ),
        )

        self.create_action(
            "Intersection - Order and Rank",
            due=td(days=19),
            targets=(
                {
                    "order": "Order of Air",
                    "order_rank": "Larling",
                },
            ),
        )

        self.create_action(
            "Union - Group or Household",
            due=td(days=20),
            targets=(
                {"community_group": TEST_GROUP_NAME},
                {"household": "House Kraken"},
            ),
        )

        self.create_action(
            "Union - Individual or Group",
            due=td(days=21),
            required=True,
            targets=(
                {"user": "testuser02"},
                {"community_group": TEST_GROUP_NAME},
            ),
        )

    def create_lifecycle_actions(self):
        td = timedelta
        status = ActionAssignment.Status

        self.create_action(
            "Previously Removed - Opened",
            due=td(days=3),
            inactive={
                "testuser01": status.OPENED,
            },
        )

        self.create_action(
            "Previously Removed - Completed",
            inactive={
                "testuser01": status.COMPLETED,
            },
        )

        self.create_action(
            "Mixed Status - Community Group",
            due=td(days=5),
            required=True,
            targets=(
                {"community_group": TEST_GROUP_NAME},
            ),
            states={
                "testuser01": status.COMPLETED,
                "testuser16": status.OPENED,
            },
        )

        self.create_action(
            "Mixed Status - Individual Targets",
            due=td(days=6),
            targets=(
                {"user": "testuser01"},
                {"user": "testuser02"},
                {"user": "testuser04"},
            ),
            states={
                "testuser02": status.OPENED,
                "testuser04": status.COMPLETED,
            },
        )

    def create_edge_case_actions(self):
        td = timedelta

        self.create_action(
            "No Targets - Management Only",
            instructions=FILLER_TEXT,
        )

        self.create_action(
            "Pending Account - No Assignment",
            targets=({"user": "testuser03"},),
            allow_empty=True,
        )

        self.create_action(
            "Suspended Account - No Assignment",
            targets=({"user": "testuser06"},),
            allow_empty=True,
        )

        self.create_action(
            "Disabled Account - No Assignment",
            targets=({"user": "testuser09"},),
            allow_empty=True,
        )

        self.create_action(
            "Same Deadline - First",
            due=td(days=4),
            targets=({"user": "testuser02"},),
        )

        self.create_action(
            "Same Deadline - Second",
            due=td(days=4),
            targets=({"user": "testuser02"},),
        )
