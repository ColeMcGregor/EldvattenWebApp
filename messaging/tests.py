
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus, User
from audit.models import AuditLog
from notifications.models import Notification
from organization.models import Chapter, ChapterStatus, CitizenshipClass, CitizenshipRecord

from .forms import ConversationForm, ConversationTargetFormSet, MessageForm
from .models import (
    Conversation,
    ConversationParticipant,
    ConversationTarget,
    Message,
    MessageRead,
    UserBlock,
)
from .services import (
    get_accessible_conversations,
    get_conversation_display_title,
    get_message_recipient_users,
    get_unread_message_count,
    get_visible_messages,
    resolve_conversation_targets,
    send_conversation_message,
    set_conversation_muted,
    user_can_access_conversation,
    user_is_conversation_muted,
    users_are_blocked,
)


class MessagingFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(
            username="message_alice",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            display_name="Alice Display",
            eldvatten_name="Astrid",
        )
        cls.bob = User.objects.create_user(
            username="message_bob",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            display_name="Bob Display",
            eldvatten_name="Bjorn",
        )
        cls.cara = User.objects.create_user(
            username="message_cara",
            password="test-password",
            account_status=AccountStatus.MEMBER,
            display_name="Cara Display",
        )
        cls.dan = User.objects.create_user(
            username="message_dan",
            password="test-password",
            account_status=AccountStatus.MEMBER,
        )
        cls.pending = User.objects.create_user(
            username="message_pending",
            account_status=AccountStatus.PENDING,
        )
        cls.inactive = User.objects.create_user(
            username="message_inactive",
            account_status=AccountStatus.MEMBER,
            is_active=False,
        )
        cls.chapter_status = ChapterStatus.objects.create(name="Messaging Active")
        cls.chapter = Chapter.objects.create(
            name="Messaging Chapter", status=cls.chapter_status,
        )
        cls.other_chapter = Chapter.objects.create(
            name="Other Messaging Chapter", status=cls.chapter_status,
        )
        cls.citizenship = CitizenshipClass.objects.create(name="Messaging Citizen")
        cls.alternate_citizenship = CitizenshipClass.objects.create(name="Messaging Guest")
        for user, chapter, citizenship in (
            (cls.alice, cls.chapter, cls.citizenship),
            (cls.bob, cls.chapter, cls.citizenship),
            (cls.cara, cls.other_chapter, cls.citizenship),
            (cls.dan, cls.chapter, cls.alternate_citizenship),
        ):
            CitizenshipRecord.objects.create(
                user=user,
                chapter=chapter,
                citizenship_class=citizenship,
                started_at=timezone.localdate(),
                changed_by=cls.alice,
            )

    def direct(self, *people):
        conversation = Conversation.objects.create(
            conversation_type=Conversation.ConversationType.DIRECT,
        )
        for person in people:
            ConversationParticipant.objects.create(
                conversation=conversation, user=person,
            )
        return conversation

    def group(self, *, chapter=None, citizenship_class=None, title="Chapter Chat"):
        conversation = Conversation.objects.create(
            conversation_type=Conversation.ConversationType.GROUP,
            title=title,
        )
        ConversationTarget.objects.create(
            conversation=conversation,
            chapter=chapter or self.chapter,
            citizenship_class=citizenship_class,
        )
        return conversation

    def url(self, name, *args):
        return reverse(f"messaging:{name}", args=args)


class MessagingModelTests(MessagingFixture):
    def test_group_requires_nonblank_title(self):
        conversation = Conversation(
            conversation_type=Conversation.ConversationType.GROUP,
            title="   ",
        )
        with self.assertRaises(ValidationError):
            conversation.full_clean()

    def test_group_target_requires_at_least_one_selector(self):
        conversation = self.group()
        with self.assertRaises(ValidationError):
            ConversationTarget(conversation=conversation).full_clean()

    def test_user_cannot_block_self(self):
        with self.assertRaises(ValidationError):
            UserBlock(blocker=self.alice, blocked=self.alice).full_clean()

    def test_direct_participant_and_read_record_are_unique(self):
        conversation = self.direct(self.alice, self.bob)
        self.assertEqual(conversation.participants.count(), 2)
        message = Message.objects.create(
            conversation=conversation, sender=self.alice, body="Hello",
        )
        MessageRead.objects.create(message=message, user=self.bob)
        self.assertEqual(MessageRead.objects.filter(message=message, user=self.bob).count(), 1)


