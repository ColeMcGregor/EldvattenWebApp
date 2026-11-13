from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from .forms import (
    CitizenshipAssignmentForm,
    CommunityGroupForm,
    GovernanceMembershipForm,
    GroupMembershipForm,
    OfficeAssignmentForm,
    OrderForm,
    OrderMembershipForm,
    SocialRankAssignmentForm,
)
from .models import (
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

User = get_user_model()


class OrganizationFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="org_admin", email="org_admin@example.test", password="test-password"
        )
        cls.member = User.objects.create_user(
            username="org_member_one", password="test-password",
            eldvatten_name="Zora Weaver", display_name="Ordinary One",
        )
        cls.other_member = User.objects.create_user(
            username="org_member_two", password="test-password",
            eldvatten_name="Astrid Weaver", display_name="Ordinary Two",
        )
        cls.third_member = User.objects.create_user(
            username="org_member_three", password="test-password",
            display_name="Mira Fallback",
        )
        cls.status = ChapterStatus.objects.create(name="Active test status")
        cls.blocked_status = ChapterStatus.objects.create(
            name="Inactive test status", is_selectable=False, allows_new_citizens=False
        )
        cls.chapter = Chapter.objects.create(name="Test Chapter", status=cls.status)
        cls.household = Household.objects.create(name="Test Household")
        cls.citizenship = CitizenshipClass.objects.create(name="Test Citizen")
        cls.social_rank = SocialRank.objects.create(name="Test Rank")
        cls.office = Office.objects.create(name="Test Office")
        cls.governance = GovernanceBody.objects.create(name="Test Council")
        cls.ranked_order = Order.objects.create(name="Test Ranked Order", uses_ranks=True)
        cls.unranked_order = Order.objects.create(name="Test Unranked Order", uses_ranks=False)
        cls.order_rank = OrderRank.objects.create(name="Test Larling", rank_order=1)
        cls.group = CommunityGroup.objects.create(name="Test Community Group")
        cls.leadership_type = HouseholdLeadershipType.objects.create(name="Test Head")

    def setUp(self):
        self.client.force_login(self.admin)
        self.today = timezone.localdate()

    def grant(self, user, *codenames):
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="organization", codename__in=codenames
        ))

    def audit(self, action, target_id=None):
        records = AuditLog.objects.filter(
            actor=self.admin, action=action, source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
        )
        if target_id is not None:
            records = records.filter(target_id=str(target_id))
        return records


