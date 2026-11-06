from django.utils import timezone

from .models import ActionAssignment
from .tests import ActionTestBase


class ActionListControlTests(ActionTestBase):
    def test_member_list_has_controls_and_sortable_attributes(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url("list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-action-filters")
        self.assertContains(response, "data-action-sort")
        self.assertContains(response, "data-action-status")
        self.assertContains(response, "data-action-required")
        self.assertContains(response, 'data-title="Test Action"')
        self.assertContains(response, 'data-status="NOT_STARTED"')
        self.assertContains(response, 'data-required="0"')
        self.assertContains(response, "js/actions/action-list.js")

    def test_member_attributes_reflect_completed_and_required_actions(self):
        action = self.make_action(
            "Required & Complete",
            deadline=timezone.now(),
            required=True,
        )
        self.assign(action, self.member, status=ActionAssignment.Status.COMPLETED)
        self.client.force_login(self.member)
        response = self.client.get(self.url("list"))
        self.assertContains(response, 'data-title="Required &amp; Complete"')
        self.assertContains(response, 'data-status="COMPLETED"')
        self.assertContains(response, 'data-required="1"')

    def test_member_list_does_not_send_other_members_actions(self):
        action = self.make_action("Other Member Only")
        self.assign(action, self.other_member)
        self.client.force_login(self.member)
        response = self.client.get(self.url("list"))
        self.assertNotContains(response, 'data-title="Other Member Only"')
        self.assertNotContains(response, "Other Member Only")

    def test_management_list_exposes_active_and_total_counts(self):
        action = self.make_action("Assignment Count Fixture")
        self.assign(action, self.member)
        self.assign(action, self.other_member, active=False)
        self.client.force_login(self.manager)
        response = self.client.get(self.url("manage_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-action-assignment-filter")
        self.assertContains(response, "data-action-search")
        self.assertContains(response, 'data-title="Assignment Count Fixture"')
        self.assertContains(response, 'data-active-assignments="1"')
        self.assertContains(response, 'data-total-assignments="2"')
        self.assertContains(response, "js/actions/action-list.js")

    def test_management_list_remains_permission_protected(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url("manage_list"))
        self.assertEqual(response.status_code, 403)
