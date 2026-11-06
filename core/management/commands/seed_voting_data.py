from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import AccountStatus
from notifications.models import Notification
from organization.models import (
    Chapter,
    CitizenshipClass,
    CommunityGroup,
    GovernanceBody,
    GroupMembership,
    Household,
    HouseholdLeadershipType,
    Office,
    Order,
    OrderRank,
    SocialRank,
)
from voting.models import (
    Vote,
    VoteComment,
    VoteEligibilityTarget,
    VoteEligibleUser,
    VoteOption,
    VoteResponse,
)
from voting.services import (
    calculate_vote_result,
    close_vote,
    open_vote,
    submit_vote_comment,
    submit_vote_response,
)


User = get_user_model()
SEED_PREFIX = "[DEV VOTE]"
TEST_GROUP_NAME = "Test Custom Group"

FILLER_TEXT = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris."
)

VOTING_PERMISSIONS = (
    "view_vote",
    "add_vote",
    "change_vote",
    "delete_vote",
)

PERMISSION_TEST_USERS = {
    "testuser40": VOTING_PERMISSIONS,
    "testuser41": ("view_vote",),
    "testuser42": ("add_vote",),
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
    "community_group": (CommunityGroup, (TEST_GROUP_NAME,)),
    "chapter": (Chapter, ("Fyr Draca Chapter", "Seattle Chapter")),
    "citizenship_class": (CitizenshipClass, ("Active Citizen",)),
    "social_rank": (SocialRank, ("Godi",)),
    "household": (Household, ("House Kraken", "House Hvit Hrafn")),
    "governance_body": (GovernanceBody, ("Godi Council",)),
    "order": (Order, ("Order of Air",)),
    "order_rank": (OrderRank, ("Larling",)),
    "office": (Office, ("Lawspeaker",)),
    "household_leadership_type": (
        HouseholdLeadershipType,
        ("Leading Jarl",),
    ),
}


