from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from messaging.models import UserBlock
from organization.models import (
    CommunityGroup,
    GroupMembership,
    Household,
    HouseholdMembership,
)

from .directory import visible_directory_members
from .models import AccountStatus, User


class DirectoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.viewer = User.objects.create_user(
            username="directory_viewer",
            display_name="Viewer Name",
            account_status=AccountStatus.MEMBER,
        )
        cls.member = User.objects.create_user(
            username="directory_member",
            display_name="Member Example",
            account_status=AccountStatus.MEMBER,
        )
        cls.other = User.objects.create_user(
            username="directory_other",
            display_name="Other Example",
            account_status=AccountStatus.MEMBER,
        )
        cls.pending = User.objects.create_user(
            username="directory_pending",
            account_status=AccountStatus.PENDING,
        )
        cls.inactive = User.objects.create_user(
            username="directory_inactive",
            account_status=AccountStatus.MEMBER,
            is_active=False,
        )
        cls.household = Household.objects.create(name="Directory Household")
        cls.other_household = Household.objects.create(name="Private Household")
        cls.group = CommunityGroup.objects.create(name="Directory Group")

        for member in (cls.viewer, cls.member, cls.other):
            GroupMembership.objects.create(
                user=member,
                community_group=cls.group,
                started_at=timezone.localdate(),
                changed_by=cls.viewer,
            )

        for member in (cls.viewer, cls.member):
            HouseholdMembership.objects.create(
                user=member,
                household=cls.household,
                started_at=timezone.localdate(),
                changed_by=cls.viewer,
            )

        HouseholdMembership.objects.create(
            user=cls.other,
            household=cls.other_household,
            started_at=timezone.localdate(),
            changed_by=cls.viewer,
        )

    def setUp(self):
        self.client.force_login(self.viewer)

    def url(self):
        return reverse("directory:index")

    def test_directory_navigation_and_member_listing(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Directory | EldVatten")
        self.assertContains(response, "Member Example")
        self.assertContains(response, "Other Example")
        self.assertNotContains(response, "directory_pending")
        self.assertNotContains(response, "directory_inactive")

    def test_search_matches_display_name_and_username(self):
        response = self.client.get(self.url(), {"q": "Member Example"})
        self.assertContains(response, "directory_member")
        self.assertNotContains(response, "directory_other")

        response = self.client.get(self.url(), {"q": "directory_other"})
        self.assertContains(response, "Other Example")
        self.assertNotContains(response, "Member Example")

    def test_first_and_last_name_search(self):
        self.member.first_name = "Rowan"
        self.member.last_name = "Example"
        self.member.display_name = ""
        self.member.save(update_fields=["first_name", "last_name", "display_name"])

        response = self.client.get(self.url(), {"q": "Rowan Example"})
        self.assertContains(response, "directory_member")
        self.assertNotContains(response, "directory_other")

    def test_category_needs_group_selection(self):
        response = self.client.get(
            self.url(),
            {"category": "household"},
        )
        self.assertContains(response, "Choose a group to view its members.")
        self.assertNotContains(response, "Member Example")

    def test_viewer_block_excludes_member_everywhere(self):
        UserBlock.objects.create(
            blocker=self.viewer,
            blocked=self.member,
        )
        response = self.client.get(self.url())
        self.assertNotContains(response, "Member Example")
        self.assertNotContains(
            self.client.get(self.url(), {"q": "Member"}),
            "Member Example",
        )
        self.assertEqual(
            self.client.get(self.url(), {"member": self.member.pk}).status_code,
            404,
        )

    def test_reverse_block_excludes_member_everywhere(self):
        UserBlock.objects.create(
            blocker=self.member,
            blocked=self.viewer,
        )
        response = self.client.get(self.url())
        self.assertNotContains(response, "Member Example")
        self.assertEqual(
            self.client.get(
                self.url(),
                {"member": self.member.pk},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            ).status_code,
            404,
        )

    def test_profile_fragment_shows_selected_members_information(self):
        response = self.client.get(
            self.url(),
            {"member": self.member.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member Profile")
        self.assertContains(response, "Member Example")
        self.assertContains(response, "directory_member")
        self.assertNotContains(response, "Viewer Name")
        self.assertNotContains(response, "<html")

    def test_selected_member_remains_within_directory_page(self):
        response = self.client.get(
            self.url(),
            {"member": self.member.pk},
        )
        self.assertContains(response, "Directory | EldVatten")
        self.assertContains(response, "Member Profile")
        self.assertContains(response, "Member Example")
        self.assertContains(response, 'id="directory-profile"')

    def test_my_eldvatten_profile_still_shows_own_details(self):
        response = self.client.get(
            reverse("my_eldvatten"),
            {"section": "profile"},
        )
        self.assertContains(response, "My Profile")
        self.assertContains(response, "Viewer Name")
        self.assertNotContains(response, "Member Example")


    def test_group_choices_include_all_groups(self):
        response = self.client.get(
            self.url(),
            {"category": "household"},
        )
        self.assertContains(response, "Directory Household")
        self.assertContains(response, "Private Household")

        response = self.client.get(
            self.url(),
            {"category": "group"},
        )
        self.assertContains(response, "Directory Group")

        response = self.client.get(
            self.url(),
            {
                "category": "household",
                "group": f"household:{self.other_household.pk}",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other Example")
        self.assertNotContains(response, "Member Example")

    def test_household_filter_only_returns_current_members(self):
        response = self.client.get(
            self.url(),
            {"category": "household", "group": f"household:{self.household.pk}"},
        )
        self.assertContains(response, "Member Example")
        self.assertNotContains(response, "Other Example")

    def test_group_filter_always_respects_block(self):
        UserBlock.objects.create(
            blocker=self.viewer,
            blocked=self.member,
        )
        response = self.client.get(
            self.url(),
            {"category": "group", "group": f"group:{self.group.pk}"},
        )
        self.assertNotContains(response, "Member Example")
        self.assertContains(response, "Other Example")

    def test_expired_membership_does_not_limit_available_filters(self):
        past_group = CommunityGroup.objects.create(name="Former Group")
        GroupMembership.objects.create(
            user=self.viewer,
            community_group=past_group,
            started_at=timezone.localdate() - timedelta(days=3),
            ended_at=timezone.localdate() - timedelta(days=1),
            changed_by=self.viewer,
        )
        GroupMembership.objects.create(
            user=self.other,
            community_group=past_group,
            started_at=timezone.localdate(),
            changed_by=self.viewer,
        )

        response = self.client.get(
            self.url(),
            {"category": "group"},
        )
        self.assertContains(response, "Former Group")

        response = self.client.get(
            self.url(),
            {"category": "group", "group": f"group:{past_group.pk}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other Example")
        self.assertNotContains(response, "Viewer Name")

    def test_all_group_categories_available_without_memberships(self):
        unaffiliated = User.objects.create_user(
            username="directory_unaffiliated",
            account_status=AccountStatus.MEMBER,
        )
        self.client.force_login(unaffiliated)

        response = self.client.get(self.url())
        for title in (
            "Chapters",
            "Households",
            "Groups",
            "Orders",
            "Governance Bodies",
        ):
            with self.subTest(title=title):
                self.assertContains(response, title)

        response = self.client.get(
            self.url(),
            {
                "category": "household",
                "group": f"household:{self.household.pk}",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member Example")

    def test_blocked_member_excluded_from_other_groups(self):
        UserBlock.objects.create(
            blocker=self.viewer,
            blocked=self.other,
        )
        for category, group in (
            ("group", f"group:{self.group.pk}"),
            ("household", f"household:{self.other_household.pk}"),
        ):
            with self.subTest(category=category):
                response = self.client.get(
                    self.url(),
                    {"category": category, "group": group},
                )
                self.assertNotContains(response, "Other Example")
                self.assertEqual(
                    self.client.get(
                        self.url(),
                        {
                            "category": category,
                            "group": group,
                            "member": self.other.pk,
                        },
                    ).status_code,
                    404,
                )

    def test_unknown_group_filter_cannot_be_used(self):
        response = self.client.get(
            self.url(),
            {"category": "household", "group": "household:999999999"},
        )
        self.assertEqual(response.status_code, 404)

    def test_missing_or_bad_profile_ids_return_404(self):
        for member_id in ("missing", "999999999"):
            with self.subTest(member_id=member_id):
                self.assertEqual(
                    self.client.get(
                        self.url(),
                        {"member": member_id},
                    ).status_code,
                    404,
                )

    def test_profile_from_another_filter_cannot_be_opened(self):
        response = self.client.get(
            self.url(),
            {
                "category": "household",
                "group": f"household:{self.household.pk}",
                "member": self.other.pk,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_anonymous_requires_login_and_pending_gets_403(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code, 302)
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_service_returns_no_members_for_nonmember(self):
        self.assertFalse(visible_directory_members(self.pending).exists())