class MessagingIdentityTests(MessagingFixture):
    def test_direct_title_prefers_eldvatten_name(self):
        conversation = self.direct(self.alice, self.bob)
        self.assertEqual(get_conversation_display_title(conversation, self.alice), "Bjorn")
        self.assertEqual(get_conversation_display_title(conversation, self.bob), "Astrid")

    def test_direct_title_uses_name_fallback_and_tracks_rename(self):
        conversation = self.direct(self.alice, self.cara)
        self.assertEqual(get_conversation_display_title(conversation, self.alice), "Cara Display")
        self.cara.eldvatten_name = "Celeste"
        self.cara.save(update_fields=["eldvatten_name"])
        self.assertEqual(get_conversation_display_title(conversation, self.alice), "Celeste")

    def test_direct_title_uses_username_when_names_are_empty(self):
        conversation = self.direct(self.alice, self.dan)
        self.assertEqual(get_conversation_display_title(conversation, self.alice), "message_dan")

    def test_group_title_does_not_change_with_member_names(self):
        conversation = self.group(title="Fire Council")
        self.assertEqual(get_conversation_display_title(conversation, self.alice), "Fire Council")

    def test_participant_selector_labels_and_order_use_community_names(self):
        form = ConversationForm(current_user=self.alice)
        field = form.fields["participants"]
        self.assertEqual(
            list(field.queryset.values_list("pk", flat=True)),
            [self.bob.pk, self.cara.pk, self.dan.pk],
        )
        self.assertEqual(field.label_from_instance(self.bob), "Bjorn (@message_bob)")
        self.assertEqual(field.label_from_instance(self.cara), "Cara Display (@message_cara)")
        self.assertEqual(field.label_from_instance(self.dan), "@message_dan")

    def test_selector_sort_uses_eldvatten_name_before_display_name(self):
        self.bob.eldvatten_name = "Zora"
        self.bob.save(update_fields=["eldvatten_name"])
        form = ConversationForm(current_user=self.alice)
        self.assertEqual(
            list(form.fields["participants"].queryset.values_list("pk", flat=True)),
            [self.cara.pk, self.dan.pk, self.bob.pk],
        )

    def test_selector_excludes_self_inactive_pending_and_blocked_users(self):
        UserBlock.objects.create(blocker=self.bob, blocked=self.alice)
        field = ConversationForm(current_user=self.alice).fields["participants"]
        ids = set(field.queryset.values_list("pk", flat=True))
        self.assertEqual(ids, {self.cara.pk, self.dan.pk})

    def test_direct_detail_displays_community_name_and_sender(self):
        conversation = self.direct(self.alice, self.bob)
        Message.objects.create(conversation=conversation, sender=self.bob, body="Unique hello")
        self.client.force_login(self.alice)
        response = self.client.get(self.url("conversation_detail", conversation.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["conversation"].display_title, "Bjorn")
        self.assertContains(response, "Bjorn")
        self.assertContains(response, "Unique hello")

    def test_sidebar_preview_uses_sender_community_name(self):
        conversation = self.direct(self.alice, self.bob)
        Message.objects.create(conversation=conversation, sender=self.bob, body="Preview sentinel")
        self.client.force_login(self.alice)
        response = self.client.get(self.url("conversation_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bjorn:")
        self.assertContains(response, "Preview sentinel")


class MessagingFormTests(MessagingFixture):
    def test_direct_form_requires_participant(self):
        form = ConversationForm(data={"conversation_type": "DIRECT"}, current_user=self.alice)
        self.assertFalse(form.is_valid())
        self.assertIn("participants", form.errors)

    def test_direct_form_accepts_member_and_clears_title(self):
        form = ConversationForm(
            data={"conversation_type": "DIRECT", "title": "Discard", "participants": [self.bob.pk]},
            current_user=self.alice,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["title"], "")

    def test_group_form_requires_title_and_forbids_individual_participants(self):
        form = ConversationForm(
            data={"conversation_type": "GROUP", "title": "", "participants": [self.bob.pk]},
            current_user=self.alice,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("title", form.errors)
        self.assertIn("participants", form.errors)

    def test_message_form_rejects_empty_body(self):
        form = MessageForm(data={"body": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("body", form.errors)

    def test_group_target_formset_requires_selector(self):
        conversation = Conversation(conversation_type="GROUP", title="Named group")
        formset = ConversationTargetFormSet(
            data={
                "targets-TOTAL_FORMS": "1", "targets-INITIAL_FORMS": "0",
                "targets-MIN_NUM_FORMS": "0", "targets-MAX_NUM_FORMS": "1000",
            },
            instance=conversation,
            prefix="targets",
        )
        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors())


class MessagingAccessTests(MessagingFixture):
    def test_direct_access_requires_active_participation(self):
        conversation = self.direct(self.alice, self.bob)
        self.assertTrue(user_can_access_conversation(self.alice, conversation))
        self.assertFalse(user_can_access_conversation(self.cara, conversation))
        participation = conversation.participants.get(user=self.alice)
        participation.left_at = timezone.now()
        participation.save(update_fields=["left_at"])
        self.assertFalse(user_can_access_conversation(self.alice, conversation))

    def test_pending_inactive_and_anonymous_users_have_no_access(self):
        conversation = self.direct(self.alice, self.bob, self.pending, self.inactive)
        for person in (self.pending, self.inactive, AnonymousUser()):
            with self.subTest(person=str(person)):
                self.assertFalse(user_can_access_conversation(person, conversation))
                self.assertFalse(get_accessible_conversations(person).exists())

    def test_group_access_uses_current_organization_target_membership(self):
        conversation = self.group(chapter=self.chapter, citizenship_class=self.citizenship)
        self.assertEqual(resolve_conversation_targets(conversation), {self.alice.pk, self.bob.pk})
        for person, allowed in ((self.alice, True), (self.bob, True), (self.cara, False), (self.dan, False)):
            with self.subTest(user=person.username):
                self.assertEqual(user_can_access_conversation(person, conversation), allowed)

    def test_ended_membership_removes_group_access(self):
        conversation = self.group()
        membership = CitizenshipRecord.objects.get(user=self.bob, chapter=self.chapter)
        membership.ended_at = timezone.localdate()
        membership.save(update_fields=["ended_at"])
        self.assertFalse(user_can_access_conversation(self.bob, conversation))
        self.assertTrue(user_can_access_conversation(self.alice, conversation))

    def test_changing_eldvatten_name_does_not_change_access_or_recipient_ids(self):
        conversation = self.direct(self.alice, self.bob)
        before = list(get_message_recipient_users(conversation=conversation, sender=self.alice).values_list("pk", flat=True))
        self.bob.eldvatten_name = "Renamed Bjorn"
        self.bob.save(update_fields=["eldvatten_name"])
        after = list(get_message_recipient_users(conversation=conversation, sender=self.alice).values_list("pk", flat=True))
        self.assertEqual(before, [self.bob.pk])
        self.assertEqual(after, before)
        self.assertTrue(user_can_access_conversation(self.bob, conversation))

    def test_nonparticipant_cannot_view_direct_detail_or_send(self):
        conversation = self.direct(self.alice, self.bob)
        self.client.force_login(self.cara)
        self.assertEqual(self.client.get(self.url("conversation_detail", conversation.pk)).status_code, 403)
        self.assertEqual(self.client.post(self.url("send_message", conversation.pk), {"body": "Nope"}).status_code, 403)
        self.assertFalse(conversation.messages.exists())

    def test_anonymous_and_pending_cannot_access_conversation_list(self):
        self.assertEqual(self.client.get(self.url("conversation_list")).status_code, 302)
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(self.url("conversation_list")).status_code, 403)

    def test_group_detail_denies_nonmatching_user(self):
        conversation = self.group()
        self.client.force_login(self.cara)
        self.assertEqual(self.client.get(self.url("conversation_detail", conversation.pk)).status_code, 403)


class MessagingDeliveryTests(MessagingFixture):
    def test_send_records_sent_message_and_notifies_recipient_by_community_name(self):
        conversation = self.direct(self.alice, self.bob)
        message = send_conversation_message(conversation=conversation, sender=self.alice, body="Hello Bob")
        self.assertEqual(message.delivery_status, Message.DeliveryStatus.SENT)
        notification = Notification.objects.get(user=self.bob, source_type="Message", source_id=str(message.pk))
        self.assertEqual(notification.title, "New message from Astrid")
        self.assertEqual(notification.target_url, self.url("conversation_detail", conversation.pk))

    def test_muted_recipient_does_not_get_notification_but_gets_message(self):
        conversation = self.direct(self.alice, self.bob)
        set_conversation_muted(conversation=conversation, user=self.bob, is_muted=True)
        self.assertTrue(user_is_conversation_muted(conversation=conversation, user=self.bob))
        message = send_conversation_message(conversation=conversation, sender=self.alice, body="Quiet message")
        self.assertEqual(message.delivery_status, Message.DeliveryStatus.SENT)
        self.assertFalse(Notification.objects.filter(user=self.bob, source_type="Message").exists())
        self.assertIn(message, get_visible_messages(conversation=conversation, user=self.bob))

    def test_block_either_direction_prevents_direct_delivery(self):
        for blocker, blocked in ((self.alice, self.bob), (self.bob, self.alice)):
            with self.subTest(blocker=blocker.username):
                UserBlock.objects.all().delete()
                UserBlock.objects.create(blocker=blocker, blocked=blocked)
                conversation = self.direct(self.alice, self.bob)
                self.assertTrue(users_are_blocked(self.alice, self.bob))
                message = send_conversation_message(conversation=conversation, sender=self.alice, body="Blocked")
                self.assertEqual(message.delivery_status, Message.DeliveryStatus.BLOCKED)
                self.assertFalse(Notification.objects.filter(source_type="Message", source_id=str(message.pk)).exists())
                self.assertIn(message, get_visible_messages(conversation=conversation, user=self.alice))
                self.assertNotIn(message, get_visible_messages(conversation=conversation, user=self.bob))

    def test_unread_count_and_read_records_are_per_user(self):
        conversation = self.direct(self.alice, self.bob)
        message = Message.objects.create(conversation=conversation, sender=self.alice, body="Unread")
        self.assertEqual(get_unread_message_count(conversation=conversation, user=self.bob), 1)
        MessageRead.objects.create(message=message, user=self.bob)
        self.assertEqual(get_unread_message_count(conversation=conversation, user=self.bob), 0)

    def test_opening_conversation_marks_received_messages_read(self):
        conversation = self.direct(self.alice, self.bob)
        message = Message.objects.create(conversation=conversation, sender=self.bob, body="Unread before view")
        self.client.force_login(self.alice)
        response = self.client.get(self.url("conversation_detail", conversation.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(MessageRead.objects.filter(message=message, user=self.alice).exists())
        self.client.get(self.url("conversation_detail", conversation.pk))
        self.assertEqual(MessageRead.objects.filter(message=message, user=self.alice).count(), 1)

    def test_group_message_notifies_only_targeted_members_other_than_sender(self):
        conversation = self.group()
        message = send_conversation_message(conversation=conversation, sender=self.alice, body="Group notice")
        self.assertEqual(message.delivery_status, Message.DeliveryStatus.SENT)
        ids = set(Notification.objects.filter(source_type="Message", source_id=str(message.pk)).values_list("user_id", flat=True))
        self.assertEqual(ids, {self.bob.pk, self.dan.pk})

    def test_send_http_requires_post_and_records_audit_without_body(self):
        conversation = self.direct(self.alice, self.bob)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(self.url("send_message", conversation.pk)).status_code, 405)
        response = self.client.post(self.url("send_message", conversation.pk), {"body": "Secret message body"})
        self.assertRedirects(response, self.url("conversation_detail", conversation.pk), fetch_redirect_response=False)
        message = Message.objects.get(conversation=conversation)
        log = AuditLog.objects.get(target_type=message._meta.verbose_name, target_id=str(message.pk))
        self.assertEqual(log.actor_id, self.alice.pk)
        self.assertEqual(log.actor_label, "Astrid")
        self.assertNotIn("Secret message body", str(log.new_value))


class MessagingWorkflowTests(MessagingFixture):
    def test_direct_creation_uses_selected_user_ids_not_names(self):
        self.client.force_login(self.alice)
        response = self.client.post(self.url("conversation_create"), {
            "conversation_type": "DIRECT", "participants": [self.bob.pk],
        })
        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.get(conversation_type="DIRECT")
        self.assertEqual(set(conversation.participants.values_list("user_id", flat=True)), {self.alice.pk, self.bob.pk})
        self.assertEqual(response["Location"], self.url("conversation_detail", conversation.pk))

    def test_invalid_direct_creation_does_not_create_conversation(self):
        self.client.force_login(self.alice)
        response = self.client.post(self.url("conversation_create"), {"conversation_type": "DIRECT"})
        self.assertRedirects(response, self.url("conversation_list"), fetch_redirect_response=False)
        self.assertFalse(Conversation.objects.exists())

    def test_leave_direct_conversation_removes_access(self):
        conversation = self.direct(self.alice, self.bob)
        self.client.force_login(self.alice)
        response = self.client.post(self.url("leave_conversation", conversation.pk))
        self.assertRedirects(response, self.url("conversation_list"), fetch_redirect_response=False)
        self.assertFalse(user_can_access_conversation(self.alice, conversation))
        self.assertTrue(user_can_access_conversation(self.bob, conversation))

    def test_cannot_leave_group_conversation_through_direct_route(self):
        conversation = self.group()
        self.client.force_login(self.alice)
        self.assertEqual(self.client.post(self.url("leave_conversation", conversation.pk)).status_code, 403)

    def test_mute_and_unmute_require_access_and_post(self):
        conversation = self.direct(self.alice, self.bob)
        mute_url = self.url("mute_conversation", conversation.pk)
        self.client.force_login(self.cara)
        self.assertEqual(self.client.post(mute_url).status_code, 403)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(mute_url).status_code, 405)
        self.assertEqual(self.client.post(mute_url).status_code, 302)
        self.assertTrue(user_is_conversation_muted(conversation=conversation, user=self.alice))
        self.assertEqual(self.client.post(self.url("unmute_conversation", conversation.pk)).status_code, 302)
        self.assertFalse(user_is_conversation_muted(conversation=conversation, user=self.alice))

    def test_block_and_unblock_are_idempotent_and_audited(self):
        self.client.force_login(self.alice)
        url = self.url("block_user", self.bob.pk)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(UserBlock.objects.filter(blocker=self.alice, blocked=self.bob).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.Action.CREATE, target_type=UserBlock._meta.verbose_name).count(), 1)
        self.assertEqual(self.client.post(self.url("unblock_user", self.bob.pk)).status_code, 302)
        self.assertFalse(UserBlock.objects.filter(blocker=self.alice, blocked=self.bob).exists())

    def test_cannot_block_self_or_pending_member(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.post(self.url("block_user", self.alice.pk)).status_code, 403)
        self.assertEqual(self.client.post(self.url("block_user", self.pending.pk)).status_code, 404)
        self.assertFalse(UserBlock.objects.exists())
