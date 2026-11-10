
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import AccountStatus, User
from audit.models import AuditLog

from .forms import BugReportForm
from .models import BugReport
from .services import create_bug_report
from .views import report_bug


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
