
import calendar
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import AccountStatus
from events.models import (
    Event,
    EventInvitation,
    EventParticipation,
    EventTarget,
)
from events.services import resolve_event_invitation_targets
from organization.models import Chapter, CommunityGroup, GroupMembership


User = get_user_model()

SEED_PREFIX = "[DEV EVENT]"
TEST_GROUP_NAME = "Test Custom Group"
TEST_CHAPTER_NAME = "Fyr Draca Chapter"

FILLER_TEXT = (
    "Please arrive with enough time to sign in and set out your materials. "
    "Wear suitable clothing for the activity and bring any tools listed "
    "in the event notes. Volunteers can ask the organizer for a task "
    "when they reach the site."
)

EVENT_DESCRIPTIONS = {
    "Open Workshop: Tablet Weaving": (
        "Visitors can watch a tablet-weaving demonstration and try a short "
        "pattern on the practice loom. All sample yarn and cards are provided."
    ),
    "Member Camp Check-In": (
        "Check the shared equipment, confirm the tent assignments, and "
        "review the safety plan before the public activities begin."
    ),
    "Planning Session: Storage Inventory": (
        "An invited working session to reconcile the storage ledger with "
        "the crates on hand. Bring notes on items your team borrowed."
    ),
    "Morning Bread and Hearth Demonstration": (
        "Learn how flatbread dough is prepared and cooked on a safe "
        "demonstration hearth. The session includes a short tasting."
    ),
    "Living History Camp: Visitor Hours": (
        "Open camp hours with craft displays, daily-life demonstrations, "
        "and a staffed welcome table for visiting families."
    ),
    "Camp Kitchen Coordination": (
        "Kitchen volunteers will assign work areas, check ingredients, "
        "and review food-safety and cleanup responsibilities."
    ),
    "Introductory Runic Lettering": (
        "Try a short writing exercise using historical rune forms. "
        "Paper, pencils, and example inscriptions are provided."
    ),
    "Quick Tool Safety Briefing": (
        "A short briefing on tool handling, shared workspaces, and "
        "first-aid contacts before craft work begins."
    ),
    "Night Watch and Stargazing": (
        "An evening gathering to observe the sky and discuss how "
        "travelers used stars and landmarks for orientation."
    ),
    "Autumn Encampment and Craft Fair": (
        "Three days of member camping, craft teaching, camp maintenance, "
        "and scheduled visitor demonstrations. See the duty roster."
    ),
    "Metalwork Demonstration Within the Encampment": (
        "The smithing team will explain forging equipment and show "
        "sample work in the marked demonstration area."
    ),
    "Seven-Day Textile Research Residency": (
        "A week of supervised weaving, dye-sample documentation, and "
        "comparison of historical textile techniques."
    ),
    "Month-End Maritime Heritage Gathering": (
        "A multi-day display of ship models, ropework, and navigation "
        "research that continues into the next calendar month."
    ),
    "Detailed Workshop Registration Notes": (
        "The workshop packet includes station assignments, a supplies "
        "list, setup notes, and instructions for returning shared tools."
    ),
    "Long-Form Inventory Ledger Review": (
        "Review the storage ledger and identify any inventory IDs that "
        "do not match the physical labels on their crates."
    ),
    "Annual Living History Planning Guide": (
        "Members will review goals for interpretation, public education, "
        "accessibility, travel, equipment, and training."
    ),
    "Finding the Riverside Annex Workshop": (
        "Meet at the annex entrance. Follow signs to the classroom, "
        "and avoid the loading area while supplies are unloaded."
    ),
    "Guest Craft Demonstration": (
        "The public can observe a short demonstration of everyday "
        "Viking-era crafts and ask questions about the tools."
    ),
    "Sagas & 'Skalds' <Open Circle>": (
        "A facilitated reading and discussion of short translated saga "
        "passages, with time for questions from new members."
    ),
    "Morning Bell and Site Access": (
        "The grounds are reserved for setup and access coordination "
        "during the full-day boundary test period."
    ),
    "Late-Day Shield Painting": (
        "Participants will prepare wood samples and paint simple "
        "shield patterns with the workshop's supplied materials."
    ),
    "Spring Research Symposium": (
        "A public meeting for short talks on material culture, "
        "craft documentation, and plans for future research."
    ),
    "Household Textile Study Group": (
        "A private work session for group members to examine weave "
        "patterns and record sample measurements."
    ),
    "Fyr Draca Chapter Planning Meeting": (
        "Chapter members will review the local activity calendar, "
        "volunteer needs, and shared equipment requests."
    ),
    "Research Library Viewing Appointment": (
        "A limited-access viewing session to review the current "
        "reference collection and discuss catalog updates."
    ),
    "Private Equipment Handoff": (
        "An equipment pickup has been arranged for the invited member. "
        "A separate participant can view this calendar record."
    ),
    "Camp Crew Equipment Check": (
        "The camp crew will count tent poles, inspect ropes, and note "
        "replacement supplies for the next trip."
    ),
    "Public Introduction to Nalbinding": (
        "An open introduction to looped textile techniques with "
        "samples for visitors to examine."
    ),
    "Updated Invitations: Cooking Practice": (
        "A small cooking-practice session. One earlier invitation was "
        "withdrawn after the volunteer roster changed."
    ),
    "Small-Group Embroidery Workshop": (
        "A hands-on session for invited members with a separate "
        "view-only audience for scheduling purposes."
    ),
    "Completed: Public Ropework Demonstration": (
        "Visitors learned three basic knots and watched a rope-making "
        "demonstration. The session has ended."
    ),
    "Completed: Camp Grounds Cleanup": (
        "Members cleared the work areas, sorted equipment, and "
        "returned borrowed tables to storage."
    ),
    "Completed: Community Craft Market": (
        "An earlier public market featuring demonstrations, examples "
        "of reconstructed goods, and educational displays."
    ),
    "Completed: Officers' Research Review": (
        "An invited review of the research notes submitted for the "
        "previous quarter."
    ),
    "Completed: Annual General Gathering": (
        "The society met for reports, planning, and shared workshops. "
        "The event record remains available for history."
    ),
    "Completed: Unanswered Workshop Invitation": (
        "A private workshop record kept to check the display of "
        "an invitation that did not receive a response."
    ),
    "Cancelled: Outdoor Archery Introduction": (
        "This public archery introduction was cancelled. The record "
        "remains on the calendar to inform visitors."
    ),
    "Cancelled: Member Tool Maintenance Day": (
        "The volunteer tool-care session was cancelled. Members "
        "should not travel to the workshop site."
    ),
    "Cancelled: Open-Air Dye Demonstration": (
        "The outdoor dye demonstration was cancelled after setup. "
        "No participants should report to the location."
    ),
    "Cancelled: Winter Hearth Workshop": (
        "This earlier workshop was cancelled and remains visible "
        "as a historic record."
    ),
}

