import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Notification, NotificationPreference, PushSubscription
from .services import (
    create_notifications,
    get_unread_notification_count,
    get_unread_notifications,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_notification_unread,
    send_push_notification,
    send_push_to_subscription,
)
from .views import get_notification_return_url


User = get_user_model()


class NotificationFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(
            username="notification_member",
            password="test-password",
        )
        cls.other = User.objects.create_user(
            username="notification_other",
            password="test-password",
        )

    def setUp(self):
        self.client.force_login(self.member)

    def notification(self, user=None, **fields):
        values = {
            "notification_type": Notification.Type.MESSAGE,
            "title": "A message arrived",
            "message": "Notification body",
            "target_url": "/messages/",
        }
        values.update(fields)
        return Notification.objects.create(user=user or self.member, **values)

    def subscription(self, user=None, **fields):
        values = {
            "endpoint": "https://push.example.invalid/one",
            "p256dh_key": "public-key",
            "auth_key": "auth-key",
        }
        values.update(fields)
        return PushSubscription.objects.create(user=user or self.member, **values)

    def json_post(self, name, data, *, user=None):
        if user is not None:
            self.client.force_login(user)
        return self.client.post(
            reverse(f"notifications:{name}"),
            data=json.dumps(data),
            content_type="application/json",
        )


class NotificationServiceTests(NotificationFixture):
    def test_creation_deduplicates_recipients_and_skips_invalid_recipients(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            created = create_notifications(
                recipients=[self.member, self.member, self.other, None, User()],
                notification_type=Notification.Type.MESSAGE,
                title="Incoming message",
                source_type="message",
                source_id=123,
                target_url="/messages/123/",
            )
        self.assertEqual(len(created), 2)
        self.assertEqual(set(Notification.objects.values_list("user_id", flat=True)), {self.member.pk, self.other.pk})
        self.assertEqual(len(callbacks), 1)
        self.assertTrue(all(item.source_id == "123" for item in created))

    def test_creation_with_no_recipients_does_not_write_or_schedule_push(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            result = create_notifications(
                recipients=[None, User()],
                notification_type=Notification.Type.MESSAGE,
                title="Unused",
            )
        self.assertEqual(result, [])
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(callbacks, [])

    def test_disabled_global_push_preference_preserves_in_app_notification(self):
        NotificationPreference.objects.create(user=self.member, push_enabled=False)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            created = create_notifications(
                recipients=[self.member],
                notification_type=Notification.Type.MESSAGE,
                title="Test",
            )
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].push_requested)
        self.assertEqual(callbacks, [])

    def test_type_specific_push_preference(self):
        NotificationPreference.objects.create(user=self.member, message_push=False, event_push=True)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            message = create_notifications(
                recipients=[self.member], notification_type=Notification.Type.MESSAGE, title="Message"
            )[0]
            event = create_notifications(
                recipients=[self.member], notification_type=Notification.Type.EVENT, title="Event"
            )[0]
        self.assertFalse(message.push_requested)
        self.assertTrue(event.push_requested)
        self.assertEqual(len(callbacks), 1)

    def test_notification_creation_schedules_push_after_commit(self):
        with patch("notifications.services.send_push_notifications") as send:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                create_notifications(
                    recipients=[self.member], notification_type=Notification.Type.MESSAGE,
                    title="Push this",
                )
            self.assertEqual(len(callbacks), 1)
            send.assert_called_once()

    def test_mark_read_is_idempotent(self):
        item = self.notification()
        mark_notification_read(item)
        first_read_at = item.read_at
        self.assertTrue(item.is_read)
        self.assertIsNotNone(first_read_at)
        mark_notification_read(item)
        item.refresh_from_db()
        self.assertEqual(item.read_at, first_read_at)

    def test_mark_unread_is_idempotent(self):
        item = self.notification(is_read=True, read_at=timezone.now())
        mark_notification_unread(item)
        self.assertFalse(item.is_read)
        self.assertIsNone(item.read_at)
        mark_notification_unread(item)
        item.refresh_from_db()
        self.assertIsNone(item.read_at)

    def test_mark_all_read_only_updates_owners_unread_notifications(self):
        mine = self.notification()
        already_read = self.notification(is_read=True, read_at=timezone.now())
        other = self.notification(user=self.other)
        self.assertEqual(mark_all_notifications_read(self.member), 1)
        mine.refresh_from_db()
        already_read.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(mine.is_read)
        self.assertIsNotNone(mine.read_at)
        self.assertTrue(already_read.is_read)
        self.assertFalse(other.is_read)
        self.assertEqual(mark_all_notifications_read(self.member), 0)

    def test_query_helpers_filter_by_owner_read_state_and_type(self):
        mine_unread = self.notification(notification_type=Notification.Type.MESSAGE)
        mine_read = self.notification(notification_type=Notification.Type.EVENT, is_read=True, read_at=timezone.now())
        self.notification(user=self.other)
        self.assertEqual(get_unread_notification_count(self.member), 1)
        self.assertEqual(list(get_unread_notifications(self.member)), [mine_unread])
        self.assertEqual(set(get_user_notifications(self.member)), {mine_unread, mine_read})
        self.assertEqual(list(get_user_notifications(self.member, read_state="unread")), [mine_unread])
        self.assertEqual(list(get_user_notifications(self.member, read_state="read")), [mine_read])
        self.assertEqual(list(get_user_notifications(self.member, notification_type=Notification.Type.EVENT)), [mine_read])

    def test_invalid_type_filter_does_not_remove_notifications(self):
        item = self.notification()
        self.assertEqual(list(get_user_notifications(self.member, notification_type="NOT_A_TYPE")), [item])


