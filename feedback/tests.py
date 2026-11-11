
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections, connections

from django.core.cache import cache
from django.db import IntegrityError
from django.test import (
    RequestFactory,
    TestCase,
    TransactionTestCase,
    override_settings,
)
from django.utils import timezone
from django.urls import reverse

from accounts.models import AccountStatus, User
from audit.models import AuditLog

from .forms import BugReportForm
from .models import BugReport, SubmissionThrottle
from .rate_limiting import (
    SubmissionRateLimitExceeded,
    get_identity_hash,
)
from .services import create_bug_report, update_bug_report
from .views import report_bug

from notifications.models import (
    Notification,
    NotificationPreference,
)


class BugReportFormTests(TestCase):
    def valid_data(self):
        return {
            "contact_email": "reporter@example.com",
            "description": (
                "The page fails to display the expected content."
            ),
            "expected_behavior": (
                "The page should display the requested content."
            ),
            "steps_to_reproduce": (
                "Open the page and select the affected item."
            ),
            "page_url": "http://localhost:8000/community/",
        }

    def test_valid_report_form(self):
        form = BugReportForm(
            data=self.valid_data(),
        )

        self.assertTrue(
            form.is_valid(),
            form.errors,
        )

    def test_description_is_required(self):
        data = self.valid_data()
        data["description"] = ""

        form = BugReportForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn(
            "description",
            form.errors,
        )

    def test_description_requires_ten_characters(self):
        data = self.valid_data()
        data["description"] = "Short"

        form = BugReportForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn(
            "description",
            form.errors,
        )

    def test_description_is_trimmed(self):
        data = self.valid_data()
        data["description"] = "  Something went wrong.  "

        form = BugReportForm(data=data)

        self.assertTrue(form.is_valid())
        self.assertEqual(
            form.cleaned_data["description"],
            "Something went wrong.",
        )

    def test_optional_fields_can_be_empty(self):
        form = BugReportForm(
            data={
                "description": (
                    "The navigation button does not respond."
                ),
            },
        )

        self.assertTrue(
            form.is_valid(),
            form.errors,
        )

    def test_invalid_email_is_rejected(self):
        data = self.valid_data()
        data["contact_email"] = "not-an-email"

        form = BugReportForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn(
            "contact_email",
            form.errors,
        )

    def test_invalid_page_url_is_rejected(self):
        data = self.valid_data()
        data["page_url"] = "not-a-url"

        form = BugReportForm(data=data)

        self.assertFalse(form.is_valid())
        self.assertIn(
            "page_url",
            form.errors,
        )

    def test_public_form_excludes_administrative_fields(self):
        form = BugReportForm()

        self.assertNotIn(
            "reporter",
            form.fields,
        )
        self.assertNotIn(
            "status",
            form.fields,
        )
        self.assertNotIn(
            "admin_notes",
            form.fields,
        )


