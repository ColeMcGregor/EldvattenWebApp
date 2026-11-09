
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
    "The proposal concerns the society's shared equipment, educational programs, "
    "or administration. Review the scope and expected cost before responding. "
    "The organizer will record the final decision in the meeting notes."
)

PROPOSAL_DETAILS = {
    "Approve Replacement Tent Lines": (
        "The camping team requests funds to replace worn guy lines "
        "before the next public encampment."
    ),
    "Schedule the Winter Textile Workshop": (
        "Confirm the proposed winter workshop date so instructors "
        "can reserve the teaching room."
    ),
    "Anonymous Feedback on the Gathering Program": (
        "Choose whether to keep the current annual gathering format. "
        "Individual ballot choices must remain private."
    ),
    "Choose a Location for the Spring Symposium": (
        "Choose one of four potential sites for the spring educational "
        "symposium. The organizing team will verify availability after the vote."
    ),
    "Approve the Required Equipment Transfer Record": (
        "Approve the final transfer record for shared equipment. "
        "Every eligible reviewer must respond."
    ),
    "Accept Custody of the Loaned Display Kit": (
        "Confirm that the named volunteer will accept responsibility "
        "for the display kit until it is returned."
    ),
    "Confirm the Workshop Supply Request": (
        "Authorize the list of yarn, needles, and practice materials "
        "needed for the next class."
    ),
    "Select the Next Shared Equipment Purchase": (
        "Decide whether to buy replacement display supports "
        "using the remaining equipment budget."
    ),
    "Private Ballot on Camp Quiet Hours": (
        "Vote on the proposed camp quiet-hours policy without "
        "associating a response with a named voter."
    ),
    "Private Ballot on Member Orientation Format": (
        "Choose whether new-member orientation should include "
        "a separate practical workshop."
    ),
    "Buy New Tablet-Weaving Cards": (
        "The textile group requests additional weaving tablets "
        "for introductory workshops."
    ),
    "Set the Fyr Draca Winter Meeting Schedule": (
        "Approve the winter meeting schedule for the Fyr Draca chapter."
    ),
    "Replace House Kraken Tent Pegs": (
        "Approve replacement of damaged tent pegs "
        "from the household inventory."
    ),
    "Approve the Annual Community Program": (
        "Approve the proposed annual schedule of research, "
        "public education, and society gatherings."
    ),
    "Review the Godi Council Meeting Format": (
        "Consider a revised format for the council's "
        "recordkeeping and meeting agenda."
    ),
    "Plan the Order of Air Research Display": (
        "Authorize preparation of a small research display "
        "by Order of Air members."
    ),
    "Schedule Larling Skills Practice": (
        "Select the next skills-practice session "
        "for members holding Larling rank."
    ),
    "Approve the Lawspeaker Document Review Schedule": (
        "Review the proposed schedule for checking "
        "and publishing society documents."
    ),
    "Approve the Council Record Archive Plan": (
        "Decide whether to organize older council records "
        "in the revised archive structure."
    ),
    "Choose a Household Inventory Process": (
        "Choose a standard method for recording "
        "and signing out household equipment."
    ),
    "Fund the Chapter Textile Demonstration": (
        "Approve materials for the chapter textile demonstration "
        "led by the working group."
    ),
    "Select the Air Order Apprentice Workshop": (
        "Choose whether the upcoming training session should "
        "focus on practical research methods."
    ),
    "Approve a Shared Loom Purchase": (
        "Approve purchase of one portable loom for use "
        "by the designated members and working group."
    ),
    "Fund Replacement Camp Lanterns": (
        "The camp crew requests replacement lanterns. "
        "A minimum participation threshold applies."
    ),
    "Approve Public Handout Printing": (
        "Approve printing a small set of public education "
        "handouts for the next open event."
    ),
    "Admit a New Society Citizen": (
        "Review a fictional citizenship application. "
        "The decision requires unanimous agreement."
    ),
    "Confirm the Revision to the Chapter Rules": (
        "Review the proposed chapter rule revision. "
        "Each eligible citizen must submit a response."
    ),
    "Choose the Spring Gathering Theme": (
        "Choose between maritime crafts, textile traditions, "
        "and trade routes for the spring event."
    ),
    "Select Future Research Topics": (
        "Choose whether the proposed research topics "
        "should enter the next planning cycle."
    ),
    "Approve the September Storage Lease": (
        "Review the proposed storage lease that reached "
        "its deadline without administrative closure."
    ),
    "Approve the Volunteer Safety Briefing": (
        "Approve the standard safety briefing for volunteers "
        "who help with public events."
    ),
    "Approve the Equipment Checkout Form": (
        "Approve the revised form for recording loans "
        "of shared equipment."
    ),
    "Purchase Two Folding Display Tables": (
        "Authorize two folding display tables "
        "for public education events."
    ),
    "Choose the Autumn Workshop Venue": (
        "Select the venue for the autumn workshop "
        "from the two proposed options."
    ),
    "Fund a Second Public Demonstration Tent": (
        "Consider funding a second teaching tent. "
        "The proposal has a required quorum."
    ),
    "Approve a New Citizenship Application": (
        "Review a fictional application for society citizenship; "
        "unanimous approval is required."
    ),
    "Approve a Proposed Citizenship Application": (
        "Review a separate fictional citizenship application; "
        "unanimous approval is required."
    ),
    "Select the Annual Member Gathering Format": (
        "Choose the gathering format using a private ballot."
    ),
    "Approve the Final Inventory Sign-Off": (
        "Approve the final inventory record after all "
        "assigned reviewers have responded."
    ),
    "Adopt the Revised Workshop Calendar": (
        "Approve the revised workshop dates after "
        "reviewing the member comments."
    ),
    "Extend the Shared Tool Storage Hours": (
        "Consider extending weekly access hours "
        "for the shared equipment room."
    ),
}

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
            description=(
                (PROPOSAL_DETAILS.get(name, FILLER_TEXT) + "\n\n") * 6
                if long_description else PROPOSAL_DETAILS.get(name, FILLER_TEXT)
            ),
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
            "Proposal Under Preparation", options=(), targets=(),
        )
        self.make_vote(
            "Approve Replacement Tent Lines",
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Schedule the Winter Textile Workshop",
            targets=({"community_group": TEST_GROUP_NAME},),
            opens_in_days=2, closes_in_days=10,
        )
        self.make_vote(
            "Anonymous Feedback on the Gathering Program",
            anonymous=True,
            targets=({"community_group": TEST_GROUP_NAME},),
        )
        self.make_vote(
            "Review the Suspended Application Request",
            targets=self.individual_targets("testuser03", "testuser06"),
        )
        self.make_vote(
            "Choose a Location for the Spring Symposium",
            options=(
                "Riverside Hall",
                "North Meadow",
                "Harborview Center",
                "Willowbank House",
            ),
            targets=(
                {"user": "testuser01"},
                {"community_group": TEST_GROUP_NAME},
                {"chapter": "Seattle Chapter"},
            ),
        )
        self.make_vote(
            "Review the Long-Term Equipment and Education Plan",
            long_description=True,
            targets=self.individual_targets("testuser01"),
        )
        self.make_vote(
            "Approve the Required Equipment Transfer Record",
            requires_all_responses=True,
            requires_quorum=True,
            quorum=(2, 3),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
        )

    def create_open_votes(self):
        self.make_vote(
            "Accept Custody of the Loaned Display Kit",
            status=Vote.Status.OPEN,
            targets=self.individual_targets("testuser01"),
            closes_in_days=2,
        )
        self.make_vote(
            "Confirm the Workshop Supply Request",
            status=Vote.Status.OPEN,
            targets=self.individual_targets("testuser01"),
            responses=(("testuser01", 0),),
        )
        self.make_vote(
            "Select the Next Shared Equipment Purchase",
            status=Vote.Status.OPEN,
            targets=self.individual_targets("testuser01", "testuser02"),
            responses=(("testuser01", 1),),
            comments=((
                "testuser01",
                "The proposed purchase may conflict with our existing "
                "equipment plan. Can we review the budget first?",
            ),),
        )
        self.make_vote(
            "Private Ballot on Camp Quiet Hours",
            status=Vote.Status.OPEN,
            anonymous=True,
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Private Ballot on Member Orientation Format",
            status=Vote.Status.OPEN,
            anonymous=True,
            targets=self.individual_targets("testuser01", "testuser02"),
            responses=(("testuser01", 0),),
            comments=((
                "testuser01",
                "A practical introduction could help new members "
                "prepare for their first camp.",
            ),),
        )
        self.make_vote(
            "Buy New Tablet-Weaving Cards",
            status=Vote.Status.OPEN,
            targets=({"community_group": TEST_GROUP_NAME},),
            responses=(("testuser01", 0), ("testuser16", 1)),
        )
        self.make_vote(
            "Set the Fyr Draca Winter Meeting Schedule",
            status=Vote.Status.OPEN,
            targets=({"chapter": "Fyr Draca Chapter"},),
        )
        self.make_vote(
            "Replace House Kraken Tent Pegs",
            status=Vote.Status.OPEN,
            targets=({"household": "House Kraken"},),
        )
        self.make_vote(
            "Approve the Annual Community Program",
            status=Vote.Status.OPEN,
            targets=({"citizenship_class": "Active Citizen"},),
        )
        self.make_vote(
            "Review the Godi Council Meeting Format",
            status=Vote.Status.OPEN,
            targets=({"social_rank": "Godi"},),
        )
        self.make_vote(
            "Plan the Order of Air Research Display",
            status=Vote.Status.OPEN,
            targets=({"order": "Order of Air"},),
        )
        self.make_vote(
            "Schedule Larling Skills Practice",
            status=Vote.Status.OPEN,
            targets=({"order_rank": "Larling"},),
        )
        self.make_vote(
            "Approve the Lawspeaker Document Review Schedule",
            status=Vote.Status.OPEN,
            targets=({"office": "Lawspeaker"},),
        )
        self.make_vote(
            "Approve the Council Record Archive Plan",
            status=Vote.Status.OPEN,
            targets=({"governance_body": "Godi Council"},),
        )
        self.make_vote(
            "Choose a Household Inventory Process",
            status=Vote.Status.OPEN,
            targets=({"household_leadership_type": "Leading Jarl"},),
        )
        self.make_vote(
            "Fund the Chapter Textile Demonstration",
            status=Vote.Status.OPEN,
            targets=({
                "community_group": TEST_GROUP_NAME,
                "chapter": "Fyr Draca Chapter",
            },),
        )
        self.make_vote(
            "Select the Air Order Apprentice Workshop",
            status=Vote.Status.OPEN,
            targets=({"order": "Order of Air", "order_rank": "Larling"},),
        )
        self.make_vote(
            "Approve a Shared Loom Purchase",
            status=Vote.Status.OPEN,
            targets=(
                {"user": "testuser02"},
                {"community_group": TEST_GROUP_NAME},
            ),
        )
        self.make_vote(
            "Fund Replacement Camp Lanterns",
            status=Vote.Status.OPEN,
            requires_quorum=True, quorum=(3, 4),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04", "testuser05"
            ),
            responses=(("testuser01", 0),),
            expected_reason="Quorum was not met.",
        )
        self.make_vote(
            "Approve Public Handout Printing",
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
            "Admit a New Society Citizen",
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
            "Confirm the Revision to the Chapter Rules",
            status=Vote.Status.OPEN,
            requires_all_responses=True,
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(("testuser01", 0),),
            expected_reason="All required responses have not been received.",
        )
        self.make_vote(
            "Choose the Spring Gathering Theme",
            status=Vote.Status.OPEN,
            options=(
                "Maritime Crafts",
                "Textile Traditions",
                "Trade Routes",
            ),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04"
            ),
            responses=(("testuser01", 0), ("testuser02", 1)),
            expected_reason="The vote ended in a tie.",
        )
        self.make_vote(
            "Select Future Research Topics",
            status=Vote.Status.OPEN,
            closes_in_days=None,
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Approve the September Storage Lease",
            status=Vote.Status.OPEN,
            expired=True,
            targets=self.individual_targets("testuser01", "testuser02"),
        )
        self.make_vote(
            "Approve the Volunteer Safety Briefing",
            status=Vote.Status.OPEN,
            targets=self.individual_targets(
                "testuser03", "testuser06", "testuser09", "testuser01"
            ),
        )
        self.make_vote(
            "Approve the Equipment Checkout Form",
            status=Vote.Status.OPEN,
            created_by="testuser40",
            targets=self.individual_targets("testuser02"),
        )

    def create_closed_votes(self):
        self.make_vote(
            "Purchase Two Folding Display Tables",
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
            "Choose the Autumn Workshop Venue",
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
            "Fund a Second Public Demonstration Tent",
            status=Vote.Status.CLOSED,
            requires_quorum=True, quorum=(3, 4),
            targets=self.individual_targets(
                "testuser01", "testuser02", "testuser04", "testuser05"
            ),
            responses=(("testuser01", 0),),
            expected_reason="Quorum was not met.",
        )
        self.make_vote(
            "Approve a New Citizenship Application",
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
            "Approve a Proposed Citizenship Application",
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
            "Select the Annual Member Gathering Format",
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
            "Approve the Final Inventory Sign-Off",
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
            "Adopt the Revised Workshop Calendar",
            status=Vote.Status.CLOSED,
            targets=self.individual_targets("testuser01", "testuser02"),
            responses=(("testuser01", 0), ("testuser02", 0)),
            comments=((
                "testuser01",
                "The proposed schedule conflicts with the second "
                "Saturday workday. Can we review the dates "
                "before closing the vote?",
            ),),
            expected_reason="An option received a simple majority.",
        )
        self.make_vote(
            "Extend the Shared Tool Storage Hours",
            status=Vote.Status.CLOSED,
            targets=self.individual_targets("testuser01", "testuser02"),
            expected_reason="No responses were submitted.",
        )