class Command(BaseCommand):
    help = (
        "Create repeatable development votes for member ballots, "
        "eligibility, anonymity, results, and management testing."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_voting_data can only run when DEBUG is enabled."
            )

        self.now = timezone.now()
        self.users = self.get_required_users()
        self.references = self.get_required_references()
        self.validate_group_membership()
        self.configure_voting_permissions()
        self.clear_existing_seed_data()

        self.created_votes = []
        self.create_draft_votes()
        self.create_open_votes()
        self.create_closed_votes()

        seeded_votes = Vote.objects.filter(title__startswith=SEED_PREFIX)
        eligibility = VoteEligibleUser.objects.filter(vote__in=seeded_votes)
        responses = VoteResponse.objects.filter(option__vote__in=seeded_votes)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("Voting development data seeded successfully.")
        )
        for status, label in (
            (Vote.Status.DRAFT, "Draft votes"),
            (Vote.Status.OPEN, "Open votes"),
            (Vote.Status.CLOSED, "Closed votes"),
        ):
            self.stdout.write(
                f"{label}: {seeded_votes.filter(status=status).count()}"
            )
        self.stdout.write(f"Total votes: {seeded_votes.count()}")
        self.stdout.write(
            "Eligibility targets: "
            f"{VoteEligibilityTarget.objects.filter(vote__in=seeded_votes).count()}"
        )
        self.stdout.write(f"Frozen eligible voters: {eligibility.count()}")
        self.stdout.write(
            "Voters who have responded: "
            f"{eligibility.filter(has_responded=True).count()}"
        )
        self.stdout.write(f"Ballot responses: {responses.count()}")
        self.stdout.write(
            "Anonymous responses: "
            f"{responses.filter(eligibility__isnull=True).count()}"
        )
        self.stdout.write(
            "Reviewer comments: "
            f"{VoteComment.objects.filter(vote__in=seeded_votes).count()}"
        )
        self.stdout.write("")
        self.stdout.write("Useful accounts:")
        self.stdout.write("  suTest     - superuser and vote creator")
        self.stdout.write("  testuser01 - primary voter; open and completed ballots")
        self.stdout.write("  testuser02 - alternate voter and group comparison")
        self.stdout.write("  testuser16 - organizational group membership")
        self.stdout.write("  testuser40 - full Voting management permissions")
        self.stdout.write("  testuser41 - view-only Voting management")
        self.stdout.write("  testuser42 - add-only Voting permission")
        self.stdout.write("  testuser03 - pending account")
        self.stdout.write("  testuser06 - suspended account")
        self.stdout.write("  testuser09 - disabled account")
        self.stdout.write("Run this command again to replace seeded Votes.")

    def get_required_users(self):
        users = {}

        for username, status in REQUIRED_USERS.items():
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist as error:
                raise CommandError(
                    f"Required user {username} does not exist. "
                    "Run seed_dev_data first."
                ) from error

            if user.account_status != status:
                raise CommandError(
                    f"{username} has status {user.account_status}, "
                    f"but expected {status}. Run seed_dev_data first."
                )

            if status == AccountStatus.MEMBER and not user.is_active:
                raise CommandError(f"{username} must be active.")

            users[username] = user

        if not users["suTest"].is_superuser:
            raise CommandError(
                "suTest must be a superuser. Run seed_dev_data first."
            )

        return users

    def get_required_references(self):
        references = {}

        for field, (model, names) in REFERENCE_MODELS.items():
            references[field] = {}
            for name in names:
                try:
                    references[field][name] = model.objects.get(name=name)
                except model.DoesNotExist as error:
                    raise CommandError(
                        f"Required {field} '{name}' does not exist. "
                        "Run seed_dev_data first."
                    ) from error

        return references

    def validate_group_membership(self):
        group = self.references["community_group"][TEST_GROUP_NAME]

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

    def configure_voting_permissions(self):
        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="voting",
                codename__in=VOTING_PERMISSIONS,
            )
        }

        missing = set(VOTING_PERMISSIONS) - set(permissions)
        if missing:
            raise CommandError(
                "Missing Voting permissions: "
                + ", ".join(sorted(missing))
                + ". Run migrations first."
            )

        for username, codenames in PERMISSION_TEST_USERS.items():
            user = self.users[username]
            user.user_permissions.remove(*permissions.values())
            user.user_permissions.add(
                *(permissions[codename] for codename in codenames)
            )

    def clear_existing_seed_data(self):
        seeded_ids = list(
            Vote.objects.filter(title__startswith=SEED_PREFIX)
            .values_list("id", flat=True)
        )

        if not seeded_ids:
            return

        Notification.objects.filter(
            source_type="Vote",
            source_id__in=[str(vote_id) for vote_id in seeded_ids],
        ).delete()

        VoteResponse.objects.filter(option__vote_id__in=seeded_ids).delete()
        Vote.objects.filter(id__in=seeded_ids).delete()

    def make_target(self, vote, selectors):
        values = {}

        for field, name in selectors.items():
            if field == "user":
                values["user"] = self.users[name]
            elif field in self.references:
                values[field] = self.references[field][name]
            else:
                raise CommandError(f"Unsupported Voting target field: {field}")

        target = VoteEligibilityTarget(vote=vote, **values)
        target.full_clean()
        target.save()
        return target

    def make_vote(
        self,
        name,
        *,
        status=Vote.Status.DRAFT,
        options=("Yes", "No"),
        targets=(),
        responses=(),
        comments=(),
        anonymous=False,
        approval_rule=Vote.ApprovalRule.SIMPLE_MAJORITY,
        requires_quorum=False,
        quorum=(2, 5),
        requires_all_responses=False,
        opens_in_days=-3,
        closes_in_days=7,
        expired=False,
        long_description=False,
        created_by="suTest",
        expected_reason=None,
    ):
        if status == Vote.Status.DRAFT and (responses or comments or expired):
            raise CommandError("Draft fixtures cannot contain responses or comments.")

        if expired and status != Vote.Status.OPEN:
            raise CommandError("Only OPEN fixtures can be marked expired.")

        title = f"{SEED_PREFIX} {name}"
        vote = Vote(
            title=title,
            description=(FILLER_TEXT + "\n\n") * 6 if long_description else FILLER_TEXT,
            status=Vote.Status.DRAFT,
            approval_rule=approval_rule,
            is_anonymous=anonymous,
            requires_quorum=requires_quorum,
            quorum_numerator=quorum[0],
            quorum_denominator=quorum[1],
            requires_all_responses=requires_all_responses,
            opens_at=(
                self.now + timedelta(days=opens_in_days)
                if opens_in_days is not None else None
            ),
            closes_at=(
                self.now + timedelta(days=closes_in_days)
                if closes_in_days is not None else None
            ),
            created_by=self.users[created_by],
        )
        vote.full_clean()
        vote.save()

        for position, label in enumerate(options):
            option = VoteOption(vote=vote, label=label, sort_order=position)
            option.full_clean()
            option.save()

        for selectors in targets:
            self.make_target(vote, selectors)

        if status == Vote.Status.DRAFT:
            self.created_votes.append(vote)
            return vote

        if not options or not targets:
            raise CommandError(f"Open fixture {name} needs options and targets.")

        vote = open_vote(vote)

        for username, body in comments:
            submit_vote_comment(vote, self.users[username], body)

        option_records = list(vote.options.all())
        for username, option_index in responses:
            if option_index < 0 or option_index >= len(option_records):
                raise CommandError(f"Invalid option index in {title}.")
            submit_vote_response(
                vote,
                self.users[username],
                option_records[option_index],
            )

        if status == Vote.Status.CLOSED:
            close_vote(vote)
            self.backdate_closed_vote(vote)
            self.remove_vote_notifications(vote)

        elif expired:
            self.backdate_expired_vote(vote)
            self.remove_vote_notifications(vote)

        else:
            Vote.objects.filter(pk=vote.pk).update(
                opened_at=self.now - timedelta(days=2),
                created_at=self.now - timedelta(days=4),
            )

        vote.refresh_from_db()
        vote.full_clean()

        if expected_reason is not None:
            actual_reason = calculate_vote_result(vote)["reason"]
            if actual_reason != expected_reason:
                raise CommandError(
                    f"Unexpected result for {title}: "
                    f"'{actual_reason}', expected '{expected_reason}'."
                )

        self.created_votes.append(vote)
        return vote

    def remove_vote_notifications(self, vote):
        Notification.objects.filter(
            source_type="Vote",
            source_id=str(vote.pk),
        ).delete()

    def backdate_closed_vote(self, vote):
        created_at = self.now - timedelta(days=16)
        opened_at = self.now - timedelta(days=14)
        response_at = self.now - timedelta(days=8)
        closed_at = self.now - timedelta(days=3)

        Vote.objects.filter(pk=vote.pk).update(
            created_at=created_at,
            opens_at=created_at,
            opened_at=opened_at,
            closes_at=closed_at,
            closed_at=closed_at,
        )
        VoteEligibleUser.objects.filter(vote=vote).update(added_at=opened_at)
        VoteResponse.objects.filter(
            option__vote=vote,
            eligibility__isnull=False,
        ).update(
            submitted_at=response_at,
            updated_at=response_at,
        )
        VoteComment.objects.filter(vote=vote).update(
            created_at=response_at,
            updated_at=response_at,
        )

    def backdate_expired_vote(self, vote):
        Vote.objects.filter(pk=vote.pk).update(
            created_at=self.now - timedelta(days=12),
            opens_at=self.now - timedelta(days=11),
            opened_at=self.now - timedelta(days=10),
            closes_at=self.now - timedelta(days=1),
        )
        VoteEligibleUser.objects.filter(vote=vote).update(
            added_at=self.now - timedelta(days=10),
        )

    def individual_targets(self, *usernames):
        return tuple({"user": username} for username in usernames)

    def create_draft_votes(self):
        self.make_vote(
            "Draft - Empty Configuration", options=(), targets=(),
        )
        self.make_vote(
            "Draft - Ready to Open",
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Draft - Future Scheduled Open",
            targets=({"community_group": TEST_GROUP_NAME},),
            opens_in_days=2, closes_in_days=10,
        )
        self.make_vote(
            "Draft - Anonymous Ballot",
            anonymous=True,
            targets=({"community_group": TEST_GROUP_NAME},),
        )
        self.make_vote(
            "Draft - No Eligible Members",
            targets=self.individual_targets("testuser03", "testuser06"),
        )
        self.make_vote(
            "Draft - Multiple Options and Targets",
            options=("Option A", "Option B", "Option C", "Option D"),
            targets=(
                {"user": "testuser01"},
                {"community_group": TEST_GROUP_NAME},
                {"chapter": "Seattle Chapter"},
            ),
        )
        self.make_vote(
            "Draft - Long Title and Description: " + "Lorem ipsum " * 8,
            long_description=True,
            targets=self.individual_targets("testuser01"),
        )
        self.make_vote(
            "Draft - All Responses Required",
            requires_all_responses=True,
            requires_quorum=True,
            quorum=(2, 3),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
        )

    def create_open_votes(self):
        self.make_vote(
            "Individual - Awaiting Response",
            status=Vote.Status.OPEN,
            targets=self.individual_targets("testuser01"),
            closes_in_days=2,
        )
        self.make_vote(
            "Individual - Identified Response",
            status=Vote.Status.OPEN,
            targets=self.individual_targets("testuser01"),
            responses=(("testuser01", 0),),
        )
        self.make_vote(
            "Identified - Changeable Ballot",
            status=Vote.Status.OPEN,
            targets=self.individual_targets("testuser01", "testuser02"),
            responses=(("testuser01", 1),),
            comments=(("testuser01", FILLER_TEXT),),
        )
        self.make_vote(
            "Anonymous - Awaiting Response",
            status=Vote.Status.OPEN,
            anonymous=True,
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Anonymous - Member 01 Already Responded",
            status=Vote.Status.OPEN,
            anonymous=True,
            targets=self.individual_targets("testuser01", "testuser02"),
            responses=(("testuser01", 0),),
            comments=(("testuser01", FILLER_TEXT),),
        )
        self.make_vote(
            "Custom Group - Open",
            status=Vote.Status.OPEN,
            targets=({"community_group": TEST_GROUP_NAME},),
            responses=(("testuser01", 0), ("testuser16", 1)),
        )
        self.make_vote(
            "Chapter - Fyr Draca",
            status=Vote.Status.OPEN,
            targets=({"chapter": "Fyr Draca Chapter"},),
        )
        self.make_vote(
            "Household - Kraken",
            status=Vote.Status.OPEN,
            targets=({"household": "House Kraken"},),
        )
        self.make_vote(
            "Citizenship - Active Citizen",
            status=Vote.Status.OPEN,
            targets=({"citizenship_class": "Active Citizen"},),
        )
        self.make_vote(
            "Social Rank - Godi",
            status=Vote.Status.OPEN,
            targets=({"social_rank": "Godi"},),
        )
        self.make_vote(
            "Order - Air",
            status=Vote.Status.OPEN,
            targets=({"order": "Order of Air"},),
        )
        self.make_vote(
            "Order Rank - Larling",
            status=Vote.Status.OPEN,
            targets=({"order_rank": "Larling"},),
        )
        self.make_vote(
            "Office - Lawspeaker",
            status=Vote.Status.OPEN,
            targets=({"office": "Lawspeaker"},),
        )
        self.make_vote(
            "Governance - Godi Council",
            status=Vote.Status.OPEN,
            targets=({"governance_body": "Godi Council"},),
        )
        self.make_vote(
            "Household Leadership - Leading Jarl",
            status=Vote.Status.OPEN,
            targets=({"household_leadership_type": "Leading Jarl"},),
        )
        self.make_vote(
            "Intersection - Group and Chapter",
            status=Vote.Status.OPEN,
            targets=({
                "community_group": TEST_GROUP_NAME,
                "chapter": "Fyr Draca Chapter",
            },),
        )
        self.make_vote(
            "Intersection - Order and Rank",
            status=Vote.Status.OPEN,
            targets=({"order": "Order of Air", "order_rank": "Larling"},),
        )
        self.make_vote(
            "Union - Individual and Group",
            status=Vote.Status.OPEN,
            targets=(
                {"user": "testuser02"},
                {"community_group": TEST_GROUP_NAME},
            ),
        )
        self.make_vote(
            "Quorum - Not Met",
            status=Vote.Status.OPEN,
            requires_quorum=True, quorum=(3, 4),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04", "testuser05"
            ),
            responses=(("testuser01", 0),),
            expected_reason="Quorum was not met.",
        )
        self.make_vote(
            "Quorum - Met",
            status=Vote.Status.OPEN,
            requires_quorum=True, quorum=(3, 4),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04", "testuser05"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 0),
                ("testuser04", 1),
            ),
            expected_reason="An option received a simple majority.",
        )
        self.make_vote(
            "Unanimous - Split Responses",
            status=Vote.Status.OPEN,
            approval_rule=Vote.ApprovalRule.UNANIMOUS,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 1),
                ("testuser04", 0),
            ),
            expected_reason="The vote did not reach unanimous agreement.",
        )
        self.make_vote(
            "All Responses Required - Still Pending",
            status=Vote.Status.OPEN,
            requires_all_responses=True,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(("testuser01", 0),),
            expected_reason="All required responses have not been received.",
        )
        self.make_vote(
            "Three Options - Tie",
            status=Vote.Status.OPEN,
            options=("Option A", "Option B", "Option C"),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(("testuser01", 0), ("testuser02", 1)),
            expected_reason="The vote ended in a tie.",
        )
        self.make_vote(
            "No Deadline - Open",
            status=Vote.Status.OPEN,
            closes_in_days=None,
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Expired - Awaiting Manual Closure",
            status=Vote.Status.OPEN,
            expired=True,
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Ineligible Accounts Excluded",
            status=Vote.Status.OPEN,
            targets=self.individual_targets(
                "testuser03", "testuser06", "testuser09", "testuser01"
            ),
        )
        self.make_vote(
            "Created by Action Manager",
            status=Vote.Status.OPEN,
            created_by="testuser40",
            targets=self.individual_targets("testuser02"),
        )

    def create_closed_votes(self):
        self.make_vote(
            "Closed - Majority Approved",
            status=Vote.Status.CLOSED,
            requires_quorum=True, quorum=(2, 3),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 0),
                ("testuser04", 1),
            ),
            expected_reason="An option received a simple majority.",
        )
        self.make_vote(
            "Closed - Tied Vote",
            status=Vote.Status.CLOSED,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04", "testuser05"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 0),
                ("testuser04", 1),
                ("testuser05", 1),
            ),
            expected_reason="The vote ended in a tie.",
        )
        self.make_vote(
            "Closed - Quorum Not Met",
            status=Vote.Status.CLOSED,
            requires_quorum=True, quorum=(3, 4),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04", "testuser05"
            ),
            responses=(("testuser01", 0),),
            expected_reason="Quorum was not met.",
        )
        self.make_vote(
            "Closed - Unanimous Approved",
            status=Vote.Status.CLOSED,
            approval_rule=Vote.ApprovalRule.UNANIMOUS,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 0),
                ("testuser04", 0),
            ),
            expected_reason="The vote reached unanimous agreement.",
        )
        self.make_vote(
            "Closed - Unanimous Rejected",
            status=Vote.Status.CLOSED,
            approval_rule=Vote.ApprovalRule.UNANIMOUS,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 0),
                ("testuser04", 1),
            ),
            expected_reason="The vote did not reach unanimous agreement.",
        )
        self.make_vote(
            "Closed - Anonymous Results",
            status=Vote.Status.CLOSED,
            anonymous=True,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 0),
                ("testuser04", 1),
            ),
            expected_reason="An option received a simple majority.",
        )
        self.make_vote(
            "Closed - All Responses Received",
            status=Vote.Status.CLOSED,
            requires_all_responses=True,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(
                ("testuser01", 0),
                ("testuser02", 0),
                ("testuser04", 1),
            ),
            expected_reason="An option received a simple majority.",
        )
        self.make_vote(
            "Closed - Identified With Reviewer Comment",
            status=Vote.Status.CLOSED,
            targets=self.individual_targets("testuser01", "testuser02"),
            responses=(("testuser01", 0), ("testuser02", 0)),
            comments=(("testuser01", FILLER_TEXT),),
            expected_reason="An option received a simple majority.",
        )
        self.make_vote(
            "Closed - No Responses",
            status=Vote.Status.CLOSED,
            targets=self.individual_targets("testuser01", "testuser02"),
            expected_reason="No responses were submitted.",
        )