EVENT_LOCATIONS = {
    "Open Workshop: Tablet Weaving": "Alderbrook Public Hall, Workshop Room",
    "Member Camp Check-In": "North Meadow Campground",
    "Planning Session: Storage Inventory": "West Storehouse, Inventory Room",
    "Morning Bread and Hearth Demonstration": "Alderbrook Heritage Hall, Hearth Area",
    "Living History Camp: Visitor Hours": "North Meadow Campground, Public Walkway",
    "Camp Kitchen Coordination": "North Meadow Campground, Kitchen Shelter",
    "Introductory Runic Lettering": "Alderbrook Heritage Hall, Classroom 2",
    "Quick Tool Safety Briefing": "North Meadow Campground, Tool Shelter",
    "Night Watch and Stargazing": "North Meadow, Eastern Field",
    "Autumn Encampment and Craft Fair": "North Meadow Campground",
    "Metalwork Demonstration Within the Encampment": "North Meadow Campground, Smithing Area",
    "Seven-Day Textile Research Residency": "Willowbank Craft House",
    "Month-End Maritime Heritage Gathering": "Harborview Heritage Center",
    "Detailed Workshop Registration Notes": "Willowbank Craft House",
    "Long-Form Inventory Ledger Review": "West Storehouse",
    "Annual Living History Planning Guide": "Alderbrook Public Hall",
    "Finding the Riverside Annex Workshop": "Riverside Annex",
    "Sagas & 'Skalds' <Open Circle>": "Alderbrook Public Hall, Reading Room",
    "Late-Day Shield Painting": "Willowbank Craft House",
    "Spring Research Symposium": "Harborview Heritage Center",
    "Household Textile Study Group": "Willowbank Craft House, Study Room",
    "Fyr Draca Chapter Planning Meeting": "North Meadow Campground, Meeting Shelter",
    "Research Library Viewing Appointment": "Alderbrook Research Library",
    "Private Equipment Handoff": "West Storehouse, Rear Entrance",
    "Camp Crew Equipment Check": "North Meadow Campground, Equipment Shelter",
    "Public Introduction to Nalbinding": "Harborview Heritage Center, Classroom",
    "Updated Invitations: Cooking Practice": "North Meadow Campground, Kitchen Shelter",
    "Small-Group Embroidery Workshop": "Willowbank Craft House, Workshop 1",
    "Completed: Public Ropework Demonstration": "Harborview Heritage Center",
    "Completed: Camp Grounds Cleanup": "North Meadow Campground",
    "Completed: Community Craft Market": "Alderbrook Public Hall",
    "Completed: Officers' Research Review": "Alderbrook Public Hall, Meeting Room",
    "Completed: Annual General Gathering": "North Meadow Campground",
    "Completed: Unanswered Workshop Invitation": "Willowbank Craft House",
    "Cancelled: Outdoor Archery Introduction": "North Meadow Campground, Range",
    "Cancelled: Member Tool Maintenance Day": "West Storehouse",
    "Cancelled: Open-Air Dye Demonstration": "North Meadow Campground, Dye Area",
    "Cancelled: Winter Hearth Workshop": "Alderbrook Heritage Hall",
}