class NotificationHTTPTests(NotificationFixture):
    def test_list_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("notifications:notification_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_contains_only_current_users_notifications(self):
        mine = self.notification()
        self.notification(user=self.other, title="Other user's secret")
        response = self.client.get(reverse("notifications:notification_list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(mine, response.context["notifications"])
        self.assertEqual(response.context["unread_count"], 1)
        self.assertNotContains(response, "Other user's secret")

    def test_open_marks_read_and_redirects_to_target(self):
        item = self.notification()
        response = self.client.get(reverse("notifications:notification_open", args=[item.pk]))
        self.assertRedirects(response, "/messages/", fetch_redirect_response=False)
        item.refresh_from_db()
        self.assertTrue(item.is_read)

    def test_open_without_target_uses_safe_next(self):
        item = self.notification(target_url="")
        response = self.client.get(reverse("notifications:notification_open", args=[item.pk]), {"next": "/home/"})
        self.assertRedirects(response, "/home/", fetch_redirect_response=False)

    def test_open_without_target_rejects_external_next(self):
        item = self.notification(target_url="")
        response = self.client.get(reverse("notifications:notification_open", args=[item.pk]), {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("notifications:notification_list"))

    def test_other_users_notification_cannot_be_opened(self):
        item = self.notification(user=self.other)
        response = self.client.get(reverse("notifications:notification_open", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertFalse(item.is_read)

    def test_mark_read_requires_post_and_does_not_modify_on_get(self):
        item = self.notification()
        response = self.client.get(reverse("notifications:notification_mark_read", args=[item.pk]))
        self.assertRedirects(response, reverse("notifications:notification_list"))
        item.refresh_from_db()
        self.assertFalse(item.is_read)

    def test_mark_read_and_unread_roundtrip(self):
        item = self.notification()
        self.client.post(reverse("notifications:notification_mark_read", args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.is_read)
        self.client.post(reverse("notifications:notification_mark_unread", args=[item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.is_read)
        self.assertIsNone(item.read_at)

    def test_cannot_mark_someone_elses_notification(self):
        item = self.notification(user=self.other)
        for name in ("notification_mark_read", "notification_mark_unread"):
            with self.subTest(name=name):
                response = self.client.post(reverse(f"notifications:{name}", args=[item.pk]))
                self.assertEqual(response.status_code, 404)

    def test_mark_all_read_only_changes_current_users_notifications(self):
        mine = self.notification()
        other = self.notification(user=self.other)
        response = self.client.post(reverse("notifications:notification_mark_all_read"))
        self.assertRedirects(response, reverse("notifications:notification_list"))
        mine.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(mine.is_read)
        self.assertFalse(other.is_read)

    def test_mark_all_read_get_does_nothing(self):
        mine = self.notification()
        response = self.client.get(reverse("notifications:notification_mark_all_read"))
        self.assertRedirects(response, reverse("notifications:notification_list"))
        mine.refresh_from_db()
        self.assertFalse(mine.is_read)

    def test_safe_return_url_rejects_protocol_relative_urls(self):
        factory = RequestFactory()
        request = factory.post("/notifications/", {"next": "//evil.example/path"}, HTTP_HOST="testserver")
        self.assertIsNone(get_notification_return_url(request))
        request = factory.post("/notifications/", {"next": "/safe/path"}, HTTP_HOST="testserver")
        self.assertEqual(get_notification_return_url(request), "/safe/path")

    def test_settings_creation_and_update(self):
        url = reverse("notifications:notification_settings")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(NotificationPreference.objects.filter(user=self.member).exists())
        values = {name: "on" for name in (
            "push_enabled", "event_push", "message_push", "community_push", "account_push", "system_push"
        )}
        response = self.client.post(url, values)
        self.assertRedirects(response, url)
        settings = NotificationPreference.objects.get(user=self.member)
        self.assertFalse(settings.action_push)
        self.assertFalse(settings.vote_push)
        self.assertTrue(settings.message_push)

    def test_settings_update_endpoint_requires_post(self):
        response = self.client.get(reverse("notifications:notification_preferences_update"))
        self.assertEqual(response.status_code, 405)


class PushSubscriptionHTTPTests(NotificationFixture):
    def test_push_endpoints_require_login(self):
        self.client.logout()
        for name in ("push_public_key", "push_subscribe", "push_status", "push_set_enabled", "push_set_active", "push_pause", "push_reset_pause"):
            with self.subTest(name=name):
                url = reverse(f"notifications:{name}")
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)

    def test_push_public_key_uses_configured_key(self):
        with override_settings(VAPID_PUBLIC_KEY="test-public-key"):
            response = self.client.get(reverse("notifications:push_public_key"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["public_key"], "test-public-key")

    def test_subscribe_rejects_missing_keys(self):
        response = self.json_post("push_subscribe", {"endpoint": "https://push.example.invalid/one"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushSubscription.objects.exists())

    def test_subscribe_creates_and_upserts_same_device(self):
        payload = {
            "endpoint": "https://push.example.invalid/one",
            "keys": {"p256dh": "first-key", "auth": "auth-token"},
            "device_name": "Test browser",
        }
        response = self.json_post("push_subscribe", payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["created"])
        self.member.refresh_from_db()
        self.assertTrue(self.member.push_prompt_seen)
        payload["keys"]["p256dh"] = "new-key"
        response = self.json_post("push_subscribe", payload)
        self.assertFalse(response.json()["created"])
        self.assertEqual(PushSubscription.objects.filter(user=self.member).count(), 1)
        self.assertEqual(PushSubscription.objects.get(user=self.member).p256dh_key, "new-key")

    def test_subscribe_is_isolated_by_user(self):
        payload = {"endpoint": "https://push.example.invalid/shared", "keys": {"p256dh": "key", "auth": "auth"}}
        self.json_post("push_subscribe", payload)
        self.json_post("push_subscribe", payload, user=self.other)
        self.assertEqual(PushSubscription.objects.filter(endpoint=payload["endpoint"]).count(), 2)

    def test_status_for_unknown_device(self):
        response = self.json_post("push_status", {"endpoint": "not-registered"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["registered"])

    def test_status_reflects_pause_and_enabled_flags(self):
        device = self.subscription(paused_until=timezone.now() + timedelta(hours=2), enabled=False, active=False)
        response = self.json_post("push_status", {"endpoint": device.endpoint})
        self.assertTrue(response.json()["registered"])
        self.assertTrue(response.json()["paused"])
        self.assertFalse(response.json()["enabled"])
        self.assertFalse(response.json()["active"])

    def test_cannot_toggle_another_users_device(self):
        device = self.subscription(user=self.other)
        for name, data in (
            ("push_set_enabled", {"endpoint": device.endpoint, "enabled": False}),
            ("push_set_active", {"endpoint": device.endpoint, "active": False}),
            ("push_pause", {"endpoint": device.endpoint, "hours": 2}),
            ("push_reset_pause", {"endpoint": device.endpoint}),
        ):
            with self.subTest(name=name):
                response = self.json_post(name, data)
                self.assertEqual(response.status_code, 404)

    def test_disabling_device_deactivates_it(self):
        device = self.subscription()
        response = self.json_post("push_set_enabled", {"endpoint": device.endpoint, "enabled": False})
        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertFalse(device.enabled)
        self.assertFalse(device.active)

    def test_cannot_activate_disabled_device(self):
        device = self.subscription(enabled=False, active=False)
        response = self.json_post("push_set_active", {"endpoint": device.endpoint, "active": True})
        self.assertEqual(response.status_code, 409)
        device.refresh_from_db()
        self.assertFalse(device.active)

    def test_enable_then_activate_device(self):
        device = self.subscription(enabled=False, active=False)
        self.json_post("push_set_enabled", {"endpoint": device.endpoint, "enabled": True})
        response = self.json_post("push_set_active", {"endpoint": device.endpoint, "active": True})
        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertTrue(device.active)

    def test_pause_and_reset_device(self):
        device = self.subscription()
        response = self.json_post("push_pause", {"endpoint": device.endpoint, "hours": 3})
        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertGreater(device.paused_until, timezone.now())
        response = self.json_post("push_reset_pause", {"endpoint": device.endpoint})
        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertIsNone(device.paused_until)

    def test_pause_rejects_invalid_duration(self):
        device = self.subscription()
        for hours in (0, 25, "2"):
            with self.subTest(hours=hours):
                response = self.json_post("push_pause", {"endpoint": device.endpoint, "hours": hours})
                self.assertEqual(response.status_code, 400)
        device.refresh_from_db()
        self.assertIsNone(device.paused_until)

    def test_invalid_json_is_rejected_by_push_mutation_endpoints(self):
        for name in ("push_subscribe", "push_status", "push_set_enabled", "push_set_active", "push_pause", "push_reset_pause"):
            with self.subTest(name=name):
                response = self.client.post(reverse(f"notifications:{name}"), data="{", content_type="application/json")
                self.assertEqual(response.status_code, 400)

    def test_push_mutation_endpoints_require_post(self):
        for name in ("push_subscribe", "push_status", "push_set_enabled", "push_set_active", "push_pause", "push_reset_pause"):
            with self.subTest(name=name):
                response = self.client.get(reverse(f"notifications:{name}"))
                self.assertEqual(response.status_code, 405)


class PushDispatchTests(NotificationFixture):
    def test_push_dispatch_ignores_disabled_inactive_and_paused_devices(self):
        good = self.subscription(endpoint="https://push.example.invalid/good")
        self.subscription(endpoint="https://push.example.invalid/disabled", enabled=False)
        self.subscription(endpoint="https://push.example.invalid/inactive", active=False)
        self.subscription(endpoint="https://push.example.invalid/paused", paused_until=timezone.now() + timedelta(hours=1))
        item = self.notification()
        with patch("notifications.services.send_push_to_subscription") as dispatch:
            send_push_notification(item)
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(dispatch.call_args.kwargs["subscription"].pk, good.pk)
        payload = json.loads(dispatch.call_args.kwargs["payload"])
        self.assertEqual(payload["title"], item.title)
        self.assertEqual(payload["target_url"], item.target_url)

    @override_settings(VAPID_PRIVATE_KEY="dummy-private-key", VAPID_SUBJECT="mailto:test@example.invalid")
    def test_expired_push_subscription_is_deactivated(self):
        device = self.subscription()
        exception = SimpleNamespace(response=SimpleNamespace(status_code=410))
        from pywebpush import WebPushException
        with patch("notifications.services.webpush", side_effect=WebPushException("expired", response=exception.response)):
            send_push_to_subscription(subscription=device, payload="{}")
        device.refresh_from_db()
        self.assertFalse(device.active)

    @override_settings(VAPID_PRIVATE_KEY="dummy-private-key", VAPID_SUBJECT="mailto:test@example.invalid")
    def test_transient_push_error_does_not_deactivate_subscription(self):
        device = self.subscription()
        from pywebpush import WebPushException
        with patch("notifications.services.webpush", side_effect=WebPushException("failure", response=SimpleNamespace(status_code=503))):
            send_push_to_subscription(subscription=device, payload="{}")
        device.refresh_from_db()
        self.assertTrue(device.active)
