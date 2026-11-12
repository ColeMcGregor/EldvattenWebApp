
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus, User
from events.models import Event
from events.queries import (
    active_public_events,
    upcoming_public_events,
)


class PublicEventTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username="public-event-organizer",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

    def create_event(
        self,
        title,
        *,
        start_at=None,
        visibility=Event.Visibility.PUBLIC,
        status=Event.Status.ACTIVE,
        duration=timedelta(hours=2),
    ):
        if start_at is None:
            start_at = timezone.now() + timedelta(days=7)

        return Event.objects.create(
            title=title,
            description=f"Description for {title}",
            start_at=start_at,
            end_at=start_at + duration,
            location=f"Location for {title}",
            organizer=self.organizer,
            visibility=visibility,
            status=status,
        )

    def test_homepage_displays_public_events(self):
        self.create_event("Public Gathering")

        response = self.client.get(
            reverse("home")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")
        self.assertContains(response, "Public Gathering")

    def test_homepage_excludes_restricted_events(self):
        self.create_event(
            "Public Gathering",
        )

        self.create_event(
            "Members Only Gathering",
            visibility=Event.Visibility.MEMBERS,
        )

        self.create_event(
            "Private Gathering",
            visibility=Event.Visibility.CUSTOM,
        )

        response = self.client.get(
            reverse("home")
        )

        self.assertContains(
            response,
            "Public Gathering",
        )

        self.assertNotContains(
            response,
            "Members Only Gathering",
        )

        self.assertNotContains(
            response,
            "Private Gathering",
        )

    def test_homepage_excludes_cancelled_events(self):
        self.create_event(
            "Active Gathering",
        )

        self.create_event(
            "Cancelled Gathering",
            status=Event.Status.CANCELLED,
        )

        response = self.client.get(
            reverse("home")
        )

        self.assertContains(
            response,
            "Active Gathering",
        )

        self.assertNotContains(
            response,
            "Cancelled Gathering",
        )

    def test_homepage_limits_upcoming_events_to_four(self):
        start_at = timezone.now() + timedelta(days=1)

        for index in range(6):
            self.create_event(
                f"Homepage Event {index}",
                start_at=start_at + timedelta(days=index),
            )

        response = self.client.get(
            reverse("home")
        )

        events = list(
            response.context["upcoming_events"]
        )

        self.assertEqual(len(events), 4)

        self.assertEqual(
            [event.title for event in events],
            [
                "Homepage Event 0",
                "Homepage Event 1",
                "Homepage Event 2",
                "Homepage Event 3",
            ],
        )

        self.assertNotContains(
            response,
            "Homepage Event 4",
        )

    def test_homepage_handles_no_upcoming_events(self):
        response = self.client.get(
            reverse("home")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["upcoming_events"]),
            [],
        )

        self.assertContains(
            response,
            "No upcoming events",
        )

    def test_public_calendar_displays_public_events(self):
        self.create_event(
            "Public Calendar Gathering",
            start_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(
            reverse("calendar")
        )

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "events/calendar.html",
        )

        self.assertContains(
            response,
            "Public Calendar Gathering",
        )

    def test_public_calendar_excludes_restricted_events(self):
        start_at = timezone.now() + timedelta(hours=1)

        self.create_event(
            "Visible Calendar Event",
            start_at=start_at,
        )

        self.create_event(
            "Members Calendar Event",
            start_at=start_at,
            visibility=Event.Visibility.MEMBERS,
        )

        self.create_event(
            "Custom Calendar Event",
            start_at=start_at,
            visibility=Event.Visibility.CUSTOM,
        )

        response = self.client.get(
            reverse("calendar")
        )

        self.assertContains(
            response,
            "Visible Calendar Event",
        )

        self.assertNotContains(
            response,
            "Members Calendar Event",
        )

        self.assertNotContains(
            response,
            "Custom Calendar Event",
        )

    def test_authenticated_user_does_not_gain_private_calendar_events(
        self,
    ):
        self.create_event(
            "Public Event",
        )

        self.create_event(
            "Members Event",
            visibility=Event.Visibility.MEMBERS,
        )

        self.client.force_login(self.organizer)

        response = self.client.get(
            reverse("calendar")
        )

        self.assertContains(
            response,
            "Public Event",
        )

        self.assertNotContains(
            response,
            "Members Event",
        )

    def test_public_calendar_excludes_cancelled_events(self):
        start_at = timezone.now() + timedelta(hours=1)

        self.create_event(
            "Active Calendar Event",
            start_at=start_at,
        )

        self.create_event(
            "Cancelled Calendar Event",
            start_at=start_at,
            status=Event.Status.CANCELLED,
        )

        response = self.client.get(
            reverse("calendar")
        )

        self.assertContains(
            response,
            "Active Calendar Event",
        )

        self.assertNotContains(
            response,
            "Cancelled Calendar Event",
        )

    def test_calendar_upcoming_list_limits_events_to_ten(self):
        start_at = timezone.now() + timedelta(days=1)

        for index in range(12):
            self.create_event(
                f"Upcoming Event {index}",
                start_at=start_at + timedelta(days=index),
            )

        response = self.client.get(
            reverse("calendar")
        )

        events = list(
            response.context["upcoming_events"]
        )

        self.assertEqual(len(events), 10)

        self.assertEqual(
            [event.title for event in events],
            [
                f"Upcoming Event {index}"
                for index in range(10)
            ],
        )

    def test_upcoming_events_are_chronological(self):
        start_at = timezone.now() + timedelta(days=1)

        self.create_event(
            "Third Event",
            start_at=start_at + timedelta(days=3),
        )

        self.create_event(
            "First Event",
            start_at=start_at + timedelta(days=1),
        )

        self.create_event(
            "Second Event",
            start_at=start_at + timedelta(days=2),
        )

        events = list(
            upcoming_public_events(limit=None)
        )

        self.assertEqual(
            [event.title for event in events],
            [
                "First Event",
                "Second Event",
                "Third Event",
            ],
        )

    def test_events_currently_underway_remain_upcoming(
        self,
    ):
        start_at = timezone.now() - timedelta(minutes=30)

        self.create_event(
            "Happening Now",
            start_at=start_at,
        )

        events = list(
            upcoming_public_events()
        )

        self.assertEqual(
            [event.title for event in events],
            ["Happening Now"],
        )

    def test_completed_events_are_excluded_from_upcoming(
        self,
    ):
        self.create_event(
            "Past Event",
            start_at=timezone.now() - timedelta(days=2),
        )

        events = list(
            upcoming_public_events()
        )

        self.assertEqual(events, [])

    def test_public_query_excludes_nonpublic_and_cancelled_events(
        self,
    ):
        self.create_event("Active Public")

        self.create_event(
            "Members Only",
            visibility=Event.Visibility.MEMBERS,
        )

        self.create_event(
            "Custom Only",
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_event(
            "Cancelled Public",
            status=Event.Status.CANCELLED,
        )

        self.assertEqual(
            list(
                active_public_events().values_list(
                    "title",
                    flat=True,
                )
            ),
            ["Active Public"],
        )

    def test_calendar_handles_invalid_month_parameters(self):
        invalid_parameters = (
            {"year": "invalid", "month": "11"},
            {"year": "2026", "month": "invalid"},
            {"year": "2026", "month": "13"},
            {"year": "-1", "month": "1"},
        )

        for parameters in invalid_parameters:
            with self.subTest(parameters=parameters):
                response = self.client.get(
                    reverse("calendar"),
                    parameters,
                )

                self.assertEqual(
                    response.status_code,
                    200,
                )

                self.assertEqual(
                    response.context["calendar_month"],
                    timezone.localdate().month,
                )

                self.assertEqual(
                    response.context["calendar_year"],
                    timezone.localdate().year,
                )

    def test_calendar_handles_no_public_events(self):
        response = self.client.get(
            reverse("calendar")
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            list(response.context["upcoming_events"]),
            [],
        )

        self.assertContains(
            response,
            "No upcoming events",
        )

    def test_calendar_places_event_on_correct_day(self):
        start_at = timezone.now() + timedelta(hours=1)

        event = self.create_event(
            "Calendar Day Event",
            start_at=start_at,
        )

        response = self.client.get(
            reverse("calendar")
        )

        expected_date = timezone.localtime(
            start_at
        ).date()

        matching_days = [
            day
            for week in response.context["calendar_weeks"]
            for day in week
            if day.date == expected_date
        ]

        self.assertEqual(len(matching_days), 1)

        self.assertIn(
            event,
            matching_days[0].events,
        )


    def test_public_event_visibility_is_independent_of_organizer_name(self):
        event = self.create_event("Name Independent Gathering")
        self.organizer.display_name = "Personal Display"
        self.organizer.eldvatten_name = "Community Organizer"
        self.organizer.save(update_fields=["display_name", "eldvatten_name"])

        self.assertEqual(
            list(active_public_events().filter(pk=event.pk)),
            [event],
        )

        for url in (reverse("home"), reverse("calendar")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, event.title)

    def test_public_event_listings_do_not_expose_organizer_names(self):
        self.organizer.display_name = "Private Personal Name Sentinel"
        self.organizer.eldvatten_name = "Community Name Sentinel"
        self.organizer.save(update_fields=["display_name", "eldvatten_name"])
        self.create_event("Public Listing Without Organizer")

        for url in (reverse("home"), reverse("calendar")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Public Listing Without Organizer")
                self.assertNotContains(response, "Private Personal Name Sentinel")
                self.assertNotContains(response, "Community Name Sentinel")
