
from django.contrib.auth import get_user_model
from django.test import (
    RequestFactory,
    SimpleTestCase,
    TestCase,
    override_settings,
)

from .models import AuditLog
from .services import (
    get_request_ip,
    record_audit_event,
)


User = get_user_model()


class RequestIPTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def make_request(
        self,
        remote_address,
        forwarded_for=None,
    ):
        metadata = {
            "REMOTE_ADDR": remote_address,
        }

        if forwarded_for is not None:
            metadata["HTTP_X_FORWARDED_FOR"] = (
                forwarded_for
            )

        return self.factory.get(
            "/resources/",
            **metadata,
        )

    def test_none_request(self):
        self.assertIsNone(
            get_request_ip(None)
        )

    def test_missing_remote_address(self):
        request = self.make_request("")

        self.assertIsNone(
            get_request_ip(request)
        )

    def test_invalid_remote_address(self):
        request = self.make_request(
            "not-an-ip",
            "203.0.113.100",
        )

        self.assertIsNone(
            get_request_ip(request)
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=(),
    )
    def test_direct_request_ignores_forwarded_header(self):
        request = self.make_request(
            "198.51.100.8",
            "203.0.113.100",
        )

        self.assertEqual(
            get_request_ip(request),
            "198.51.100.8",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.2",),
    )
    def test_untrusted_source_cannot_spoof_ip(self):
        request = self.make_request(
            "198.51.100.8",
            "203.0.113.100",
        )

        self.assertEqual(
            get_request_ip(request),
            "198.51.100.8",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.2",),
    )
    def test_trusted_proxy_uses_forwarded_client(self):
        request = self.make_request(
            "10.30.0.2",
            "198.51.100.8",
        )

        self.assertEqual(
            get_request_ip(request),
            "198.51.100.8",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.0/24",),
    )
    def test_spoofed_leftmost_address_is_ignored(self):
        request = self.make_request(
            "10.30.0.2",
            "203.0.113.100, 198.51.100.8, 10.30.0.3",
        )

        self.assertEqual(
            get_request_ip(request),
            "198.51.100.8",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.2",),
    )
    def test_trusted_proxy_without_header_uses_remote(self):
        request = self.make_request(
            "10.30.0.2",
        )

        self.assertEqual(
            get_request_ip(request),
            "10.30.0.2",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.2",),
    )
    def test_invalid_forwarded_header_uses_remote(self):
        request = self.make_request(
            "10.30.0.2",
            "not-an-ip",
        )

        self.assertEqual(
            get_request_ip(request),
            "10.30.0.2",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.0/24",),
    )
    def test_malformed_address_in_proxy_chain(self):
        request = self.make_request(
            "10.30.0.2",
            "198.51.100.8, invalid, 10.30.0.3",
        )

        self.assertEqual(
            get_request_ip(request),
            "10.30.0.2",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.2",),
    )
    def test_all_trusted_addresses_use_remote(self):
        request = self.make_request(
            "10.30.0.2",
            "10.30.0.2",
        )

        self.assertEqual(
            get_request_ip(request),
            "10.30.0.2",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("2001:db8::2",),
    )
    def test_ipv6_forwarded_client(self):
        request = self.make_request(
            "2001:db8::2",
            "2001:db8:1::100",
        )

        self.assertEqual(
            get_request_ip(request),
            "2001:db8:1::100",
        )

    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("2001:db8::2",),
    )
    def test_untrusted_ipv6_cannot_spoof_ip(self):
        request = self.make_request(
            "2001:db8:1::100",
            "2001:db8:ffff::999",
        )

        self.assertEqual(
            get_request_ip(request),
            "2001:db8:1::100",
        )


class AuditIPPersistenceTests(TestCase):
    @override_settings(
        AUDIT_TRUSTED_PROXY_CIDRS=("10.30.0.2",),
    )
    def test_spoofed_ip_not_saved_in_audit_log(self):
        request = RequestFactory().get(
            "/resources/",
            REMOTE_ADDR="198.51.100.8",
            HTTP_X_FORWARDED_FOR="203.0.113.100",
        )

        audit_log = record_audit_event(
            action=AuditLog.Action.CREATE,
            target_type="Resource",
            target_id="1",
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
            request=request,
        )

        audit_log.refresh_from_db()

        self.assertEqual(
            audit_log.ip_address,
            "198.51.100.8",
        )

        self.assertEqual(
            audit_log.request_path,
            "/resources/",
        )


class AuditActorNameTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = User.objects.create_user(
            username="audit_actor",
            password="test-password",
            first_name="Personal",
            last_name="Name",
            display_name="Display Name",
            eldvatten_name="EldVatten Name",
        )

    def create_audit_log(self, actor=None):
        return record_audit_event(
            action=AuditLog.Action.CREATE,
            target_type="Resource",
            target_id="42",
            source=AuditLog.Source.WEB_APP,
            method=AuditLog.Method.MANUAL,
            actor=actor,
        )

    def test_eldvatten_name_takes_precedence(self):
        audit_log = self.create_audit_log(
            actor=self.actor,
        )

        self.assertEqual(
            audit_log.actor_label,
            "EldVatten Name",
        )

    def test_display_name_fallback(self):
        self.actor.eldvatten_name = ""

        audit_log = self.create_audit_log(
            actor=self.actor,
        )

        self.assertEqual(
            audit_log.actor_label,
            "Display Name",
        )

    def test_personal_name_fallback(self):
        self.actor.eldvatten_name = "   "
        self.actor.display_name = ""

        audit_log = self.create_audit_log(
            actor=self.actor,
        )

        self.assertEqual(
            audit_log.actor_label,
            "Personal Name",
        )

    def test_username_fallback(self):
        self.actor.eldvatten_name = ""
        self.actor.display_name = ""
        self.actor.first_name = ""
        self.actor.last_name = ""

        audit_log = self.create_audit_log(
            actor=self.actor,
        )

        self.assertEqual(
            audit_log.actor_label,
            "audit_actor",
        )

    def test_actor_identity_is_preserved(self):
        audit_log = self.create_audit_log(
            actor=self.actor,
        )

        audit_log.refresh_from_db()

        self.assertEqual(
            audit_log.actor_id,
            self.actor.pk,
        )

        self.assertEqual(
            audit_log.actor_label,
            "EldVatten Name",
        )

    def test_actor_label_is_historical_snapshot(self):
        audit_log = self.create_audit_log(
            actor=self.actor,
        )

        self.actor.eldvatten_name = "Renamed Member"
        self.actor.save(
            update_fields=["eldvatten_name"],
        )

        audit_log.refresh_from_db()

        self.assertEqual(
            audit_log.actor_id,
            self.actor.pk,
        )

        self.assertEqual(
            audit_log.actor_label,
            "EldVatten Name",
        )

        new_audit_log = self.create_audit_log(
            actor=self.actor,
        )

        self.assertEqual(
            new_audit_log.actor_label,
            "Renamed Member",
        )
