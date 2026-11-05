
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
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris."
)


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
        location="Development Location",
        organizer="organizer",
        invitation_targets=(),
        visibility_targets=(),
        participation=(),
        revoked_invites=(),
    ):
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
            "Happening Now - Public",
            self.now - timedelta(hours=2),
            self.now + timedelta(hours=4),
            visibility=Event.Visibility.PUBLIC,
            location="Development Hall",
            invitation_targets=({"user": "member"},),
            participation=(("member", rsvp.GOING, attendance.UNKNOWN),),
        )

        self.create_event(
            "Happening Now - Members",
            self.now - timedelta(hours=9),
            self.now + timedelta(hours=2),
            location="Development Grounds",
        )

        self.create_event(
            "Happening Now - Invited Only",
            self.now - timedelta(minutes=30),
            self.now + timedelta(hours=6),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member_two"},),
            participation=(("member_two", rsvp.MAYBE, attendance.UNKNOWN),),
        )

        self.create_event(
            "Tomorrow - Morning",
            self.local_datetime(day + timedelta(days=1), 9),
            self.local_datetime(day + timedelta(days=1), 11),
            visibility=Event.Visibility.PUBLIC,
        )

        overlap_day = day + timedelta(days=2)
        self.create_event(
            "Overlap A - Morning Through Afternoon",
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
            "Overlap B - Concurrent Event",
            self.local_datetime(overlap_day, 10),
            self.local_datetime(overlap_day, 12),
            location="Second Development Location",
            invitation_targets=({"user": "member_three"},),
        )

        self.create_event(
            "Overlap C - Same Start Time",
            self.local_datetime(overlap_day, 10),
            self.local_datetime(overlap_day, 11, 30),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "Overlap D - Short Event Within Longer Event",
            self.local_datetime(overlap_day, 10, 15),
            self.local_datetime(overlap_day, 10, 30),
        )

        overnight = day + timedelta(days=3)
        self.create_event(
            "Crossing Midnight",
            self.local_datetime(overnight, 23, 15),
            self.local_datetime(overnight + timedelta(days=1), 3, 30),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "Three-Day Event",
            self.local_datetime(day + timedelta(days=5), 9),
            self.local_datetime(day + timedelta(days=7), 18),
            location="Development Site",
            invitation_targets=({"user": "member"},),
        )

        self.create_event(
            "Overlap Within Three-Day Event",
            self.local_datetime(day + timedelta(days=6), 13),
            self.local_datetime(day + timedelta(days=6), 16),
            location="Development Site - Area B",
        )

        self.create_event(
            "Week-Long Event",
            self.local_datetime(day + timedelta(days=10), 9),
            self.local_datetime(day + timedelta(days=17), 16),
            visibility=Event.Visibility.PUBLIC,
        )

        boundary = self.month_boundary_date()
        self.create_event(
            "Cross-Month Event",
            self.local_datetime(boundary, 12),
            self.local_datetime(boundary + timedelta(days=3), 14),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "Long Title - " + "RepeatedTitleSegment" * 8,
            self.local_datetime(day + timedelta(days=4), 11),
            self.local_datetime(day + timedelta(days=4), 14),
            description=FILLER_TEXT * 3,
        )

        self.create_event(
            "Unbroken Body Text",
            self.local_datetime(day + timedelta(days=8), 13),
            self.local_datetime(day + timedelta(days=8), 16),
            description=(
                FILLER_TEXT + "\n\n" + "UnbrokenToken" * 55
            ),
        )

        self.create_event(
            "Very Long Description",
            self.local_datetime(day + timedelta(days=9), 12),
            self.local_datetime(day + timedelta(days=9), 16),
            description=(FILLER_TEXT + "\n\n") * 48,
        )

        self.create_event(
            "Long Location Field",
            self.local_datetime(day + timedelta(days=11), 12),
            self.local_datetime(day + timedelta(days=11), 15),
            location=("Development Location - " + "LongBuildingName" * 13),
        )

        self.create_event(
            "Empty Description and Location",
            self.local_datetime(day + timedelta(days=12), 10),
            self.local_datetime(day + timedelta(days=12), 13),
            visibility=Event.Visibility.PUBLIC,
            description="",
            location="",
        )

        self.create_event(
            "Punctuation & 'Quotes' <Angle Brackets>",
            self.local_datetime(day + timedelta(days=17), 10),
            self.local_datetime(day + timedelta(days=17), 12),
            visibility=Event.Visibility.PUBLIC,
            description=(
                FILLER_TEXT
                + "\n\nSymbols: <example> & \"double quotes\"."
            ),
        )

        self.create_event(
            "Zero-Duration Event",
            self.local_datetime(day + timedelta(days=23), 9),
            self.local_datetime(day + timedelta(days=23), 9),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "All-Day Boundary - 24 Hours",
            self.local_datetime(day + timedelta(days=24), 0),
            self.local_datetime(day + timedelta(days=25), 0),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "Late Afternoon Event",
            self.local_datetime(day + timedelta(days=18), 16, 30),
            self.local_datetime(day + timedelta(days=18), 19, 30),
        )

        self.create_event(
            "Far Future Event",
            self.local_datetime(day + timedelta(days=180), 9),
            self.local_datetime(day + timedelta(days=180), 12),
            visibility=Event.Visibility.PUBLIC,
        )

    def create_targeted_events(self):
        day = self.today
        rsvp = EventParticipation.RSVPStatus
        attendance = EventParticipation.AttendanceStatus

        self.create_event(
            "Custom - Group Visibility",
            self.local_datetime(day + timedelta(days=13), 10),
            self.local_datetime(day + timedelta(days=13), 12),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"community_group": True},),
            organizer="staff",
        )

        self.create_event(
            "Custom - Chapter Visibility",
            self.local_datetime(day + timedelta(days=14), 14),
            self.local_datetime(day + timedelta(days=14), 17),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"chapter": True},),
        )

        self.create_event(
            "Custom - Visible But Not Invited",
            self.local_datetime(day + timedelta(days=15), 11),
            self.local_datetime(day + timedelta(days=15), 13),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"user": "member_two"},),
        )

        self.create_event(
            "Custom - Invite Plus Separate Visibility",
            self.local_datetime(day + timedelta(days=16), 10),
            self.local_datetime(day + timedelta(days=16), 12),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member"},),
            visibility_targets=({"user": "member_three"},),
            participation=(("member", rsvp.GOING, attendance.UNKNOWN),),
        )

        self.create_event(
            "Members - Group Invitation Targets",
            self.local_datetime(day + timedelta(days=19), 10),
            self.local_datetime(day + timedelta(days=19), 13),
            invitation_targets=({"community_group": True},),
            participation=(
                ("member", rsvp.MAYBE, attendance.UNKNOWN),
                ("group_member", rsvp.GOING, attendance.UNKNOWN),
            ),
        )

        self.create_event(
            "Public - Only Selected Members Invited",
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
            "Custom - Previously Invited Member Revoked",
            self.local_datetime(day + timedelta(days=21), 11),
            self.local_datetime(day + timedelta(days=21), 14),
            visibility=Event.Visibility.CUSTOM,
            visibility_targets=({"user": "member_four"},),
            revoked_invites=("member",),
        )

        self.create_event(
            "Custom - Two Invitation Targets",
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
            "Past - Yesterday",
            self.local_datetime(day - timedelta(days=1), 9),
            self.local_datetime(day - timedelta(days=1), 12),
            visibility=Event.Visibility.PUBLIC,
            invitation_targets=({"user": "member"},),
            participation=(("member", rsvp.GOING, attendance.ATTENDED),),
        )

        self.create_event(
            "Past - Last Week",
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
            "Past - Last Month",
            self.local_datetime(day - timedelta(days=30), 10),
            self.local_datetime(day - timedelta(days=30), 16),
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_event(
            "Past - Three Months Ago",
            self.local_datetime(day - timedelta(days=90), 11),
            self.local_datetime(day - timedelta(days=90), 14),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member_two"},),
            participation=(("member_two", rsvp.MAYBE, attendance.ABSENT),),
        )

        self.create_event(
            "Past - Over One Year Ago",
            self.local_datetime(day - timedelta(days=395), 10),
            self.local_datetime(day - timedelta(days=395), 17),
            invitation_targets=({"user": "member"},),
            participation=(("member", rsvp.GOING, attendance.ATTENDED),),
        )

        self.create_event(
            "Past - Unanswered Invitation",
            self.local_datetime(day - timedelta(days=15), 9),
            self.local_datetime(day - timedelta(days=15), 12),
            visibility=Event.Visibility.CUSTOM,
            invitation_targets=({"user": "member_three"},),
        )

    def create_cancelled_events(self):
        day = self.today
        self.create_event(
            "Cancelled - Upcoming Public Event",
            self.local_datetime(day + timedelta(days=4), 9),
            self.local_datetime(day + timedelta(days=4), 12),
            visibility=Event.Visibility.PUBLIC,
            status=Event.Status.CANCELLED,
        )

        self.create_event(
            "Cancelled - Upcoming Member Event",
            self.local_datetime(day + timedelta(days=25), 10),
            self.local_datetime(day + timedelta(days=25), 15),
            status=Event.Status.CANCELLED,
            invitation_targets=({"user": "member_two"},),
        )

        self.create_event(
            "Cancelled - During Its Scheduled Time",
            self.now - timedelta(hours=1),
            self.now + timedelta(hours=3),
            visibility=Event.Visibility.PUBLIC,
            status=Event.Status.CANCELLED,
        )

        self.create_event(
            "Cancelled - Historic Event",
            self.local_datetime(day - timedelta(days=50), 10),
            self.local_datetime(day - timedelta(days=50), 14),
            visibility=Event.Visibility.PUBLIC,
            status=Event.Status.CANCELLED,
        )
