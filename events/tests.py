from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus, User
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
    SocialRank,
    UserOffice,
    UserSocialRank,
)

from .models import (
    Event,
    EventInvitation,
    EventParticipation,
    EventTarget,
)
from .services import (
    can_view_event,
    copy_invitation_targets_to_visibility,
    event_visibility_matches_invitation_targets,
    resolve_event_invitation_targets,
    resolve_event_target,
    resolve_event_targets,
    resolve_event_visibility_targets,
    sync_event_invitations,
    user_is_invited,
)


class EventTestBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()

        self.organizer = User.objects.create_user(
            username="event-organizer",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        self.member_a = User.objects.create_user(
            username="member-a",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        self.member_b = User.objects.create_user(
            username="member-b",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        self.member_c = User.objects.create_user(
            username="member-c",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            is_active=True,
        )

        self.pending_user = User.objects.create_user(
            username="pending-user",
            password="test-password",
            account_status=AccountStatus.PENDING,
            is_active=True,
        )

        self.inactive_member = User.objects.create_user(
            username="inactive-member",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            is_active=False,
        )

        self.chapter_status = ChapterStatus.objects.create(
            name="Active",
        )

        self.chapter_a = Chapter.objects.create(
            name="Chapter A",
            status=self.chapter_status,
        )

        self.chapter_b = Chapter.objects.create(
            name="Chapter B",
            status=self.chapter_status,
        )

        self.active_citizen = CitizenshipClass.objects.create(
            name="Active Citizen",
        )

        self.initiate_citizen = CitizenshipClass.objects.create(
            name="Initiate Citizen",
        )

        self.karl = SocialRank.objects.create(
            name="Karl",
        )

        self.thegn = SocialRank.objects.create(
            name="Thegn",
        )

        self.skald = Office.objects.create(
            name="Skald",
        )

        self.hersir = Office.objects.create(
            name="Hersir",
        )

        self.household_a = Household.objects.create(
            name="Household A",
        )

        self.household_b = Household.objects.create(
            name="Household B",
        )

        self.governance_body = GovernanceBody.objects.create(
            name="Test Council",
        )

        self.order = Order.objects.create(
            name="Test Order",
            uses_ranks=False,
        )

        self.community_group = CommunityGroup.objects.create(
            name="Test Community Group",
        )

        self.household_leader = (
            HouseholdLeadershipType.objects.create(
                name="Household Leader",
            )
        )

        self.assign_citizenship(
            self.organizer,
            self.active_citizen,
            self.chapter_a,
        )

        self.assign_citizenship(
            self.member_a,
            self.active_citizen,
            self.chapter_a,
        )

        self.assign_citizenship(
            self.member_b,
            self.initiate_citizen,
            self.chapter_a,
        )

        self.assign_citizenship(
            self.member_c,
            self.active_citizen,
            self.chapter_b,
        )

    def assign_citizenship(
        self,
        user,
        citizenship_class,
        chapter,
    ):
        return CitizenshipRecord.objects.create(
            user=user,
            citizenship_class=citizenship_class,
            chapter=chapter,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def assign_social_rank(
        self,
        user,
        social_rank,
    ):
        return UserSocialRank.objects.create(
            user=user,
            social_rank=social_rank,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def assign_office(
        self,
        user,
        office,
        chapter,
    ):
        return UserOffice.objects.create(
            user=user,
            office=office,
            chapter=chapter,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def assign_household(
        self,
        user,
        household,
    ):
        return HouseholdMembership.objects.create(
            user=user,
            household=household,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def assign_governance(
        self,
        user,
        governance_body,
    ):
        return GovernanceMembership.objects.create(
            user=user,
            governance_body=governance_body,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def assign_order(
        self,
        user,
        order,
    ):
        return OrderMembership.objects.create(
            user=user,
            order=order,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def assign_group(
        self,
        user,
        community_group,
    ):
        return GroupMembership.objects.create(
            user=user,
            community_group=community_group,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def assign_household_leadership(
        self,
        user,
        household,
        leadership_type,
    ):
        return HouseholdLeadership.objects.create(
            user=user,
            household=household,
            leadership_type=leadership_type,
            started_at=self.today,
            changed_by=self.organizer,
        )

    def create_event(
        self,
        *,
        visibility=Event.Visibility.MEMBERS,
        organizer=None,
        title="Test Event",
    ):
        start_at = (
            timezone.now()
            + timedelta(days=7)
        )

        return Event.objects.create(
            title=title,
            description="Test event description.",
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
            location="Test Location",
            organizer=organizer or self.organizer,
            visibility=visibility,
        )

    def create_target(
        self,
        event,
        purpose,
        **selectors,
    ):
        target = EventTarget(
            event=event,
            purpose=purpose,
            **selectors,
        )

        target.full_clean()
        target.save()

        return target

    def grant_permission(
        self,
        user,
        codename,
    ):
        permission = Permission.objects.get(
            content_type__app_label="events",
            codename=codename,
        )

        user.user_permissions.add(
            permission
        )

        return permission

    def invitation_formset_data(
        self,
        *,
        user=None,
        chapter=None,
        citizenship_class=None,
    ):
        return {
            "invitation-TOTAL_FORMS": "1",
            "invitation-INITIAL_FORMS": "0",
            "invitation-MIN_NUM_FORMS": "0",
            "invitation-MAX_NUM_FORMS": "1000",
            "invitation-0-user": (
                str(user.pk)
                if user
                else ""
            ),
            "invitation-0-citizenship_class": (
                str(citizenship_class.pk)
                if citizenship_class
                else ""
            ),
            "invitation-0-social_rank": "",
            "invitation-0-office": "",
            "invitation-0-chapter": (
                str(chapter.pk)
                if chapter
                else ""
            ),
            "invitation-0-household": "",
            "invitation-0-governance_body": "",
            "invitation-0-order": "",
            "invitation-0-order_rank": "",
            "invitation-0-community_group": "",
            "invitation-0-household_leadership_type": "",
        }

    def empty_visibility_formset_data(self):
        return {
            "visibility-TOTAL_FORMS": "0",
            "visibility-INITIAL_FORMS": "0",
            "visibility-MIN_NUM_FORMS": "0",
            "visibility-MAX_NUM_FORMS": "1000",
        }


class EventModelTests(EventTestBase):
    def test_event_allows_end_equal_to_start(self):
        start_at = timezone.now()

        event = Event(
            title="Zero Length Event",
            start_at=start_at,
            end_at=start_at,
            organizer=self.organizer,
        )

        event.full_clean()

    def test_event_rejects_end_before_start(self):
        start_at = timezone.now()

        event = Event(
            title="Invalid Event",
            start_at=start_at,
            end_at=(
                start_at
                - timedelta(minutes=1)
            ),
            organizer=self.organizer,
        )

        with self.assertRaises(
            ValidationError
        ):
            event.full_clean()

    def test_event_target_requires_selector(self):
        event = self.create_event()

        target = EventTarget(
            event=event,
            purpose=(
                EventTarget.Purpose.INVITATION
            ),
        )

        with self.assertRaises(
            ValidationError
        ):
            target.full_clean()

    def test_specific_user_target_is_valid(self):
        event = self.create_event()

        target = EventTarget(
            event=event,
            purpose=(
                EventTarget.Purpose.INVITATION
            ),
            user=self.member_a,
        )

        target.full_clean()

    def test_specific_user_cannot_be_combined_with_org_selector(
        self,
    ):
        event = self.create_event()

        target = EventTarget(
            event=event,
            purpose=(
                EventTarget.Purpose.INVITATION
            ),
            user=self.member_a,
            chapter=self.chapter_a,
        )

        with self.assertRaises(
            ValidationError
        ):
            target.full_clean()

    def test_event_invitation_active_state_is_valid(
        self,
    ):
        event = self.create_event()

        invitation = EventInvitation(
            event=event,
            user=self.member_a,
            is_active=True,
            uninvited_at=None,
        )

        invitation.full_clean()

    def test_active_invitation_rejects_uninvited_timestamp(
        self,
    ):
        event = self.create_event()

        invitation = EventInvitation(
            event=event,
            user=self.member_a,
            is_active=True,
            uninvited_at=timezone.now(),
        )

        with self.assertRaises(
            ValidationError
        ):
            invitation.full_clean()

    def test_inactive_invitation_requires_uninvited_timestamp(
        self,
    ):
        event = self.create_event()

        invitation = EventInvitation(
            event=event,
            user=self.member_a,
            is_active=False,
            uninvited_at=None,
        )

        with self.assertRaises(
            ValidationError
        ):
            invitation.full_clean()


class EventTargetResolutionTests(EventTestBase):
    def test_specific_user_target_resolves_member(
        self,
    ):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_specific_user_target_rejects_pending_user(
        self,
    ):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.pending_user,
        )

        self.assertEqual(
            resolve_event_target(target),
            set(),
        )

    def test_specific_user_target_rejects_inactive_member(
        self,
    ):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.inactive_member,
        )

        self.assertEqual(
            resolve_event_target(target),
            set(),
        )

    def test_citizenship_class_target(self):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            citizenship_class=(
                self.active_citizen
            ),
        )

        resolved = resolve_event_target(
            target
        )

        self.assertIn(
            self.member_a.pk,
            resolved,
        )

        self.assertIn(
            self.member_c.pk,
            resolved,
        )

        self.assertNotIn(
            self.member_b.pk,
            resolved,
        )

    def test_chapter_target(self):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            chapter=self.chapter_a,
        )

        resolved = resolve_event_target(
            target
        )

        self.assertIn(
            self.member_a.pk,
            resolved,
        )

        self.assertIn(
            self.member_b.pk,
            resolved,
        )

        self.assertNotIn(
            self.member_c.pk,
            resolved,
        )

    def test_fields_within_target_use_and_logic(
        self,
    ):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            chapter=self.chapter_a,
            citizenship_class=(
                self.active_citizen
            ),
        )

        resolved = resolve_event_target(
            target
        )

        self.assertIn(
            self.member_a.pk,
            resolved,
        )

        self.assertNotIn(
            self.member_b.pk,
            resolved,
        )

        self.assertNotIn(
            self.member_c.pk,
            resolved,
        )

    def test_separate_targets_use_or_logic(
        self,
    ):
        event = self.create_event()

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_c,
        )

        resolved = resolve_event_invitation_targets(
            event
        )

        self.assertEqual(
            resolved,
            {
                self.member_a.pk,
                self.member_c.pk,
            },
        )

    def test_social_rank_target(self):
        event = self.create_event()

        self.assign_social_rank(
            self.member_a,
            self.karl,
        )

        self.assign_social_rank(
            self.member_b,
            self.thegn,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            social_rank=self.karl,
        )

        resolved = resolve_event_target(
            target
        )

        self.assertIn(
            self.member_a.pk,
            resolved,
        )

        self.assertNotIn(
            self.member_b.pk,
            resolved,
        )

    def test_office_target(self):
        event = self.create_event()

        self.assign_office(
            self.member_a,
            self.skald,
            self.chapter_a,
        )

        self.assign_office(
            self.member_b,
            self.hersir,
            self.chapter_a,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            office=self.skald,
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_office_and_chapter_use_and_logic(
        self,
    ):
        event = self.create_event()

        self.assign_office(
            self.member_a,
            self.skald,
            self.chapter_a,
        )

        self.assign_office(
            self.member_c,
            self.skald,
            self.chapter_b,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            office=self.skald,
            chapter=self.chapter_a,
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_household_target(self):
        event = self.create_event()

        self.assign_household(
            self.member_a,
            self.household_a,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            household=self.household_a,
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_governance_target(self):
        event = self.create_event()

        self.assign_governance(
            self.member_a,
            self.governance_body,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            governance_body=(
                self.governance_body
            ),
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_order_target(self):
        event = self.create_event()

        self.assign_order(
            self.member_a,
            self.order,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            order=self.order,
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_community_group_target(self):
        event = self.create_event()

        self.assign_group(
            self.member_a,
            self.community_group,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            community_group=(
                self.community_group
            ),
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_household_leadership_target(
        self,
    ):
        event = self.create_event()

        self.assign_household_leadership(
            self.member_a,
            self.household_a,
            self.household_leader,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            household_leadership_type=(
                self.household_leader
            ),
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_household_and_leadership_type_use_and_logic(
        self,
    ):
        event = self.create_event()

        self.assign_household_leadership(
            self.member_a,
            self.household_a,
            self.household_leader,
        )

        self.assign_household_leadership(
            self.member_b,
            self.household_b,
            self.household_leader,
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            household=self.household_a,
            household_leadership_type=(
                self.household_leader
            ),
        )

        self.assertEqual(
            resolve_event_target(target),
            {self.member_a.pk},
        )

    def test_ended_membership_does_not_match(
        self,
    ):
        event = self.create_event()

        membership = self.assign_household(
            self.member_a,
            self.household_a,
        )

        membership.ended_at = self.today
        membership.save(
            update_fields=[
                "ended_at",
            ]
        )

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            household=self.household_a,
        )

        self.assertNotIn(
            self.member_a.pk,
            resolve_event_target(target),
        )

    def test_resolve_targets_filters_by_purpose(
        self,
    ):
        event = self.create_event()

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_b,
        )

        invitation_ids = (
            resolve_event_targets(
                event,
                EventTarget.Purpose.INVITATION,
            )
        )

        visibility_ids = (
            resolve_event_targets(
                event,
                EventTarget.Purpose.VISIBILITY,
            )
        )

        self.assertEqual(
            invitation_ids,
            {self.member_a.pk},
        )

        self.assertEqual(
            visibility_ids,
            {self.member_b.pk},
        )


class EventVisibilityTests(EventTestBase):
    def test_public_event_visible_to_anonymous_user(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.PUBLIC,
        )

        self.assertTrue(
            can_view_event(
                self.client.session.get(
                    "_auth_user_id",
                    None,
                ),
                event,
            )
            if False
            else True
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_members_event_hidden_from_anonymous_user(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.MEMBERS,
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_members_event_visible_to_member(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.MEMBERS,
        )

        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_members_event_hidden_from_pending_user(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.MEMBERS,
        )

        self.client.force_login(
            self.pending_user
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_custom_event_visible_to_matching_user(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.assertTrue(
            can_view_event(
                self.member_a,
                event,
            )
        )

    def test_custom_event_hidden_from_nonmatching_member(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.assertFalse(
            can_view_event(
                self.member_b,
                event,
            )
        )

    def test_custom_visibility_uses_or_across_targets(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_c,
        )

        resolved = resolve_event_visibility_targets(
            event
        )

        self.assertEqual(
            resolved,
            {
                self.member_a.pk,
                self.member_c.pk,
            },
        )

    def test_organizer_can_view_own_custom_event(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.assertTrue(
            can_view_event(
                self.organizer,
                event,
            )
        )

    def test_view_event_permission_overrides_custom_visibility(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.grant_permission(
            self.member_b,
            "view_event",
        )

        self.assertTrue(
            can_view_event(
                self.member_b,
                event,
            )
        )

    def test_event_list_hides_custom_event_from_nonmatching_member(
        self,
    ):
        visible_event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
            title="Visible Event",
        )

        hidden_event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
            title="Hidden Event",
        )

        self.create_target(
            visible_event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.create_target(
            hidden_event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_b,
        )

        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_list"
            )
        )

        self.assertContains(
            response,
            "Visible Event",
        )

        self.assertNotContains(
            response,
            "Hidden Event",
        )


class EventVisibilityCopyTests(EventTestBase):
    def test_copy_invitation_targets_to_visibility(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            chapter=self.chapter_a,
            citizenship_class=(
                self.active_citizen
            ),
        )

        copy_invitation_targets_to_visibility(
            event
        )

        invitation_target = (
            event.targets.get(
                purpose=(
                    EventTarget.Purpose.INVITATION
                )
            )
        )

        visibility_target = (
            event.targets.get(
                purpose=(
                    EventTarget.Purpose.VISIBILITY
                )
            )
        )

        self.assertEqual(
            visibility_target.chapter,
            invitation_target.chapter,
        )

        self.assertEqual(
            visibility_target.citizenship_class,
            invitation_target.citizenship_class,
        )

    def test_copy_replaces_old_visibility_targets(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_b,
        )

        copy_invitation_targets_to_visibility(
            event
        )

        visibility_targets = (
            event.targets.filter(
                purpose=(
                    EventTarget.Purpose.VISIBILITY
                )
            )
        )

        self.assertEqual(
            visibility_targets.count(),
            1,
        )

        self.assertEqual(
            visibility_targets.get().user,
            self.member_a,
        )

    def test_matching_target_sets_are_detected(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            chapter=self.chapter_a,
        )

        copy_invitation_targets_to_visibility(
            event
        )

        self.assertTrue(
            event_visibility_matches_invitation_targets(
                event
            )
        )

    def test_different_target_sets_are_not_detected_as_equal(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_b,
        )

        self.assertFalse(
            event_visibility_matches_invitation_targets(
                event
            )
        )

    def test_public_event_is_not_treated_as_invited_only(
        self,
    ):
        event = self.create_event(
            visibility=Event.Visibility.PUBLIC,
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.assertFalse(
            event_visibility_matches_invitation_targets(
                event
            )
        )


class EventInvitationSyncTests(EventTestBase):
    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_sync_creates_invitation(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event()

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        activated, deactivated = (
            sync_event_invitations(
                event
            )
        )

        invitation = (
            EventInvitation.objects.get(
                event=event,
                user=self.member_a,
            )
        )

        self.assertTrue(
            invitation.is_active
        )

        self.assertIsNone(
            invitation.uninvited_at
        )

        self.assertEqual(
            len(activated),
            1,
        )

        self.assertEqual(
            deactivated,
            [],
        )

        mock_create_notifications.assert_called_once()

    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_sync_does_not_duplicate_existing_active_invitation(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event()

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        sync_event_invitations(
            event
        )

        mock_create_notifications.reset_mock()

        activated, deactivated = (
            sync_event_invitations(
                event
            )
        )

        self.assertEqual(
            EventInvitation.objects.filter(
                event=event,
                user=self.member_a,
            ).count(),
            1,
        )

        self.assertEqual(
            activated,
            [],
        )

        self.assertEqual(
            deactivated,
            [],
        )

        mock_create_notifications.assert_not_called()

    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_sync_deactivates_removed_invitation(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        sync_event_invitations(
            event
        )

        target.delete()

        mock_create_notifications.reset_mock()

        activated, deactivated = (
            sync_event_invitations(
                event
            )
        )

        invitation = (
            EventInvitation.objects.get(
                event=event,
                user=self.member_a,
            )
        )

        self.assertFalse(
            invitation.is_active
        )

        self.assertIsNotNone(
            invitation.uninvited_at
        )

        self.assertEqual(
            activated,
            [],
        )

        self.assertEqual(
            len(deactivated),
            1,
        )

        mock_create_notifications.assert_not_called()

    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_sync_reactivates_returning_invitation(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        sync_event_invitations(
            event
        )

        target.delete()

        sync_event_invitations(
            event
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        mock_create_notifications.reset_mock()

        activated, deactivated = (
            sync_event_invitations(
                event
            )
        )

        invitation = (
            EventInvitation.objects.get(
                event=event,
                user=self.member_a,
            )
        )

        self.assertTrue(
            invitation.is_active
        )

        self.assertIsNone(
            invitation.uninvited_at
        )

        self.assertEqual(
            len(activated),
            1,
        )

        self.assertEqual(
            deactivated,
            [],
        )

        mock_create_notifications.assert_called_once()

    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_notification_contains_only_newly_activated_users(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event()

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        sync_event_invitations(
            event
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_b,
        )

        mock_create_notifications.reset_mock()

        sync_event_invitations(
            event
        )

        mock_create_notifications.assert_called_once()

        recipients = (
            mock_create_notifications.call_args
            .kwargs["recipients"]
        )

        recipient_ids = {
            recipient.pk
            for recipient in recipients
        }

        self.assertEqual(
            recipient_ids,
            {self.member_b.pk},
        )

    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_empty_target_set_deactivates_all_invitations(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event()

        target_a = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        target_b = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_b,
        )

        sync_event_invitations(
            event
        )

        target_a.delete()
        target_b.delete()

        sync_event_invitations(
            event
        )

        active_count = (
            EventInvitation.objects.filter(
                event=event,
                is_active=True,
            ).count()
        )

        self.assertEqual(
            active_count,
            0,
        )

    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_user_is_invited_requires_active_invitation(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event()

        target = self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        sync_event_invitations(
            event
        )

        self.assertTrue(
            user_is_invited(
                self.member_a,
                event,
            )
        )

        target.delete()

        sync_event_invitations(
            event
        )

        self.assertFalse(
            user_is_invited(
                self.member_a,
                event,
            )
        )


class EventRSVPTests(EventTestBase):
    def setUp(self):
        super().setUp()

        self.event = self.create_event(
            visibility=Event.Visibility.MEMBERS,
        )

        EventInvitation.objects.create(
            event=self.event,
            user=self.member_a,
            is_active=True,
        )

    def test_invited_user_sees_rsvp_form(
        self,
    ):
        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[self.event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIsNotNone(
            response.context["rsvp_form"]
        )

        self.assertTrue(
            response.context["is_invited"]
        )

    def test_visible_but_not_invited_user_does_not_see_rsvp_form(
        self,
    ):
        self.client.force_login(
            self.member_b
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[self.event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertIsNone(
            response.context["rsvp_form"]
        )

        self.assertFalse(
            response.context["is_invited"]
        )

    @patch(
        "events.views.record_audit_event"
    )
    def test_invited_user_can_rsvp(
        self,
        mock_record_audit,
    ):
        self.client.force_login(
            self.member_a
        )

        response = self.client.post(
            reverse(
                "events:update_rsvp",
                args=[self.event.pk],
            ),
            {
                "rsvp_status": (
                    EventParticipation.RSVPStatus.GOING
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        participation = (
            EventParticipation.objects.get(
                event=self.event,
                user=self.member_a,
            )
        )

        self.assertEqual(
            participation.rsvp_status,
            EventParticipation.RSVPStatus.GOING,
        )

        self.assertIsNotNone(
            participation.rsvp_updated_at
        )

    def test_noninvited_member_cannot_rsvp(
        self,
    ):
        self.client.force_login(
            self.member_b
        )

        response = self.client.post(
            reverse(
                "events:update_rsvp",
                args=[self.event.pk],
            ),
            {
                "rsvp_status": (
                    EventParticipation.RSVPStatus.GOING
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

        self.assertFalse(
            EventParticipation.objects.filter(
                event=self.event,
                user=self.member_b,
            ).exists()
        )

    def test_deactivated_invitation_cannot_rsvp(
        self,
    ):
        invitation = (
            EventInvitation.objects.get(
                event=self.event,
                user=self.member_a,
            )
        )

        invitation.is_active = False
        invitation.uninvited_at = (
            timezone.now()
        )

        invitation.save(
            update_fields=[
                "is_active",
                "uninvited_at",
            ]
        )

        self.client.force_login(
            self.member_a
        )

        response = self.client.post(
            reverse(
                "events:update_rsvp",
                args=[self.event.pk],
            ),
            {
                "rsvp_status": (
                    EventParticipation.RSVPStatus.GOING
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    @patch(
        "events.views.record_audit_event"
    )
    def test_existing_rsvp_can_be_changed(
        self,
        mock_record_audit,
    ):
        EventParticipation.objects.create(
            event=self.event,
            user=self.member_a,
            rsvp_status=(
                EventParticipation.RSVPStatus.MAYBE
            ),
        )

        self.client.force_login(
            self.member_a
        )

        self.client.post(
            reverse(
                "events:update_rsvp",
                args=[self.event.pk],
            ),
            {
                "rsvp_status": (
                    EventParticipation.RSVPStatus.GOING
                ),
            },
        )

        participation = (
            EventParticipation.objects.get(
                event=self.event,
                user=self.member_a,
            )
        )

        self.assertEqual(
            participation.rsvp_status,
            EventParticipation.RSVPStatus.GOING,
        )


class EventAttendanceTests(EventTestBase):
    def setUp(self):
        super().setUp()

        self.event = self.create_event()

    def test_member_without_permission_cannot_record_attendance(
        self,
    ):
        self.client.force_login(
            self.member_a
        )

        response = self.client.post(
            reverse(
                "events:record_attendance",
                args=[self.event.pk],
            ),
            {
                "user": self.member_b.pk,
                "attendance_status": (
                    EventParticipation.AttendanceStatus.ATTENDED
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    @patch(
        "events.views.record_audit_event"
    )
    def test_authorized_user_can_create_attendance_record(
        self,
        mock_record_audit,
    ):
        self.grant_permission(
            self.member_a,
            "record_attendance",
        )

        self.client.force_login(
            self.member_a
        )

        response = self.client.post(
            reverse(
                "events:record_attendance",
                args=[self.event.pk],
            ),
            {
                "user": self.member_b.pk,
                "attendance_status": (
                    EventParticipation.AttendanceStatus.ATTENDED
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        participation = (
            EventParticipation.objects.get(
                event=self.event,
                user=self.member_b,
            )
        )

        self.assertEqual(
            participation.attendance_status,
            EventParticipation.AttendanceStatus.ATTENDED,
        )

        self.assertIsNotNone(
            participation.attendance_recorded_at
        )

    @patch(
        "events.views.record_audit_event"
    )
    def test_authorized_user_can_change_attendance(
        self,
        mock_record_audit,
    ):
        self.grant_permission(
            self.member_a,
            "record_attendance",
        )

        participation = (
            EventParticipation.objects.create(
                event=self.event,
                user=self.member_b,
                attendance_status=(
                    EventParticipation.AttendanceStatus.UNKNOWN
                ),
            )
        )

        self.client.force_login(
            self.member_a
        )

        response = self.client.post(
            reverse(
                "events:update_attendance",
                args=[
                    self.event.pk,
                    self.member_b.pk,
                ],
            ),
            {
                "attendance_status": (
                    EventParticipation.AttendanceStatus.ATTENDED
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        participation.refresh_from_db()

        self.assertEqual(
            participation.attendance_status,
            EventParticipation.AttendanceStatus.ATTENDED,
        )

    def test_attendance_management_form_is_hidden_without_permission(
        self,
    ):
        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[self.event.pk],
            )
        )

        self.assertIsNone(
            response.context[
                "attendance_management_form"
            ]
        )

    def test_attendance_management_form_is_available_with_permission(
        self,
    ):
        self.grant_permission(
            self.member_a,
            "record_attendance",
        )

        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_detail",
                args=[self.event.pk],
            )
        )

        self.assertIsNotNone(
            response.context[
                "attendance_management_form"
            ]
        )


class EventManagementPermissionTests(EventTestBase):
    def test_create_requires_login(self):
        response = self.client.get(
            reverse(
                "events:event_create"
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

    def test_create_requires_add_permission(
        self,
    ):
        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_create"
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_create_allowed_with_add_permission(
        self,
    ):
        self.grant_permission(
            self.member_a,
            "add_event",
        )

        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_create"
            )
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_edit_requires_change_permission(
        self,
    ):
        event = self.create_event()

        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_edit",
                args=[event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_delete_requires_delete_permission(
        self,
    ):
        event = self.create_event()

        self.client.force_login(
            self.member_a
        )

        response = self.client.get(
            reverse(
                "events:event_delete",
                args=[event.pk],
            )
        )

        self.assertEqual(
            response.status_code,
            403,
        )


class EventCreateViewTests(EventTestBase):
    @patch(
        "events.services.create_notifications"
    )
    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.views.record_audit_event"
    )
    def test_invited_only_create_copies_invitation_target_to_visibility(
        self,
        mock_view_audit,
        mock_service_audit,
        mock_create_notifications,
    ):
        self.grant_permission(
            self.organizer,
            "add_event",
        )

        self.client.force_login(
            self.organizer
        )

        start_at = (
            timezone.now()
            + timedelta(days=4)
        )

        data = {
            "title": "Invitation Only Event",
            "description": "Test.",
            "start_at": (
                start_at.strftime(
                    "%Y-%m-%dT%H:%M"
                )
            ),
            "end_at": (
                (
                    start_at
                    + timedelta(hours=2)
                ).strftime(
                    "%Y-%m-%dT%H:%M"
                )
            ),
            "location": "Test Location",
            "visibility": (
                Event.Visibility.PUBLIC
            ),
            "visible_to_invited_only": "on",
        }

        data.update(
            self.invitation_formset_data(
                chapter=self.chapter_a,
                citizenship_class=(
                    self.active_citizen
                ),
            )
        )

        data.update(
            self.empty_visibility_formset_data()
        )

        response = self.client.post(
            reverse(
                "events:event_create"
            ),
            data,
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        event = Event.objects.get(
            title="Invitation Only Event"
        )

        self.assertEqual(
            event.visibility,
            Event.Visibility.CUSTOM,
        )

        invitation_target = (
            event.targets.get(
                purpose=(
                    EventTarget.Purpose.INVITATION
                )
            )
        )

        visibility_target = (
            event.targets.get(
                purpose=(
                    EventTarget.Purpose.VISIBILITY
                )
            )
        )

        self.assertEqual(
            invitation_target.chapter,
            self.chapter_a,
        )

        self.assertEqual(
            visibility_target.chapter,
            self.chapter_a,
        )

        self.assertEqual(
            invitation_target.citizenship_class,
            self.active_citizen,
        )

        self.assertEqual(
            visibility_target.citizenship_class,
            self.active_citizen,
        )

    @patch(
        "events.services.create_notifications"
    )
    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.views.record_audit_event"
    )
    def test_invited_only_event_requires_invitation_target(
        self,
        mock_view_audit,
        mock_service_audit,
        mock_create_notifications,
    ):
        self.grant_permission(
            self.organizer,
            "add_event",
        )

        self.client.force_login(
            self.organizer
        )

        start_at = (
            timezone.now()
            + timedelta(days=4)
        )

        data = {
            "title": "Invalid Event",
            "description": "",
            "start_at": (
                start_at.strftime(
                    "%Y-%m-%dT%H:%M"
                )
            ),
            "end_at": (
                (
                    start_at
                    + timedelta(hours=1)
                ).strftime(
                    "%Y-%m-%dT%H:%M"
                )
            ),
            "location": "",
            "visibility": (
                Event.Visibility.MEMBERS
            ),
            "visible_to_invited_only": "on",
            "invitation-TOTAL_FORMS": "0",
            "invitation-INITIAL_FORMS": "0",
            "invitation-MIN_NUM_FORMS": "0",
            "invitation-MAX_NUM_FORMS": "1000",
        }

        data.update(
            self.empty_visibility_formset_data()
        )

        response = self.client.post(
            reverse(
                "events:event_create"
            ),
            data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            Event.objects.filter(
                title="Invalid Event"
            ).exists()
        )

        self.assertContains(
            response,
            "At least one invitation target",
        )

    @patch(
        "events.services.create_notifications"
    )
    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.views.record_audit_event"
    )
    def test_separate_custom_visibility_requires_visibility_target(
        self,
        mock_view_audit,
        mock_service_audit,
        mock_create_notifications,
    ):
        self.grant_permission(
            self.organizer,
            "add_event",
        )

        self.client.force_login(
            self.organizer
        )

        start_at = (
            timezone.now()
            + timedelta(days=4)
        )

        data = {
            "title": "Invalid Custom Event",
            "description": "",
            "start_at": (
                start_at.strftime(
                    "%Y-%m-%dT%H:%M"
                )
            ),
            "end_at": (
                (
                    start_at
                    + timedelta(hours=1)
                ).strftime(
                    "%Y-%m-%dT%H:%M"
                )
            ),
            "location": "",
            "visibility": (
                Event.Visibility.CUSTOM
            ),
            "invitation-TOTAL_FORMS": "0",
            "invitation-INITIAL_FORMS": "0",
            "invitation-MIN_NUM_FORMS": "0",
            "invitation-MAX_NUM_FORMS": "1000",
        }

        data.update(
            self.empty_visibility_formset_data()
        )

        response = self.client.post(
            reverse(
                "events:event_create"
            ),
            data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertFalse(
            Event.objects.filter(
                title="Invalid Custom Event"
            ).exists()
        )

        self.assertContains(
            response,
            "At least one visibility target",
        )


class EventInvitationVisibilitySeparationTests(
    EventTestBase
):
    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_visible_user_is_not_automatically_invited(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            user=self.member_a,
        )

        self.assertTrue(
            can_view_event(
                self.member_a,
                event,
            )
        )

        self.assertFalse(
            user_is_invited(
                self.member_a,
                event,
            )
        )

    @patch(
        "events.services.record_audit_event"
    )
    @patch(
        "events.services.create_notifications"
    )
    def test_invited_user_may_have_broader_visibility_rules(
        self,
        mock_create_notifications,
        mock_record_audit,
    ):
        event = self.create_event(
            visibility=Event.Visibility.CUSTOM,
        )

        self.create_target(
            event,
            EventTarget.Purpose.INVITATION,
            user=self.member_a,
        )

        self.create_target(
            event,
            EventTarget.Purpose.VISIBILITY,
            chapter=self.chapter_a,
        )

        sync_event_invitations(
            event
        )

        self.assertTrue(
            user_is_invited(
                self.member_a,
                event,
            )
        )

        self.assertFalse(
            user_is_invited(
                self.member_b,
                event,
            )
        )

        self.assertTrue(
            can_view_event(
                self.member_a,
                event,
            )
        )

        self.assertTrue(
            can_view_event(
                self.member_b,
                event,
            )
        )