class OrganizationAccessTests(OrganizationFixtures):
    def test_anonymous_users_are_redirected_from_all_management_and_detail_routes(self):
        self.client.logout()
        routes = [
            reverse("organization:index"),
            reverse("organization:chapter_manage"),
            reverse("organization:chapter_detail", args=[self.chapter.pk]),
            reverse("organization:household_manage"),
            reverse("organization:household_detail", args=[self.household.pk]),
            reverse("organization:citizenship_manage"),
            reverse("organization:social_rank_manage"),
            reverse("organization:office_manage"),
            reverse("organization:governance_manage"),
            reverse("organization:governance_detail", args=[self.governance.pk]),
            reverse("organization:order_manage"),
            reverse("organization:order_rank_manage"),
            reverse("organization:order_detail", args=[self.ranked_order.pk]),
            reverse("organization:community_group_manage"),
            reverse("organization:community_group_detail", args=[self.group.pk]),
        ]
        for url in routes:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("next=", response["Location"])

    def test_unprivileged_member_cannot_access_organization_pages(self):
        self.client.force_login(self.member)
        for route in (
            "index", "chapter_manage", "household_manage", "citizenship_manage",
            "social_rank_manage", "office_manage", "governance_manage",
            "order_manage", "order_rank_manage", "community_group_manage",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(reverse(f"organization:{route}")).status_code, 403)

    def test_superuser_can_access_all_management_pages(self):
        for route in (
            "index", "chapter_manage", "household_manage", "citizenship_manage",
            "social_rank_manage", "office_manage", "governance_manage",
            "order_manage", "order_rank_manage", "community_group_manage",
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(f"organization:{route}"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "administration/organization_manage.html" if route != "index" else "administration/organization_index.html")

    def test_management_routes_reject_unsupported_http_methods(self):
        for route in (
            "chapter_manage", "household_manage", "citizenship_manage",
            "social_rank_manage", "office_manage", "governance_manage",
            "order_manage", "order_rank_manage", "community_group_manage",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.delete(reverse(f"organization:{route}")).status_code, 405)

    def test_detail_pages_require_get_and_missing_records_return_404(self):
        detail_routes = (
            ("chapter_detail", self.chapter.pk),
            ("household_detail", self.household.pk),
            ("governance_detail", self.governance.pk),
            ("order_detail", self.ranked_order.pk),
            ("community_group_detail", self.group.pk),
        )
        for name, pk in detail_routes:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"organization:{name}", args=[pk])).status_code, 200)
                self.assertEqual(self.client.post(reverse(f"organization:{name}", args=[pk])).status_code, 405)
                self.assertEqual(self.client.get(reverse(f"organization:{name}", args=[999999])).status_code, 404)

    def test_view_only_permissions_allow_read_but_not_create_or_edit(self):
        self.grant(self.member, "view_communitygroup")
        self.client.force_login(self.member)
        url = reverse("organization:community_group_manage")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_add"])
        self.assertFalse(response.context["can_edit"])
        self.assertEqual(self.client.get(url + "?action=create").status_code, 403)
        self.assertEqual(self.client.get(url + f"?edit={self.group.pk}").status_code, 403)
        self.assertEqual(self.client.post(url + "?action=create", {"name": "Not Allowed"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("organization:community_group_detail", args=[self.group.pk])).status_code, 200)
        self.assertFalse(CommunityGroup.objects.filter(name="Not Allowed").exists())

    def test_assignment_only_permission_does_not_grant_definition_edit(self):
        self.grant(self.member, "add_groupmembership")
        self.client.force_login(self.member)
        url = reverse("organization:community_group_manage")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_assign"])
        self.assertFalse(response.context["can_add"])
        self.assertEqual(self.client.get(url + "?action=create").status_code, 403)
        self.assertEqual(self.client.get(reverse("organization:community_group_detail", args=[self.group.pk])).status_code, 403)

    def test_membership_history_not_disclosed_to_definition_only_viewer(self):
        GroupMembership.objects.create(
            user=self.member, community_group=self.group,
            started_at=self.today, changed_by=self.admin,
        )
        self.grant(self.other_member, "view_communitygroup")
        self.client.force_login(self.other_member)
        response = self.client.get(reverse("organization:community_group_detail", args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sections"], [])
        response = self.client.get(reverse("organization:community_group_manage"))
        self.assertFalse(response.context["can_view_assignments"])
        self.assertNotContains(response, "Zora Weaver")

    def test_index_disallows_view_only_role(self):
        self.grant(self.member, "view_communitygroup")
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("organization:index")).status_code, 403)


class DefinitionManagementTests(OrganizationFixtures):
    DEFINITIONS = (
        ("chapter_manage", Chapter, {"status": "status"}),
        ("household_manage", Household, {"is_assignable": "on"}),
        ("citizenship_manage", CitizenshipClass, {"is_assignable": "on"}),
        ("social_rank_manage", SocialRank, {"is_assignable": "on"}),
        ("office_manage", Office, {"is_assignable": "on"}),
        ("governance_manage", GovernanceBody, {"is_assignable": "on"}),
        ("order_manage", Order, {"is_assignable": "on", "uses_ranks": "on"}),
        ("community_group_manage", CommunityGroup, {"is_assignable": "on"}),
    )

    def post_data(self, kwargs, *, name, description="Test description"):
        data = {"name": name, "description": description}
        for field, value in kwargs.items():
            data[field] = self.status.pk if value == "status" else value
        return data

    def test_all_definition_pages_can_create_and_audit(self):
        for i, (route, model, extra) in enumerate(self.DEFINITIONS):
            with self.subTest(route=route):
                url = reverse(f"organization:{route}")
                name = f"Created Definition {i}"
                response = self.client.post(url + "?action=create", self.post_data(extra, name=name))
                self.assertRedirects(response, url)
                obj = model.objects.get(name=name)
                audit = self.audit(AuditLog.Action.CREATE, obj.pk).latest("pk")
                self.assertEqual(audit.new_value["name"], name)
                self.assertEqual(audit.request_path, url)
                if model is Order:
                    self.assertTrue(obj.uses_ranks)
                    self.assertTrue(audit.new_value["uses_ranks"])

    def test_all_definition_pages_can_edit_and_audit_prior_state(self):
        for i, (route, model, extra) in enumerate(self.DEFINITIONS):
            with self.subTest(route=route):
                obj = model.objects.create(
                    name=f"Edit Target {i}", description="Before",
                    **({"status": self.status} if model is Chapter else {}),
                )
                url = reverse(f"organization:{route}")
                new_name = f"Edited Definition {i}"
                response = self.client.post(
                    url + f"?edit={obj.pk}",
                    self.post_data(extra, name=new_name, description="After"),
                )
                self.assertRedirects(response, url)
                obj.refresh_from_db()
                self.assertEqual(obj.name, new_name)
                self.assertEqual(obj.description, "After")
                audit = self.audit(AuditLog.Action.UPDATE, obj.pk).latest("pk")
                self.assertEqual(audit.old_value["name"], f"Edit Target {i}")
                self.assertEqual(audit.new_value["description"], "After")

    def test_search_and_status_filters(self):
        route = reverse("organization:community_group_manage")
        CommunityGroup.objects.create(name="Unique Search Target", description="Findable")
        CommunityGroup.objects.create(name="Not Available", is_assignable=False)
        response = self.client.get(route, {"search": "Unique Search"})
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(response.context["records"][0]["name"], "Unique Search Target")
        response = self.client.get(route, {"status": "unavailable"})
        self.assertEqual([r["name"] for r in response.context["records"]], ["Not Available"])
        response = self.client.get(route, {"status": "assignable"})
        self.assertNotIn("Not Available", [r["name"] for r in response.context["records"]])
        response = self.client.get(route, {"status": "nonsense"})
        self.assertEqual(response.status_code, 200)

    def test_chapter_status_filters_and_nonselectable_existing_status(self):
        target = Chapter.objects.create(name="Former Chapter", status=self.blocked_status)
        response = self.client.get(reverse("organization:chapter_manage"), {"status": self.blocked_status.pk})
        self.assertEqual([r["name"] for r in response.context["records"]], [target.name])
        response = self.client.get(reverse("organization:chapter_manage"), {"edit": target.pk})
        self.assertIn(self.blocked_status, response.context["form"].fields["status"].queryset)
        create_form = self.client.get(reverse("organization:chapter_manage"), {"action": "create"}).context["form"]
        self.assertNotIn(self.blocked_status, create_form.fields["status"].queryset)

    def test_invalid_create_does_not_write_or_audit(self):
        url = reverse("organization:community_group_manage")
        before = self.audit(AuditLog.Action.CREATE).count()
        response = self.client.post(url + "?action=create", {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(self.audit(AuditLog.Action.CREATE).count(), before)

    def test_duplicate_name_is_rejected(self):
        url = reverse("organization:community_group_manage")
        response = self.client.post(url + "?action=create", {
            "name": self.group.name, "description": "Duplicate", "is_assignable": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(CommunityGroup.objects.filter(name=self.group.name).count(), 1)

    def test_post_without_explicit_create_or_edit_is_forbidden(self):
        for route in ("chapter_manage", "household_manage", "community_group_manage", "order_rank_manage"):
            with self.subTest(route=route):
                self.assertEqual(self.client.post(reverse(f"organization:{route}"), {"name": "Bypass"}).status_code, 403)

    def test_pagination_limits_definition_page_to_25(self):
        CommunityGroup.objects.bulk_create([
            CommunityGroup(name=f"Paginated Group {i:02}") for i in range(30)
        ])
        url = reverse("organization:community_group_manage")
        page_one = self.client.get(url)
        page_two = self.client.get(url, {"page": 2})
        self.assertEqual(len(page_one.context["records"]), 25)
        self.assertEqual(len(page_two.context["records"]), 6)

    def test_disabling_definition_does_not_delete_it(self):
        url = reverse("organization:community_group_manage")
        response = self.client.post(url + f"?edit={self.group.pk}", {
            "name": self.group.name, "description": "Retired",
        })
        self.assertRedirects(response, url)
        self.group.refresh_from_db()
        self.assertFalse(self.group.is_assignable)
        self.assertTrue(CommunityGroup.objects.filter(pk=self.group.pk).exists())

    def test_order_rank_create_edit_search_and_audit(self):
        url = reverse("organization:order_rank_manage")
        response = self.client.post(url + "?action=create", {
            "name": "New Rank", "rank_order": 7, "is_assignable": "on",
        })
        self.assertRedirects(response, url)
        rank = OrderRank.objects.get(name="New Rank")
        self.assertEqual(self.audit(AuditLog.Action.CREATE, rank.pk).count(), 1)
        response = self.client.post(url + f"?edit={rank.pk}", {
            "name": "Renamed Rank", "rank_order": 8,
        })
        self.assertRedirects(response, url)
        rank.refresh_from_db()
        self.assertEqual(rank.rank_order, 8)
        self.assertFalse(rank.is_assignable)
        self.assertEqual(self.audit(AuditLog.Action.UPDATE, rank.pk).count(), 1)
        response = self.client.get(url, {"search": "Renamed"})
        self.assertEqual(response.context["page"].paginator.count, 1)


class AssignmentWorkflowTests(OrganizationFixtures):
    ASSIGNMENTS = (
        ("citizenship_manage", CitizenshipRecord, "citizenship_class", "citizenship"),
        ("social_rank_manage", UserSocialRank, "social_rank", "social_rank"),
        ("office_manage", UserOffice, "office", "office"),
        ("governance_manage", GovernanceMembership, "governance_body", "governance"),
        ("order_manage", OrderMembership, "order", "unranked_order"),
        ("community_group_manage", GroupMembership, "community_group", "group"),
    )

    def assignment_data(self, field, obj, *, user=None, started_at=None):
        data = {
            "operation": "assign", "user": (user or self.member).pk,
            field: obj.pk, "started_at": (started_at or self.today).isoformat(),
            "notes": "Assignment note",
        }
        if field in ("citizenship_class", "office"):
            data["chapter"] = self.chapter.pk
        return data

    def test_all_six_assignment_workflows_create_audit_and_end_without_deleting(self):
        for route, model, field, fixture_name in self.ASSIGNMENTS:
            with self.subTest(route=route):
                url = reverse(f"organization:{route}")
                obj = getattr(self, fixture_name)
                payload = self.assignment_data(field, obj)
                response = self.client.post(url + "?assignment=create", payload)
                self.assertRedirects(response, url)
                record = model.objects.get(user=self.member, **{field: obj})
                self.assertEqual(record.changed_by, self.admin)
                self.assertEqual(record.started_at, self.today)
                self.assertEqual(record.notes, "Assignment note")
                self.assertIsNone(record.ended_at)
                assignment_audit = self.audit(AuditLog.Action.ASSIGN, record.pk).filter(
                    target_type=model._meta.verbose_name,
                )
                self.assertEqual(assignment_audit.count(), 1)
                self.assertEqual(assignment_audit.get().new_value["user_id"], self.member.pk)

                response = self.client.post(url, {
                    "operation": "end", "assignment_id": record.pk,
                })
                self.assertRedirects(response, url)
                record.refresh_from_db()
                self.assertEqual(record.ended_at, self.today)
                self.assertEqual(record.changed_by, self.admin)
                self.assertTrue(model.objects.filter(pk=record.pk).exists())
                removal_audit = self.audit(AuditLog.Action.REMOVE, record.pk).filter(
                    target_type=model._meta.verbose_name,
                )
                self.assertEqual(removal_audit.count(), 1)
                self.assertEqual(removal_audit.get().new_value["ended_at"], self.today.isoformat())

    def test_all_six_reject_duplicate_active_assignments(self):
        for route, model, field, fixture_name in self.ASSIGNMENTS:
            with self.subTest(route=route):
                obj = getattr(self, fixture_name)
                payload = self.assignment_data(field, obj, user=self.other_member)
                url = reverse(f"organization:{route}")
                self.assertRedirects(self.client.post(url + "?assignment=create", payload), url)
                response = self.client.post(url + "?assignment=create", payload)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["assignment_form"].errors)
                self.assertEqual(model.objects.filter(user=self.other_member, **{field: obj}).count(), 1)

    def test_end_requires_current_record_and_never_deletes_history(self):
        record = GroupMembership.objects.create(
            user=self.member, community_group=self.group,
            started_at=self.today, changed_by=self.admin, ended_at=self.today,
        )
        url = reverse("organization:community_group_manage")
        response = self.client.post(url, {"operation": "end", "assignment_id": record.pk})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(GroupMembership.objects.filter(pk=record.pk).exists())

    def test_future_dated_assignment_cannot_be_ended_early(self):
        future = self.today + timedelta(days=10)
        record = GroupMembership.objects.create(
            user=self.member, community_group=self.group,
            started_at=future, changed_by=self.admin,
        )
        url = reverse("organization:community_group_manage")
        response = self.client.post(url, {"operation": "end", "assignment_id": record.pk})
        self.assertRedirects(response, url)
        record.refresh_from_db()
        self.assertIsNone(record.ended_at)
        self.assertFalse(self.audit(AuditLog.Action.REMOVE, record.pk).exists())

    def test_ended_assignment_is_visible_in_history(self):
        record = GroupMembership.objects.create(
            user=self.member, community_group=self.group,
            started_at=self.today - timedelta(days=30),
            ended_at=self.today, changed_by=self.admin,
        )
        response = self.client.get(reverse("organization:community_group_manage"))
        self.assertNotIn(record.pk, [item["id"] for item in response.context["current_assignments"]])
        self.assertIn(record.pk, [item["id"] for item in response.context["assignment_history"]])

    def test_invalid_assignment_does_not_create_audit_or_record(self):
        url = reverse("organization:community_group_manage")
        before = self.audit(AuditLog.Action.ASSIGN).count()
        response = self.client.post(url + "?assignment=create", {
            "operation": "assign", "user": self.member.pk,
            "community_group": "", "started_at": self.today.isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["assignment_form"].errors)
        self.assertFalse(GroupMembership.objects.filter(user=self.member).exists())
        self.assertEqual(self.audit(AuditLog.Action.ASSIGN).count(), before)

    def test_unassignable_group_rejected_for_new_assignment(self):
        self.group.is_assignable = False
        self.group.save(update_fields=["is_assignable"])
        url = reverse("organization:community_group_manage")
        response = self.client.post(url + "?assignment=create", self.assignment_data("community_group", self.group))
        self.assertEqual(response.status_code, 200)
        self.assertIn("community_group", response.context["assignment_form"].errors)
        self.assertFalse(GroupMembership.objects.filter(user=self.member).exists())

    def test_nonselectable_chapter_rejected_for_new_citizenship(self):
        self.chapter.status = self.blocked_status
        self.chapter.save(update_fields=["status"])
        url = reverse("organization:citizenship_manage")
        response = self.client.post(
            url + "?assignment=create", self.assignment_data("citizenship_class", self.citizenship)
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("chapter", response.context["assignment_form"].errors)

    def test_one_user_can_hold_offices_in_different_chapters(self):
        other_chapter = Chapter.objects.create(name="Other chapter", status=self.status)
        url = reverse("organization:office_manage")
        first = self.assignment_data("office", self.office)
        second = dict(first, chapter=other_chapter.pk)
        self.assertRedirects(self.client.post(url + "?assignment=create", first), url)
        self.assertRedirects(self.client.post(url + "?assignment=create", second), url)
        self.assertEqual(UserOffice.objects.filter(user=self.member, office=self.office, ended_at__isnull=True).count(), 2)

    def test_order_requires_rank_only_when_order_uses_ranks(self):
        url = reverse("organization:order_manage")
        ranked_data = self.assignment_data("order", self.ranked_order)
        no_rank = self.client.post(url + "?assignment=create", ranked_data)
        self.assertEqual(no_rank.status_code, 200)
        self.assertIn("order_rank", no_rank.context["assignment_form"].errors)
        self.assertFalse(OrderMembership.objects.filter(user=self.member).exists())

        ranked_data["order_rank"] = self.order_rank.pk
        self.assertRedirects(self.client.post(url + "?assignment=create", ranked_data), url)
        ranked_membership = OrderMembership.objects.get(user=self.member, order=self.ranked_order)
        self.assertEqual(ranked_membership.order_rank, self.order_rank)

        unranked_data = self.assignment_data("order", self.unranked_order, user=self.other_member)
        unranked_data["order_rank"] = self.order_rank.pk
        has_rank = self.client.post(url + "?assignment=create", unranked_data)
        self.assertEqual(has_rank.status_code, 200)
        self.assertIn("order_rank", has_rank.context["assignment_form"].errors)
        unranked_data.pop("order_rank")
        self.assertRedirects(self.client.post(url + "?assignment=create", unranked_data), url)
        self.assertIsNone(OrderMembership.objects.get(user=self.other_member, order=self.unranked_order).order_rank)

    def test_cannot_change_rank_structure_after_any_order_membership(self):
        OrderMembership.objects.create(
            user=self.member, order=self.unranked_order,
            started_at=self.today, changed_by=self.admin,
        )
        url = reverse("organization:order_manage")
        response = self.client.post(url + f"?edit={self.unranked_order.pk}", {
            "name": self.unranked_order.name, "description": "Change attempted",
            "uses_ranks": "on", "is_assignable": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("uses_ranks", response.context["form"].errors)
        self.unranked_order.refresh_from_db()
        self.assertFalse(self.unranked_order.uses_ranks)

    def test_order_rank_not_assignable_is_rejected(self):
        self.order_rank.is_assignable = False
        self.order_rank.save(update_fields=["is_assignable"])
        url = reverse("organization:order_manage")
        data = self.assignment_data("order", self.ranked_order)
        data["order_rank"] = self.order_rank.pk
        response = self.client.post(url + "?assignment=create", data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("order_rank", response.context["assignment_form"].errors)

    def test_user_cannot_end_assignments_without_change_permission(self):
        record = GroupMembership.objects.create(
            user=self.member, community_group=self.group,
            started_at=self.today, changed_by=self.admin,
        )
        self.grant(self.other_member, "view_groupmembership", "add_groupmembership")
        self.client.force_login(self.other_member)
        response = self.client.post(reverse("organization:community_group_manage"), {
            "operation": "end", "assignment_id": record.pk,
        })
        self.assertEqual(response.status_code, 403)
        record.refresh_from_db()
        self.assertIsNone(record.ended_at)

    def test_assignment_requires_add_permission(self):
        self.grant(self.other_member, "view_groupmembership")
        self.client.force_login(self.other_member)
        url = reverse("organization:community_group_manage")
        response = self.client.post(url + "?assignment=create", self.assignment_data("community_group", self.group))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(GroupMembership.objects.filter(user=self.member).exists())


class DetailPageTests(OrganizationFixtures):
    def test_chapter_detail_separates_current_and_historical_citizens_and_officers(self):
        CitizenshipRecord.objects.create(
            user=self.member, chapter=self.chapter, citizenship_class=self.citizenship,
            started_at=self.today, changed_by=self.admin,
        )
        CitizenshipRecord.objects.create(
            user=self.other_member, chapter=self.chapter, citizenship_class=self.citizenship,
            started_at=self.today - timedelta(days=20), ended_at=self.today,
            changed_by=self.admin,
        )
        UserOffice.objects.create(
            user=self.member, office=self.office, chapter=self.chapter,
            started_at=self.today, changed_by=self.admin,
        )
        UserOffice.objects.create(
            user=self.other_member, office=self.office, chapter=self.chapter,
            started_at=self.today - timedelta(days=20), ended_at=self.today,
            changed_by=self.admin,
        )
        response = self.client.get(reverse("organization:chapter_detail", args=[self.chapter.pk]))
        sections = {section["title"]: section for section in response.context["sections"]}
        for title in ("Current Citizens", "Former Citizens", "Current Officers", "Former Officers"):
            self.assertEqual(sections[title]["count"], 1)
        self.assertEqual(sections["Current Citizens"]["items"][0]["name"], "Zora Weaver")
        self.assertEqual(sections["Former Officers"]["items"][0]["name"], "Astrid Weaver")

    def test_household_detail_separates_current_and_former_members_and_leaders(self):
        HouseholdMembership.objects.create(
            user=self.member, household=self.household,
            started_at=self.today, changed_by=self.admin,
        )
        HouseholdMembership.objects.create(
            user=self.other_member, household=self.household,
            started_at=self.today - timedelta(days=10), ended_at=self.today,
            changed_by=self.admin,
        )
        HouseholdLeadership.objects.create(
            user=self.member, household=self.household,
            leadership_type=self.leadership_type, started_at=self.today, changed_by=self.admin,
        )
        HouseholdLeadership.objects.create(
            user=self.other_member, household=self.household,
            leadership_type=self.leadership_type, started_at=self.today - timedelta(days=10),
            ended_at=self.today, changed_by=self.admin,
        )
        response = self.client.get(reverse("organization:household_detail", args=[self.household.pk]))
        sections = {section["title"]: section for section in response.context["sections"]}
        for title in ("Current Members", "Former Members", "Current Leadership", "Former Leadership"):
            self.assertEqual(sections[title]["count"], 1)

    def test_governance_order_and_group_details_show_current_and_former_members(self):
        fixtures = (
            ("governance_detail", self.governance, GovernanceMembership, "governance_body"),
            ("order_detail", self.unranked_order, OrderMembership, "order"),
            ("community_group_detail", self.group, GroupMembership, "community_group"),
        )
        for route, obj, model, field in fixtures:
            with self.subTest(route=route):
                model.objects.create(
                    user=self.member, started_at=self.today,
                    changed_by=self.admin, **{field: obj},
                )
                model.objects.create(
                    user=self.other_member,
                    started_at=self.today - timedelta(days=30),
                    ended_at=self.today, changed_by=self.admin, **{field: obj},
                )
                response = self.client.get(reverse(f"organization:{route}", args=[obj.pk]))
                sections = {s["title"]: s for s in response.context["sections"]}
                self.assertEqual(sections["Current Members"]["count"], 1)
                self.assertEqual(sections["Former Members"]["count"], 1)
                self.assertEqual(sections["Current Members"]["items"][0]["name"], "Zora Weaver")


class MemberChoiceTests(OrganizationFixtures):
    FORMS = (
        CitizenshipAssignmentForm,
        SocialRankAssignmentForm,
        OfficeAssignmentForm,
        GovernanceMembershipForm,
        OrderMembershipForm,
        GroupMembershipForm,
    )

    def test_all_six_dropdowns_show_name_username_and_sort_by_name(self):
        for form_class in self.FORMS:
            with self.subTest(form=form_class.__name__):
                form = form_class()
                choices = list(form.fields["user"].widget.choices)
                choices = [(value, str(label)) for value, label in choices if value]
                labels = [label for _, label in choices]
                self.assertIn("Astrid Weaver (@org_member_two)", labels)
                self.assertIn("Zora Weaver (@org_member_one)", labels)
                self.assertIn("Mira Fallback (@org_member_three)", labels)
                self.assertLess(
                    labels.index("Astrid Weaver (@org_member_two)"),
                    labels.index("Mira Fallback (@org_member_three)"),
                )
                self.assertLess(
                    labels.index("Mira Fallback (@org_member_three)"),
                    labels.index("Zora Weaver (@org_member_one)"),
                )
                displayed_names = [label.rsplit(" (@", 1)[0].casefold() for label in labels]
                self.assertEqual(displayed_names, sorted(displayed_names))

    def test_user_name_fallbacks_are_used_when_eldvatten_name_is_missing(self):
        other = User.objects.create_user(username="fallback_username", password="test-password")
        choices = {str(value): str(label) for value, label in GroupMembershipForm().fields["user"].choices}
        self.assertEqual(choices[str(other.pk)], "fallback_username (@fallback_username)")
        self.assertEqual(choices[str(self.third_member.pk)], "Mira Fallback (@org_member_three)")


class OrganizationModelConstraintTests(OrganizationFixtures):
    def test_duplicate_active_group_membership_fails_at_database(self):
        GroupMembership.objects.create(
            user=self.member, community_group=self.group, started_at=self.today,
            changed_by=self.admin,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GroupMembership.objects.create(
                    user=self.member, community_group=self.group,
                    started_at=self.today, changed_by=self.admin,
                )

    def test_historical_group_membership_does_not_block_new_current_membership(self):
        GroupMembership.objects.create(
            user=self.member, community_group=self.group,
            started_at=self.today - timedelta(days=20),
            ended_at=self.today - timedelta(days=10), changed_by=self.admin,
        )
        GroupMembership.objects.create(
            user=self.member, community_group=self.group,
            started_at=self.today, changed_by=self.admin,
        )
        self.assertEqual(GroupMembership.objects.filter(user=self.member, community_group=self.group).count(), 2)

    def test_order_membership_model_validates_rank_policy(self):
        unranked = OrderMembership(
            user=self.member, order=self.unranked_order, order_rank=self.order_rank,
            started_at=self.today, changed_by=self.admin,
        )
        ranked = OrderMembership(
            user=self.other_member, order=self.ranked_order,
            started_at=self.today, changed_by=self.admin,
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            unranked.full_clean()
        with self.assertRaises(ValidationError):
            ranked.full_clean()