class BugReportSubmissionTests(TestCase):
    def setUp(self):
        cache.clear()

        self.member = User.objects.create_user(
            username="feedback_member",
            email="member@example.com",
            password="TestPassword123!",
            account_status=AccountStatus.MEMBER,
        )

        self.report_url = reverse(
            "feedback:report_bug"
        )
        self.received_url = reverse(
            "feedback:report_received"
        )

    def tearDown(self):
        cache.clear()

    def valid_data(self):
        return {
            "contact_email": "reporter@example.com",
            "description": (
                "The page fails to display the expected content."
            ),
            "expected_behavior": (
                "The requested content should appear."
            ),
            "steps_to_reproduce": (
                "Open the page and select the affected item."
            ),
            "page_url": "http://localhost:8000/community/",
        }

    def test_anonymous_user_can_open_report_form(self):
        response = self.client.get(
            self.report_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertTemplateUsed(
            response,
            "feedback/report_form.html",
        )

    def test_authenticated_user_can_open_report_form(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.report_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )

    def test_anonymous_submission_creates_report_and_audit(self):
        response = self.client.post(
            self.report_url,
            self.valid_data(),
        )

        self.assertRedirects(
            response,
            self.received_url,
        )

        report = BugReport.objects.get()

        self.assertIsNone(
            report.reporter,
        )
        self.assertEqual(
            report.status,
            BugReport.Status.NEW,
        )

        audit = AuditLog.objects.get(
            target_type="BugReport",
            target_id=str(report.pk),
            action=AuditLog.Action.CREATE,
        )

        self.assertIsNone(
            audit.actor,
        )
        self.assertEqual(
            audit.source,
            AuditLog.Source.WEB_APP,
        )
        self.assertEqual(
            audit.method,
            AuditLog.Method.MANUAL,
        )
        self.assertEqual(
            audit.request_path,
            self.report_url,
        )
        self.assertEqual(
            audit.target_label,
            f"Bug Report #{report.pk}",
        )
        self.assertIsNone(
            audit.old_value,
        )
        self.assertEqual(
            audit.new_value,
            {"status": BugReport.Status.NEW},
        )

    def test_authenticated_submission_records_correct_actor(self):
        self.client.force_login(self.member)

        response = self.client.post(
            self.report_url,
            self.valid_data(),
        )

        self.assertRedirects(
            response,
            self.received_url,
        )

        report = BugReport.objects.get()

        self.assertEqual(
            report.reporter,
            self.member,
        )

        audit = AuditLog.objects.get(
            target_type="BugReport",
            target_id=str(report.pk),
        )

        self.assertEqual(
            audit.actor,
            self.member,
        )

    def test_submission_cannot_set_reporter_or_admin_fields(self):
        data = self.valid_data()
        data.update({
            "reporter": str(self.member.pk),
            "status": BugReport.Status.RESOLVED,
            "admin_notes": "Injected notes",
        })

        response = self.client.post(
            self.report_url,
            data,
        )

        self.assertRedirects(
            response,
            self.received_url,
        )

        report = BugReport.objects.get()

        self.assertIsNone(
            report.reporter,
        )
        self.assertEqual(
            report.status,
            BugReport.Status.NEW,
        )
        self.assertEqual(
            report.admin_notes,
            "",
        )

    def test_invalid_submission_creates_no_records(self):
        data = self.valid_data()
        data["description"] = "Short"

        response = self.client.post(
            self.report_url,
            data,
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertEqual(
            BugReport.objects.count(),
            0,
        )
        self.assertEqual(
            AuditLog.objects.count(),
            0,
        )

    def test_repeated_anonymous_submission_is_rate_limited(self):
        first_response = self.client.post(
            self.report_url,
            self.valid_data(),
            REMOTE_ADDR="192.0.2.10",
        )

        second_response = self.client.post(
            self.report_url,
            self.valid_data(),
            REMOTE_ADDR="192.0.2.10",
        )

        self.assertEqual(
            first_response.status_code,
            302,
        )
        self.assertEqual(
            second_response.status_code,
            429,
        )
        self.assertEqual(
            BugReport.objects.count(),
            1,
        )
        self.assertEqual(
            AuditLog.objects.count(),
            1,
        )

    def test_different_anonymous_addresses_can_submit(self):
        first_response = self.client.post(
            self.report_url,
            self.valid_data(),
            REMOTE_ADDR="192.0.2.11",
        )

        second_response = self.client.post(
            self.report_url,
            self.valid_data(),
            REMOTE_ADDR="192.0.2.12",
        )

        self.assertEqual(
            first_response.status_code,
            302,
        )
        self.assertEqual(
            second_response.status_code,
            302,
        )
        self.assertEqual(
            BugReport.objects.count(),
            2,
        )
        self.assertEqual(
            AuditLog.objects.count(),
            2,
        )

    def test_report_form_prefills_page_url(self):
        response = self.client.get(
            self.report_url,
            {
                "page": "http://localhost:8000/events/",
            },
        )

        self.assertEqual(
            response.context["form"]["page_url"].value(),
            "http://localhost:8000/events/",
        )

    def test_member_email_is_prefilled(self):
        self.client.force_login(self.member)

        response = self.client.get(
            self.report_url
        )

        self.assertEqual(
            response.context["form"]["contact_email"].value(),
            "member@example.com",
        )

    def test_confirmation_page_is_available(self):
        response = self.client.get(
            self.received_url
        )

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertTemplateUsed(
            response,
            "feedback/report_received.html",
        )


class BugReportAuditIntegrityTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def make_request(self):
        request = self.factory.post(
            "/feedback/report/",
            REMOTE_ADDR="192.0.2.20",
        )

        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()

        return request

    def make_report(self):
        return BugReport(
            description=(
                "The page fails when an item is selected."
            ),
            expected_behavior=(
                "The page should display the selected item."
            ),
            steps_to_reproduce=(
                "Open the page and select an item."
            ),
            contact_email="private@example.com",
            page_url="http://localhost:8000/community/",
        )

    def test_audit_does_not_duplicate_report_contents(self):
        report = create_bug_report(
            report=self.make_report(),
            request=self.make_request(),
        )

        audit = AuditLog.objects.get(
            target_type="BugReport",
            target_id=str(report.pk),
        )

        self.assertEqual(
            audit.new_value,
            {"status": "NEW"},
        )

        audit_contents = " ".join([
            audit.target_label,
            audit.notes,
            str(audit.old_value),
            str(audit.new_value),
        ])

        self.assertNotIn(
            report.description,
            audit_contents,
        )
        self.assertNotIn(
            report.contact_email,
            audit_contents,
        )
        self.assertNotIn(
            report.steps_to_reproduce,
            audit_contents,
        )

    def test_audit_records_request_ip(self):
        report = create_bug_report(
            report=self.make_report(),
            request=self.make_request(),
        )

        audit = AuditLog.objects.get(
            target_type="BugReport",
            target_id=str(report.pk),
        )

        self.assertEqual(
            str(audit.ip_address),
            "192.0.2.20",
        )

    def test_existing_report_cannot_be_submitted_again(self):
        report = create_bug_report(
            report=self.make_report(),
            request=self.make_request(),
        )

        with self.assertRaises(ValueError):
            create_bug_report(
                report=report,
                request=self.make_request(),
            )

        self.assertEqual(
            BugReport.objects.count(),
            1,
        )
        self.assertEqual(
            AuditLog.objects.count(),
            1,
        )

    def test_invalid_report_creates_no_audit(self):
        report = self.make_report()
        report.description = ""

        with self.assertRaises(Exception):
            create_bug_report(
                report=report,
                request=self.make_request(),
            )

        self.assertEqual(
            BugReport.objects.count(),
            0,
        )
        self.assertEqual(
            AuditLog.objects.count(),
            0,
        )

    def test_audit_failure_rolls_back_report_creation(self):
        with patch(
            "feedback.services.record_audit_event",
            side_effect=IntegrityError(
                "Simulated audit database failure"
            ),
        ):
            with self.assertRaises(IntegrityError):
                create_bug_report(
                    report=self.make_report(),
                    request=self.make_request(),
                )

        self.assertEqual(
            BugReport.objects.count(),
            0,
        )
        self.assertEqual(
            AuditLog.objects.count(),
            0,
        )

class BugReportAdministrationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="feedback_admin",
            email="admin@example.com",
            password="TestPassword123!",
        )
        self.member = User.objects.create_user(
            username="feedback_regular",
            password="TestPassword123!",
            account_status=AccountStatus.MEMBER,
        )
        self.staff = User.objects.create_user(
            username="feedback_staff",
            password="TestPassword123!",
            is_staff=True,
            account_status=AccountStatus.MEMBER,
        )
        self.report = BugReport.objects.create(
            reporter=self.member,
            description="An existing bug report for management tests.",
            contact_email="reporter@example.com",
            page_url="http://localhost:8000/community/",
        )
        self.list_url = reverse("administration:bug_report_list")
        self.detail_url = reverse(
            "administration:bug_report_detail",
            args=[self.report.pk],
        )

    def test_superuser_can_open_list_and_detail(self):
        self.client.force_login(self.admin)
        listing = self.client.get(self.list_url)
        detail = self.client.get(self.detail_url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertTemplateUsed(listing, "administration/bug_reports.html")
        self.assertTemplateUsed(detail, "administration/bug_report_detail.html")
        self.assertContains(detail, self.report.description)

    def test_system_section_links_to_bug_reports(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("administration:section", args=["system"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.list_url)

    def test_anonymous_visitors_are_redirected_to_login(self):
        for url in (self.list_url, self.detail_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)

    def test_members_cannot_view_or_change_reports(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.get(self.detail_url).status_code, 403)
        response = self.client.post(self.detail_url, {
            "status": BugReport.Status.RESOLVED,
            "admin_notes": "Not allowed",
        })
        self.assertEqual(response.status_code, 403)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, BugReport.Status.NEW)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_staff_without_superuser_cannot_manage_reports(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.get(self.detail_url).status_code, 403)
        self.assertEqual(self.client.post(self.detail_url, {
            "status": BugReport.Status.RESOLVED,
            "admin_notes": "Not allowed",
        }).status_code, 403)

    def test_status_filter_only_returns_matching_reports(self):
        BugReport.objects.create(
            description="A second report in the resolved category.",
            status=BugReport.Status.RESOLVED,
        )
        self.client.force_login(self.admin)
        response = self.client.get(self.list_url, {"status": "NEW"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page"].paginator.count, 1)
        self.assertEqual(response.context["reports"][0], self.report)

    def test_invalid_status_filter_is_ignored(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.list_url, {"status": "INVALID"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_status"], "")
        self.assertEqual(response.context["page"].paginator.count, 1)

    def test_report_list_is_paginated(self):
        BugReport.objects.bulk_create([
            BugReport(description=f"Additional test report {i}.")
            for i in range(25)
        ])
        self.client.force_login(self.admin)
        first = self.client.get(self.list_url)
        second = self.client.get(self.list_url, {"page": "2"})
        self.assertEqual(len(first.context["reports"]), 25)
        self.assertEqual(len(second.context["reports"]), 1)
        self.assertEqual(first.context["page"].paginator.count, 26)

    def test_administrator_updates_status_and_creates_audit(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.detail_url, {
            "status": BugReport.Status.INVESTIGATING,
            "admin_notes": "",
        })
        self.assertRedirects(response, self.detail_url)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, BugReport.Status.INVESTIGATING)
        audit = AuditLog.objects.get(
            target_type="BugReport",
            target_id=str(self.report.pk),
            action=AuditLog.Action.UPDATE,
        )
        self.assertEqual(audit.actor, self.admin)
        self.assertEqual(audit.old_value, {"status": "NEW"})
        self.assertEqual(audit.new_value, {"status": "INVESTIGATING"})
        self.assertEqual(audit.source, AuditLog.Source.WEB_APP)

    def test_notes_edit_is_audited_without_copying_text(self):
        self.client.force_login(self.admin)
        note = "Private internal investigation notes."
        response = self.client.post(self.detail_url, {
            "status": BugReport.Status.NEW,
            "admin_notes": note,
        })
        self.assertRedirects(response, self.detail_url)
        self.report.refresh_from_db()
        self.assertEqual(self.report.admin_notes, note)
        audit = AuditLog.objects.get(action=AuditLog.Action.UPDATE)
        self.assertEqual(audit.notes, "Internal notes updated.")
        self.assertNotIn(note, str(audit.new_value))
        self.assertNotIn(note, str(audit.old_value))
        self.assertNotIn(note, audit.notes)

    def test_unchanged_submission_does_not_create_audit_noise(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.detail_url, {
            "status": BugReport.Status.NEW,
            "admin_notes": "",
        })
        self.assertRedirects(response, self.detail_url)
        self.assertFalse(AuditLog.objects.exists())

    def test_invalid_status_does_not_save_or_audit(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.detail_url, {
            "status": "NOT_A_STATUS",
            "admin_notes": "Changed",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, BugReport.Status.NEW)
        self.assertEqual(self.report.admin_notes, "")
        self.assertFalse(AuditLog.objects.exists())

    def test_audit_failure_rolls_back_administrative_update(self):
        self.client.force_login(self.admin)
        with patch(
            "feedback.services.record_audit_event",
            side_effect=IntegrityError("Simulated audit failure"),
        ):
            with self.assertRaises(IntegrityError):
                self.client.post(self.detail_url, {
                    "status": BugReport.Status.RESOLVED,
                    "admin_notes": "Should be rolled back",
                })
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, BugReport.Status.NEW)
        self.assertEqual(self.report.admin_notes, "")
        self.assertFalse(AuditLog.objects.exists())

    def test_service_rejects_non_administrator(self):
        request = RequestFactory().post(self.detail_url)
        request.user = self.member
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            update_bug_report(
                report=self.report,
                status=BugReport.Status.RESOLVED,
                admin_notes="No permission",
                request=request,
            )
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, BugReport.Status.NEW)
        self.assertFalse(AuditLog.objects.exists())


class BugReportNotificationTests(TestCase):
    def setUp(self):
        cache.clear()

        self.report_url = reverse(
            "feedback:report_bug"
        )

        self.admin_one = User.objects.create_superuser(
            username="feedback_admin_one",
            email="admin-one@example.com",
            password="TestPassword123!",
        )

        self.admin_two = User.objects.create_superuser(
            username="feedback_admin_two",
            email="admin-two@example.com",
            password="TestPassword123!",
        )

        self.member = User.objects.create_user(
            username="feedback_notification_member",
            email="member@example.com",
            password="TestPassword123!",
            account_status=AccountStatus.MEMBER,
        )

        self.staff = User.objects.create_user(
            username="feedback_staff",
            email="staff@example.com",
            password="TestPassword123!",
            is_staff=True,
        )

        self.inactive_admin = User.objects.create_superuser(
            username="feedback_inactive_admin",
            email="inactive@example.com",
            password="TestPassword123!",
        )

        self.inactive_admin.is_active = False
        self.inactive_admin.save(
            update_fields=["is_active"]
        )

    def tearDown(self):
        cache.clear()

    def valid_data(self):
        return {
            "contact_email": "private@example.com",
            "description": (
                "The page fails to display the expected content."
            ),
            "expected_behavior": (
                "The page should display the requested content."
            ),
            "steps_to_reproduce": (
                "Open the page and select the affected item."
            ),
            "page_url": "http://localhost:8000/community/",
        }

    def submit_report(self):
        return self.client.post(
            self.report_url,
            self.valid_data(),
            REMOTE_ADDR="192.0.2.50",
        )

    def test_new_report_notifies_active_full_administrators(self):
        response = self.submit_report()

        self.assertEqual(
            response.status_code,
            302,
        )

        report = BugReport.objects.get()

        notifications = Notification.objects.filter(
            source_type="BugReport",
            source_id=str(report.pk),
        )

        self.assertEqual(
            notifications.count(),
            2,
        )

        self.assertSetEqual(
            set(
                notifications.values_list(
                    "user_id",
                    flat=True,
                )
            ),
            {
                self.admin_one.pk,
                self.admin_two.pk,
            },
        )

    def test_notification_links_to_correct_report(self):
        self.submit_report()

        report = BugReport.objects.get()

        expected_url = reverse(
            "administration:bug_report_detail",
            args=[report.pk],
        )

        notifications = Notification.objects.filter(
            source_type="BugReport",
            source_id=str(report.pk),
        )

        for notification in notifications:
            self.assertEqual(
                notification.notification_type,
                Notification.Type.SYSTEM,
            )

            self.assertEqual(
                notification.title,
                f"New Bug Report #{report.pk}",
            )

            self.assertEqual(
                notification.target_url,
                expected_url,
            )

            self.assertFalse(
                notification.is_read,
            )

    def test_notification_does_not_expose_report_contents(self):
        self.submit_report()

        report = BugReport.objects.get()

        notifications = Notification.objects.filter(
            source_type="BugReport",
            source_id=str(report.pk),
        )

        for notification in notifications:
            notification_contents = " ".join([
                notification.title,
                notification.message,
                notification.source_type,
                notification.source_id,
                notification.target_url,
            ])

            self.assertNotIn(
                report.description,
                notification_contents,
            )

            self.assertNotIn(
                report.contact_email,
                notification_contents,
            )

            self.assertNotIn(
                report.steps_to_reproduce,
                notification_contents,
            )

    def test_disabled_push_preference_preserves_in_app_notification(self):
        NotificationPreference.objects.create(
            user=self.admin_one,
            push_enabled=False,
        )

        self.submit_report()

        notification_one = Notification.objects.get(
            user=self.admin_one,
            source_type="BugReport",
        )

        notification_two = Notification.objects.get(
            user=self.admin_two,
            source_type="BugReport",
        )

        self.assertFalse(
            notification_one.push_requested,
        )

        self.assertTrue(
            notification_two.push_requested,
        )

    def test_disabled_system_push_preserves_in_app_notification(self):
        NotificationPreference.objects.create(
            user=self.admin_one,
            system_push=False,
        )

        self.submit_report()

        notification = Notification.objects.get(
            user=self.admin_one,
            source_type="BugReport",
        )

        self.assertFalse(
            notification.push_requested,
        )

        self.assertFalse(
            notification.is_read,
        )

    def test_notification_failure_rolls_back_report_and_audit(self):
        with patch(
            "feedback.services.create_notifications",
            side_effect=IntegrityError(
                "Simulated notification failure"
            ),
        ):
            with self.assertRaises(IntegrityError):
                self.submit_report()

        self.assertEqual(
            BugReport.objects.count(),
            0,
        )

        self.assertEqual(
            AuditLog.objects.filter(
                target_type="BugReport",
            ).count(),
            0,
        )

        self.assertEqual(
            Notification.objects.filter(
                source_type="BugReport",
            ).count(),
            0,
        )

    def test_invalid_submission_creates_no_notifications(self):
        data = self.valid_data()
        data["description"] = "Short"

        response = self.client.post(
            self.report_url,
            data,
            REMOTE_ADDR="192.0.2.51",
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertEqual(
            BugReport.objects.count(),
            0,
        )

        self.assertFalse(
            Notification.objects.filter(
                source_type="BugReport",
            ).exists()
        )

    def test_push_dispatch_runs_after_commit(self):
        with patch(
            "notifications.services.send_push_notifications"
        ) as send_push:
            with self.captureOnCommitCallbacks(
                execute=True
            ):
                self.submit_report()

            send_push.assert_called_once()

            dispatched = send_push.call_args.args[0]

            self.assertSetEqual(
                {
                    notification.user_id
                    for notification in dispatched
                },
                {
                    self.admin_one.pk,
                    self.admin_two.pk,
                },
            )



class BugReportRateLimitTests(TestCase):
    def setUp(self):
        self.report_url = reverse("feedback:report_bug")
        self.member = User.objects.create_user(
            username="throttle_member",
            password="TestPassword123!",
            account_status=AccountStatus.MEMBER,
        )

    def valid_data(self):
        return {
            "description": "A valid report about an unresponsive menu button.",
        }

    def submit(self, *, address="192.0.2.80", **headers):
        return self.client.post(
            self.report_url,
            self.valid_data(),
            REMOTE_ADDR=address,
            **headers,
        )

    def shift_window(self, period, *, address="192.0.2.80", minutes=2):
        identifier = (
            f"user:{self.member.pk}"
            if self.client.session.get("_auth_user_id")
            else f"ip:{address}"
        )
        SubmissionThrottle.objects.filter(
            identifier=get_identity_hash(identifier),
            period=period,
        ).update(
            window_started_at=timezone.now() - timedelta(minutes=minutes),
        )

    def test_second_submission_is_rejected_with_retry_after(self):
        self.assertEqual(self.submit().status_code, 302)
        response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertEqual(BugReport.objects.count(), 1)
        self.assertEqual(
            AuditLog.objects.filter(target_type="BugReport").count(), 1
        )

    def test_minute_quota_expires(self):
        self.assertEqual(self.submit().status_code, 302)
        self.shift_window(SubmissionThrottle.Period.MINUTE)
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(BugReport.objects.count(), 2)

    def test_anonymous_hourly_quota_is_three(self):
        for _ in range(3):
            self.assertEqual(self.submit().status_code, 302)
            self.shift_window(SubmissionThrottle.Period.MINUTE)
        response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 60)
        self.assertEqual(BugReport.objects.count(), 3)
        quota = SubmissionThrottle.objects.get(
            identifier=get_identity_hash("ip:192.0.2.80"),
            period=SubmissionThrottle.Period.HOUR,
        )
        self.assertEqual(quota.submission_count, 3)

    def test_authenticated_hourly_quota_is_five(self):
        self.client.force_login(self.member)
        for _ in range(5):
            self.assertEqual(self.submit().status_code, 302)
            self.shift_window(SubmissionThrottle.Period.MINUTE)
        response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response["Retry-After"]), 60)
        self.assertEqual(BugReport.objects.count(), 5)

    def test_hourly_window_expires(self):
        for _ in range(3):
            self.assertEqual(self.submit().status_code, 302)
            self.shift_window(SubmissionThrottle.Period.MINUTE)
        self.assertEqual(self.submit().status_code, 429)
        self.shift_window(SubmissionThrottle.Period.HOUR, minutes=61)
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(BugReport.objects.count(), 4)

    def test_different_anonymous_addresses_have_independent_quotas(self):
        self.assertEqual(self.submit(address="192.0.2.81").status_code, 302)
        self.assertEqual(self.submit(address="192.0.2.82").status_code, 302)
        self.assertEqual(self.submit(address="192.0.2.81").status_code, 429)

    def test_authenticated_accounts_have_independent_quotas(self):
        other = User.objects.create_user(
            username="other_throttle_member",
            password="TestPassword123!",
        )
        self.client.force_login(self.member)
        self.assertEqual(self.submit().status_code, 302)
        self.client.force_login(other)
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(BugReport.objects.count(), 2)

    def test_invalid_form_does_not_consume_quota(self):
        response = self.client.post(
            self.report_url,
            {"description": "Short"},
            REMOTE_ADDR="192.0.2.80",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SubmissionThrottle.objects.exists())
        self.assertEqual(self.submit().status_code, 302)

    def test_failed_audit_rolls_back_quota(self):
        with patch(
            "feedback.services.record_audit_event",
            side_effect=IntegrityError("Simulated audit failure"),
        ):
            with self.assertRaises(IntegrityError):
                self.submit()
        self.assertFalse(SubmissionThrottle.objects.exists())
        self.assertEqual(BugReport.objects.count(), 0)
        self.assertEqual(self.submit().status_code, 302)

    def test_failed_notification_rolls_back_quota(self):
        with patch(
            "feedback.services.create_notifications",
            side_effect=IntegrityError("Simulated notification failure"),
        ):
            with self.assertRaises(IntegrityError):
                self.submit()
        self.assertFalse(SubmissionThrottle.objects.exists())
        self.assertEqual(self.submit().status_code, 302)

    @override_settings(AUDIT_TRUSTED_PROXY_CIDRS=())
    def test_untrusted_forwarded_header_cannot_bypass_quota(self):
        self.assertEqual(
            self.submit(HTTP_X_FORWARDED_FOR="198.51.100.1").status_code,
            302,
        )
        self.assertEqual(
            self.submit(HTTP_X_FORWARDED_FOR="198.51.100.2").status_code,
            429,
        )

    @override_settings(AUDIT_TRUSTED_PROXY_CIDRS=("10.0.0.0/8",))
    def test_trusted_proxy_uses_distinct_forwarded_client_addresses(self):
        self.assertEqual(
            self.submit(
                address="10.0.0.5",
                HTTP_X_FORWARDED_FOR="198.51.100.1",
            ).status_code,
            302,
        )
        self.assertEqual(
            self.submit(
                address="10.0.0.5",
                HTTP_X_FORWARDED_FOR="198.51.100.2",
            ).status_code,
            302,
        )
        self.assertEqual(
            self.submit(
                address="10.0.0.5",
                HTTP_X_FORWARDED_FOR="198.51.100.1",
            ).status_code,
            429,
        )

    def test_missing_client_ip_is_rejected_without_adding_quota(self):
        response = self.submit(address="")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")
        self.assertFalse(SubmissionThrottle.objects.exists())

    def test_identity_hash_is_keyed_and_deterministic(self):
        identity = "ip:192.0.2.80"
        value = get_identity_hash(identity)
        self.assertEqual(len(value), 64)
        self.assertEqual(value, get_identity_hash(identity))
        self.assertNotEqual(value, identity)
        with override_settings(SECRET_KEY="distinct-test-signing-key"):
            self.assertNotEqual(value, get_identity_hash(identity))


class BugReportRateLimitConcurrencyTests(TransactionTestCase):
    def test_simultaneous_submissions_cannot_exceed_minute_quota(self):
        barrier = Barrier(2)
        factory = RequestFactory()

        def submit_once():
            close_old_connections()
            try:
                request = factory.post(
                    "/feedback/report/",
                    REMOTE_ADDR="192.0.2.99",
                )
                request.user = AnonymousUser()
                barrier.wait(timeout=10)
                try:
                    create_bug_report(
                        report=BugReport(
                            description="Concurrent test submission for quota enforcement."
                        ),
                        request=request,
                    )
                    return "created"
                except SubmissionRateLimitExceeded:
                    return "limited"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit_once(), range(2)))

        self.assertCountEqual(results, ["created", "limited"])
        self.assertEqual(BugReport.objects.count(), 1)
        self.assertEqual(
            AuditLog.objects.filter(target_type="BugReport").count(), 1
        )
        self.assertEqual(
            SubmissionThrottle.objects.get(
                identifier=get_identity_hash("ip:192.0.2.99"),
                period=SubmissionThrottle.Period.MINUTE,
            ).submission_count,
            1,
        )