class Command(BaseCommand):
    help = (
        "Create repeatable development Events for calendar, agenda, "
        "visibility, invitation, RSVP, and attendance testing."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_event_data can only run when DEBUG is enabled."
            )

        self.users = self.get_required_users()
        self.test_group = self.get_required_group()
        self.test_chapter = self.get_required_chapter()
        self.validate_group_membership()

        Event.objects.filter(
            title__startswith=SEED_PREFIX,
        ).delete()

        self.now = timezone.now()
        self.today = timezone.localdate(self.now)
        self.created_events = []

        self.create_active_events()
        self.create_targeted_events()
        self.create_historical_events()
        self.create_cancelled_events()

        seeded_events = Event.objects.filter(
            title__startswith=SEED_PREFIX,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Event development data seeded successfully."
            )
        )
        self.stdout.write(f"Events: {seeded_events.count()}")
        self.stdout.write(
            "Targets: "
            f"{EventTarget.objects.filter(event__in=seeded_events).count()}"
        )
        self.stdout.write(
            "Invitations: "
            f"{EventInvitation.objects.filter(event__in=seeded_events).count()}"
        )
        self.stdout.write(
            "Participations: "
            f"{EventParticipation.objects.filter(event__in=seeded_events).count()}"
        )
        self.stdout.write("")
        self.stdout.write("Useful accounts:")
        self.stdout.write("  testuser01 - invited member and group member")
        self.stdout.write("  testuser02 - other member with varied access")
        self.stdout.write("  testuser04 - member with selected visibility")
        self.stdout.write("  testuser05 - member without some invitations")
        self.stdout.write("  suTest     - development superuser")
        self.stdout.write("Run this command again to replace the seed Events.")

    def get_required_users(self):
        usernames = {
            "organizer": "suTest",
            "member": "testuser01",
            "member_two": "testuser02",
            "member_three": "testuser04",
            "member_four": "testuser05",
            "member_five": "testuser07",
            "group_member": "testuser16",
            "other_group_member": "testuser19",
            "staff": "testuser40",
        }

        users = {}
        for key, username in usernames.items():
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist as error:
                raise CommandError(
                    f"Required development user {username} does not exist. "
                    "Run seed_dev_data first."
                ) from error

            if (
                user.account_status != AccountStatus.MEMBER
                or not user.is_active
            ):
                raise CommandError(
                    f"Required development user {username} "
                    "must be an active MEMBER."
                )

            users[key] = user

        return users

    def get_required_group(self):
        try:
            return CommunityGroup.objects.get(name=TEST_GROUP_NAME)
        except CommunityGroup.DoesNotExist as error:
            raise CommandError(
                f"{TEST_GROUP_NAME} does not exist. "
                "Run seed_dev_data first."
            ) from error

    def get_required_chapter(self):
        try:
            return Chapter.objects.get(name=TEST_CHAPTER_NAME)
        except Chapter.DoesNotExist as error:
            raise CommandError(
                f"{TEST_CHAPTER_NAME} does not exist. "
                "Run seed_dev_data first."
            ) from error

    def validate_group_membership(self):
        if not GroupMembership.objects.filter(
            user=self.users["member"],
            community_group=self.test_group,
            ended_at__isnull=True,
        ).exists():
            raise CommandError(
                "testuser01 must belong to Test Custom Group. "
                "Run seed_dev_data first."
            )

    def local_datetime(self, day, hour, minute=0):
        return timezone.make_aware(
            datetime.combine(day, time(hour, minute)),
            timezone.get_current_timezone(),
        )

    def next_month(self, day):
        if day.month == 12:
            return date(day.year + 1, 1, 1)
        return date(day.year, day.month + 1, 1)

    def month_boundary_date(self):
        month_end = date(
            self.today.year,
            self.today.month,
            calendar.monthrange(
                self.today.year,
                self.today.month,
            )[1],
        )
        if month_end - timedelta(days=1) <= self.today:
            next_month = self.next_month(self.today)
            month_end = self.next_month(next_month) - timedelta(days=1)
        return month_end - timedelta(days=1)

    def add_target(self, event, purpose, fields):
        selectors = {}
        for name, value in fields.items():
            if name == "user":
                selectors[name] = self.users[value]
            elif name == "community_group":
                selectors[name] = self.test_group
            elif name == "chapter":
                selectors[name] = self.test_chapter
            else:
                raise CommandError(f"Unsupported seed target: {name}")

        target = EventTarget(
            event=event,
            purpose=purpose,
            **selectors,
        )
        target.full_clean()
        target.save()
        return target

    def create_event(
        self,
        title,
        start_at,
        end_at,
        *,
        visibility=Event.Visibility.MEMBERS,
        status=Event.Status.ACTIVE,
        description=FILLER_TEXT,
        location=None,
        organizer="organizer",
        invitation_targets=(),
        visibility_targets=(),
        participation=(),
        revoked_invites=(),
    ):
        if description == FILLER_TEXT:
            description = EVENT_DESCRIPTIONS.get(title, FILLER_TEXT)
        if location is None:
            location = EVENT_LOCATIONS.get(title, "Alderbrook Community Center")

        event = Event(
            title=f"{SEED_PREFIX} {title}",
            description=description,
            start_at=start_at,
            end_at=end_at,
            location=location,
            organizer=self.users[organizer],
            visibility=visibility,
            status=status,
        )
        event.full_clean()
        event.save()

        for target_data in invitation_targets:
            self.add_target(
                event,
                EventTarget.Purpose.INVITATION,
                target_data,
            )

        for target_data in visibility_targets:
            self.add_target(
                event,
                EventTarget.Purpose.VISIBILITY,
                target_data,
            )

        invited_ids = resolve_event_invitation_targets(event)
        for user_id in sorted(invited_ids):
            invitation = EventInvitation(
                event=event,
                user_id=user_id,
            )
            invitation.full_clean()
            invitation.save()

        for user_key in revoked_invites:
            user_id = self.users[user_key].pk
            if user_id in invited_ids:
                raise CommandError(
                    f"Revoked member {user_key} still matches "
                    f"an invitation target for {event.title}."
                )
            invitation = EventInvitation(
                event=event,
                user_id=user_id,
                is_active=False,
                uninvited_at=self.now - timedelta(days=2),
            )
            invitation.full_clean()
            invitation.save()

        for user_key, rsvp, attendance in participation:
            user = self.users[user_key]
            if not EventInvitation.objects.filter(
                event=event,
                user=user,
                is_active=True,
            ).exists():
                raise CommandError(
                    f"Participation requires an active invitation: "
                    f"{user.username} / {event.title}."
                )

            is_historical = end_at <= self.now
            record = EventParticipation(
                event=event,
                user=user,
                rsvp_status=rsvp,
                attendance_status=attendance,
                rsvp_updated_at=(
                    start_at - timedelta(days=2)
                    if is_historical
                    else self.now
                ),
                attendance_recorded_at=(
                    end_at + timedelta(hours=1)
                    if attendance != EventParticipation.AttendanceStatus.UNKNOWN
                    else None
                ),
            )
            record.full_clean()
            record.save()

        self.created_events.append(event)
        return event

    def create_active_events(self):
        day = self.today
        rsvp = EventParticipation.RSVPStatus
        attendance = EventParticipation.AttendanceStatus

        self.create_event(
            'Open Workshop: Tablet Weaving',
            self.now - timedelta(hours=2),
            self.now + timedelta(hours=4),
            visibility=Event.Visibility.PUBLIC,
            location="Alderbrook Public Hall, Workshop Room",
            invitation_targets=({"user": "member"},),
            participation=(("member", rsvp.GOING, attendance.UNKNOWN),),
        )

        self.create_event(
            'Member Camp Check-In',
            self.now - timedelta(hours=9),
            self.now + timedelta(hours=2),
            location="North Meadow Campground",
        )

        self.create_event(
            'Planning Session: Storage Inventory',
            self.now - timedelta(minutes=30),
            self.now + timedelta(hours=6),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member_two"},),
            participation=(("member_two", rsvp.MAYBE, attendance.UNKNOWN),),
        )

        self.create_event(
            'Morning Bread and Hearth Demonstration',
            self.local_datetime(day + timedelta(days=1), 9),
            self.local_datetime(day + timedelta(days=1), 11),
            visibility=Event.Visibility.PUBLIC,
        )

        overlap_day = day + timedelta(days=2)
        self.create_event(
            'Living History Camp: Visitor Hours',
            self.local_datetime(overlap_day, 9),
            self.local_datetime(overlap_day, 14),
            visibility=Event.Visibility.PUBLIC,
            invitation_targets=(
                {"user": "member"},
                {"user": "member_two"},
            ),
            participation=(
                ("member", rsvp.GOING, attendance.UNKNOWN),
                ("member_two", rsvp.NOT_GOING, attendance.UNKNOWN),
            ),
        )

        self.create_event(
            'Camp Kitchen Coordination',
            self.local_datetime(overlap_day, 10),
            self.local_datetime(overlap_day, 12),
            location="North Meadow Campground, Kitchen Shelter",
            invitation_targets=({"user": "member_three"},),
        )

        self.create_event(
            'Introductory Runic Lettering',
            self.local_datetime(overlap_day, 10),
            self.local_datetime(overlap_day, 11, 30),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            'Quick Tool Safety Briefing',
            self.local_datetime(overlap_day, 10, 15),
            self.local_datetime(overlap_day, 10, 30),
        )

        overnight = day + timedelta(days=3)
        self.create_event(
            'Night Watch and Stargazing',
            self.local_datetime(overnight, 23, 15),
            self.local_datetime(overnight + timedelta(days=1), 3, 30),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            'Autumn Encampment and Craft Fair',
            self.local_datetime(day + timedelta(days=5), 9),
            self.local_datetime(day + timedelta(days=7), 18),
            location="North Meadow Campground",
            invitation_targets=({"user": "member"},),
        )

        self.create_event(
            'Metalwork Demonstration Within the Encampment',
            self.local_datetime(day + timedelta(days=6), 13),
            self.local_datetime(day + timedelta(days=6), 16),
            location="North Meadow Campground, Smithing Area",
        )

        self.create_event(
            'Seven-Day Textile Research Residency',
            self.local_datetime(day + timedelta(days=10), 9),
            self.local_datetime(day + timedelta(days=17), 16),
            visibility=Event.Visibility.PUBLIC,
        )

        boundary = self.month_boundary_date()
        self.create_event(
            'Month-End Maritime Heritage Gathering',
            self.local_datetime(boundary, 12),
            self.local_datetime(boundary + timedelta(days=3), 14),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "Detailed Workshop Registration Notes: "
            + "Bring the full tool and material checklist. " * 3,
            self.local_datetime(day + timedelta(days=4), 11),
            self.local_datetime(day + timedelta(days=4), 14),
            description=FILLER_TEXT * 3,
        )

        self.create_event(
            'Long-Form Inventory Ledger Review',
            self.local_datetime(day + timedelta(days=8), 13),
            self.local_datetime(day + timedelta(days=8), 16),
            description=(
                FILLER_TEXT
                + "\n\n"
                + "NORTHMEADOWSUPPLYINVENTORYREFERENCE" * 55
            ),
        )

        self.create_event(
            'Annual Living History Planning Guide',
            self.local_datetime(day + timedelta(days=9), 12),
            self.local_datetime(day + timedelta(days=9), 16),
            description=(FILLER_TEXT + "\n\n") * 48,
        )

        self.create_event(
            'Finding the Riverside Annex Workshop',
            self.local_datetime(day + timedelta(days=11), 12),
            self.local_datetime(day + timedelta(days=11), 15),
            location=(
                "Riverside Annex, East Workshop Wing, "
                + "Second Corridor, Historic Collections Room, " * 4
            ),
        )

        self.create_event(
            'Guest Craft Demonstration',
            self.local_datetime(day + timedelta(days=12), 10),
            self.local_datetime(day + timedelta(days=12), 13),
            visibility=Event.Visibility.PUBLIC,
            description="",
            location="",
        )

        self.create_event(
            "Sagas & 'Skalds' <Open Circle>",
            self.local_datetime(day + timedelta(days=17), 10),
            self.local_datetime(day + timedelta(days=17), 12),
            visibility=Event.Visibility.PUBLIC,
            description=(
                FILLER_TEXT
                + "\n\nSymbols: <example> & \"double quotes\"."
            ),
        )

        self.create_event(
            'Site Opening Notice (Instant)',
            self.local_datetime(day + timedelta(days=23), 9),
            self.local_datetime(day + timedelta(days=23), 9),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            'Morning Bell and Site Access',
            self.local_datetime(day + timedelta(days=24), 0),
            self.local_datetime(day + timedelta(days=25), 0),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            'Late-Day Shield Painting',
            self.local_datetime(day + timedelta(days=18), 16, 30),
            self.local_datetime(day + timedelta(days=18), 19, 30),
        )

        self.create_event(
            'Spring Research Symposium',
            self.local_datetime(day + timedelta(days=180), 9),
            self.local_datetime(day + timedelta(days=180), 12),
            visibility=Event.Visibility.PUBLIC,
        )

    def create_targeted_events(self):
        day = self.today
        rsvp = EventParticipation.RSVPStatus
        attendance = EventParticipation.AttendanceStatus

        self.create_event(
            'Household Textile Study Group',
            self.local_datetime(day + timedelta(days=13), 10),
            self.local_datetime(day + timedelta(days=13), 12),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"community_group": True},),
            organizer="staff",
        )

        self.create_event(
            'Fyr Draca Chapter Planning Meeting',
            self.local_datetime(day + timedelta(days=14), 14),
            self.local_datetime(day + timedelta(days=14), 17),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"chapter": True},),
        )

        self.create_event(
            'Research Library Viewing Appointment',
            self.local_datetime(day + timedelta(days=15), 11),
            self.local_datetime(day + timedelta(days=15), 13),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"user": "member_two"},),
        )

        self.create_event(
            'Private Equipment Handoff',
            self.local_datetime(day + timedelta(days=16), 10),
            self.local_datetime(day + timedelta(days=16), 12),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member"},),
            visibility_targets=({"user": "member_three"},),
            participation=(("member", rsvp.GOING, attendance.UNKNOWN),),
        )

        self.create_event(
            'Camp Crew Equipment Check',
            self.local_datetime(day + timedelta(days=19), 10),
            self.local_datetime(day + timedelta(days=19), 13),
            invitation_targets=({"community_group": True},),
            participation=(
                ("member", rsvp.MAYBE, attendance.UNKNOWN),
                ("group_member", rsvp.GOING, attendance.UNKNOWN),
            ),
        )

        self.create_event(
            'Public Introduction to Nalbinding',
            self.local_datetime(day + timedelta(days=20), 11),
            self.local_datetime(day + timedelta(days=20), 13),
            visibility=Event.Visibility.PUBLIC,
            invitation_targets=(
                {"user": "member"},
                {"user": "member_two"},
            ),
            participation=(("member", rsvp.NOT_GOING, attendance.UNKNOWN),),
        )

        self.create_event(
            'Updated Invitations: Cooking Practice',
            self.local_datetime(day + timedelta(days=21), 11),
            self.local_datetime(day + timedelta(days=21), 14),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"user": "member_four"},),
            revoked_invites=("member",),
        )

        self.create_event(
            'Small-Group Embroidery Workshop',
            self.local_datetime(day + timedelta(days=22), 11),
            self.local_datetime(day + timedelta(days=22), 14),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=(
                {"user": "member"},
                {"user": "member_two"},
            ),
            visibility_targets=({"user": "member_four"},),
        )

    def create_historical_events(self):
        day = self.today
        rsvp = EventParticipation.RSVPStatus
        attendance = EventParticipation.AttendanceStatus

        self.create_event(
            'Completed: Public Ropework Demonstration',
            self.local_datetime(day - timedelta(days=1), 9),
            self.local_datetime(day - timedelta(days=1), 12),
            visibility=Event.Visibility.PUBLIC,
            invitation_targets=({"user": "member"},),
            participation=(("member", rsvp.GOING, attendance.ATTENDED),),
        )

        self.create_event(
            'Completed: Camp Grounds Cleanup',
            self.local_datetime(day - timedelta(days=7), 10),
            self.local_datetime(day - timedelta(days=7), 15),
            invitation_targets=(
                {"user": "member"},
                {"user": "member_two"},
            ),
            participation=(
                ("member", rsvp.GOING, attendance.ATTENDED),
                ("member_two", rsvp.NOT_GOING, attendance.ABSENT),
            ),
        )

        self.create_event(
            'Completed: Community Craft Market',
            self.local_datetime(day - timedelta(days=30), 10),
            self.local_datetime(day - timedelta(days=30), 16),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "Completed: Officers' Research Review",
            self.local_datetime(day - timedelta(days=90), 11),
            self.local_datetime(day - timedelta(days=90), 14),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member_two"},),
            participation=(("member_two", rsvp.MAYBE, attendance.ABSENT),),
        )

        self.create_event(
            'Completed: Annual General Gathering',
            self.local_datetime(day - timedelta(days=395), 10),
            self.local_datetime(day - timedelta(days=395), 17),
            invitation_targets=({"user": "member"},),
            participation=(("member", rsvp.GOING, attendance.ATTENDED),),
        )

        self.create_event(
            'Completed: Unanswered Workshop Invitation',
            self.local_datetime(day - timedelta(days=15), 9),
            self.local_datetime(day - timedelta(days=15), 12),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member_three"},),
        )

    def create_cancelled_events(self):
        day = self.today

        self.create_event(
            'Cancelled: Outdoor Archery Introduction',
            self.local_datetime(day + timedelta(days=4), 9),
            self.local_datetime(day + timedelta(days=4), 12),
            visibility=Event.Visibility.PUBLIC,
            status=Event.Status.CANCELLED,
        )

        self.create_event(
            'Cancelled: Member Tool Maintenance Day',
            self.local_datetime(day + timedelta(days=25), 10),
            self.local_datetime(day + timedelta(days=25), 15),
            status=Event.Status.CANCELLED,
            invitation_targets=({"user": "member_two"},),
        )

        self.create_event(
            'Cancelled: Open-Air Dye Demonstration',
            self.now - timedelta(hours=1),
            self.now + timedelta(hours=3),
            visibility=Event.Visibility.PUBLIC,
            status=Event.Status.CANCELLED,
        )

        self.create_event(
            'Cancelled: Winter Hearth Workshop',
            self.local_datetime(day - timedelta(days=50), 10),
            self.local_datetime(day - timedelta(days=50), 14),
            visibility=Event.Visibility.PUBLIC,
            status=Event.Status.CANCELLED,
        )
