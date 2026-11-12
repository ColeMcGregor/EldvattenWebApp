from io import BytesIO, StringIO
from pathlib import Path
import os
import tempfile
import time
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountStatus, User
from audit.models import AuditLog
from organization.models import CommunityGroup, GroupMembership

from .forms import ResourceTargetForm
from .models import Resource, ResourceTarget
from .services import (
    can_view_resource,
    schedule_resource_file_cleanup,
    visible_resources_for_user,
)
from .storage import private_resource_storage


class ResourceTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(
            username="resources_manager", account_status=AccountStatus.MEMBER
        )
        permission = Permission.objects.get(
            content_type__app_label="resources", codename="manage_resources"
        )
        cls.manager.user_permissions.add(permission)
        cls.member = User.objects.create_user(
            username="resources_member", account_status=AccountStatus.MEMBER
        )
        cls.other = User.objects.create_user(
            username="resources_other", account_status=AccountStatus.MEMBER
        )
        cls.pending = User.objects.create_user(
            username="resources_pending", account_status=AccountStatus.PENDING
        )
        cls.inactive_user = User.objects.create_user(
            username="resources_inactive_user", account_status=AccountStatus.MEMBER,
            is_active=False,
        )
        cls.link = Resource.objects.create(
            title="Public Resource", resource_type=Resource.ResourceType.LINK,
            external_url="https://example.org/document", created_by=cls.manager,
            visibility=Resource.Visibility.MEMBERS,
        )
        cls.custom = Resource.objects.create(
            title="Private Resource", resource_type=Resource.ResourceType.LINK,
            external_url="https://example.org/private", created_by=cls.manager,
            visibility=Resource.Visibility.CUSTOM,
        )
        ResourceTarget.objects.create(
            resource=cls.custom, effect=ResourceTarget.Effect.INCLUDE,
            user=cls.member,
        )

    def url(self, name, resource=None):
        args = [resource.pk] if resource is not None else []
        return reverse(f"resources:{name}", args=args)

    def form_data(self, **changes):
        data = {
            "title": "Created Link", "description": "Lorem ipsum dolor sit amet.",
            "resource_type": "LINK", "external_url": "https://example.org/created",
            "visibility": "MEMBERS", "sort_order": "0", "is_active": "on",
            "targets-TOTAL_FORMS": "0", "targets-INITIAL_FORMS": "0",
            "targets-MIN_NUM_FORMS": "0", "targets-MAX_NUM_FORMS": "100",
        }
        data.update(changes)
        return data


class ResourceVisibilityTests(ResourceTestBase):
    def test_anonymous_and_pending_cannot_access_member_resources(self):
        self.assertFalse(can_view_resource(AnonymousUser(), self.link))
        self.assertFalse(can_view_resource(self.pending, self.link))
        self.assertFalse(visible_resources_for_user(self.pending).exists())

    def test_member_can_view_all_member_resources(self):
        self.assertTrue(can_view_resource(self.member, self.link))
        self.assertTrue(can_view_resource(self.other, self.link))

    def test_custom_resource_only_includes_targeted_member(self):
        self.assertTrue(can_view_resource(self.member, self.custom))
        self.assertFalse(can_view_resource(self.other, self.custom))

    def test_exclusion_overrides_member_visibility(self):
        ResourceTarget.objects.create(
            resource=self.link, effect=ResourceTarget.Effect.EXCLUDE,
            user=self.member,
        )
        self.assertFalse(can_view_resource(self.member, self.link))
        self.assertTrue(can_view_resource(self.other, self.link))

    def test_exclusion_overrides_custom_inclusion(self):
        ResourceTarget.objects.create(
            resource=self.custom, effect=ResourceTarget.Effect.EXCLUDE,
            user=self.member,
        )
        self.assertFalse(can_view_resource(self.member, self.custom))

    def test_inactive_resource_is_hidden_even_from_manager(self):
        self.link.is_active = False
        self.link.save(update_fields=["is_active"])
        self.assertFalse(can_view_resource(self.member, self.link))
        self.assertFalse(can_view_resource(self.manager, self.link))

    def test_manager_may_view_active_resource_regardless_of_targets(self):
        self.assertTrue(can_view_resource(self.manager, self.custom))

    def test_group_target_uses_current_membership(self):
        group = CommunityGroup.objects.create(name="Resource Test Group")
        GroupMembership.objects.create(
            user=self.other, community_group=group,
            started_at=timezone.localdate(), changed_by=self.manager,
        )
        ResourceTarget.objects.filter(resource=self.custom).delete()
        ResourceTarget.objects.create(
            resource=self.custom, effect=ResourceTarget.Effect.INCLUDE,
            community_group=group,
        )
        self.assertTrue(can_view_resource(self.other, self.custom))
        self.assertFalse(can_view_resource(self.member, self.custom))

    def test_resource_target_needs_selector(self):
        target = ResourceTarget(resource=self.custom)
        with self.assertRaisesMessage(Exception, "at least one selector"):
            target.full_clean()

    def test_combined_user_and_organization_target_is_invalid(self):
        group = CommunityGroup.objects.create(name="Second Resource Group")
        target = ResourceTarget(
            resource=self.custom, user=self.member, community_group=group
        )
        with self.assertRaisesMessage(Exception, "cannot be combined"):
            target.full_clean()


class ResourceMemberViewTests(ResourceTestBase):
    def test_anonymous_list_redirects_to_login(self):
        self.assertEqual(self.client.get(self.url("list")).status_code, 302)

    def test_pending_member_list_forbidden(self):
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(self.url("list")).status_code, 403)

    def test_visible_list_excludes_custom_resource_for_unlisted_user(self):
        self.client.force_login(self.other)
        response = self.client.get(self.url("list"))
        self.assertContains(response, "Public Resource")
        self.assertNotContains(response, "Private Resource")
        self.assertContains(response, 'data-resource-query')
        self.assertContains(response, 'href="/resources/')

    def test_member_list_shows_accessible_custom_resource(self):
        self.client.force_login(self.member)
        self.assertContains(self.client.get(self.url("list")), "Private Resource")

    def test_member_list_excludes_inactive_resource(self):
        self.link.is_active = False
        self.link.save(update_fields=["is_active"])
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(self.url("list")), "Public Resource")

    def test_download_requires_visibility_and_correct_type(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("download", self.custom)).status_code, 404)
        self.assertEqual(self.client.get(self.url("download", self.link)).status_code, 404)

    def test_link_open_requires_visibility(self):
        self.client.force_login(self.member)
        response = self.client.get(self.url("open", self.custom))
        self.assertRedirects(
            response, self.custom.external_url, fetch_redirect_response=False
        )
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url("open", self.custom)).status_code, 404)

    def test_download_returns_private_file_through_view(self):
        resource = Resource.objects.create(
            title="File resource", resource_type=Resource.ResourceType.FILE,
            file="resources/example.txt", created_by=self.manager,
        )
        self.client.force_login(self.member)
        with patch.object(private_resource_storage, "open", return_value=BytesIO(b"private")):
            response = self.client.get(self.url("download", resource))
            self.assertEqual(response.status_code, 200)
            self.assertIn("attachment", response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"private")

    def test_blocked_download_is_rejected_before_storage_open(self):
        resource = Resource.objects.create(
            title="Private File", resource_type=Resource.ResourceType.FILE,
            file="resources/secret.txt", created_by=self.manager,
            visibility=Resource.Visibility.CUSTOM,
        )
        self.client.force_login(self.other)
        with patch.object(private_resource_storage, "open") as storage_open:
            self.assertEqual(
                self.client.get(self.url("download", resource)).status_code, 404
            )
            storage_open.assert_not_called()


class ResourceManagementTests(ResourceTestBase):
    def setUp(self):
        self.client.force_login(self.manager)

    def test_member_cannot_manage_resources(self):
        self.client.force_login(self.member)
        for name in ("manage_list", "create"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(self.url(name)).status_code, 403)
        for name in ("manage_detail", "edit"):
            with self.subTest(name=name):
                self.assertEqual(
                    self.client.get(self.url(name, self.link)).status_code, 403
                )
        self.assertEqual(
            self.client.post(self.url("create"), self.form_data()).status_code, 403
        )

    def test_management_list_includes_active_and_inactive(self):
        self.custom.is_active = False
        self.custom.save(update_fields=["is_active"])
        response = self.client.get(self.url("manage_list"))
        self.assertContains(response, "Public Resource")
        self.assertContains(response, "Private Resource")
        self.assertContains(response, "Create Resource")

    def test_member_list_displays_manage_tab_for_manager_only(self):
        self.assertContains(self.client.get(self.url("list")), "Manage Resources")
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(self.url("list")), "Manage Resources")

    def test_create_link_records_audit(self):
        response = self.client.post(self.url("create"), self.form_data())
        created = Resource.objects.get(title="Created Link")
        self.assertRedirects(response, self.url("manage_detail", created))
        self.assertEqual(created.resource_type, Resource.ResourceType.LINK)
        self.assertTrue(AuditLog.objects.filter(
            target_type="Resource", target_id=str(created.pk),
            action=AuditLog.Action.CREATE,
        ).exists())

    def test_create_custom_requires_include_target(self):
        response = self.client.post(
            self.url("create"), self.form_data(visibility="CUSTOM")
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at least one include target")
        self.assertFalse(Resource.objects.filter(title="Created Link").exists())

    def test_create_custom_with_include_target(self):
        response = self.client.post(
            self.url("create"), self.form_data(
                visibility="CUSTOM",
                **{
                    "targets-TOTAL_FORMS": "1",
                    "targets-0-effect": "INCLUDE",
                    "targets-0-user": str(self.member.pk),
                },
            ),
        )
        created = Resource.objects.get(title="Created Link")
        self.assertRedirects(response, self.url("manage_detail", created))
        self.assertTrue(can_view_resource(self.member, created))
        self.assertFalse(can_view_resource(self.other, created))

    def test_all_members_can_have_exclusion_without_include(self):
        response = self.client.post(
            self.url("create"), self.form_data(**{
                "targets-TOTAL_FORMS": "1",
                "targets-0-effect": "EXCLUDE",
                "targets-0-user": str(self.member.pk),
            }),
        )
        created = Resource.objects.get(title="Created Link")
        self.assertRedirects(response, self.url("manage_detail", created))
        self.assertFalse(can_view_resource(self.member, created))
        self.assertTrue(can_view_resource(self.other, created))

    def test_invalid_file_resource_does_not_save(self):
        response = self.client.post(self.url("create"), self.form_data(
            resource_type="FILE", external_url=""
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Resource.objects.filter(title="Created Link").exists())

    def test_uploaded_file_resource_is_saved_in_private_storage(self):
        upload = SimpleUploadedFile("sample.txt", b"sample", content_type="text/plain")
        with patch.object(private_resource_storage, "save", return_value="resources/sample.txt"):
            response = self.client.post(
                self.url("create"),
                self.form_data(resource_type="FILE", external_url="", file=upload),
            )
        created = Resource.objects.get(title="Created Link")
        self.assertRedirects(response, self.url("manage_detail", created))
        self.assertEqual(created.file.name, "resources/sample.txt")

    def test_editing_updates_resource_and_writes_old_and_new_values(self):
        initial_targets = list(self.link.targets.all())
        self.assertEqual(initial_targets, [])
        response = self.client.post(
            self.url("edit", self.link),
            {
                **self.form_data(title="Edited Link"),
                "targets-INITIAL_FORMS": "0",
            },
        )
        self.assertRedirects(response, self.url("manage_detail", self.link))
        self.link.refresh_from_db()
        self.assertEqual(self.link.title, "Edited Link")
        event = AuditLog.objects.get(
            target_type="Resource", target_id=str(self.link.pk),
            action=AuditLog.Action.UPDATE,
        )
        self.assertEqual(event.old_value["title"], "Public Resource")
        self.assertEqual(event.new_value["title"], "Edited Link")

    def test_editing_can_deactivate_resource(self):
        data = self.form_data(title=self.link.title)
        data.pop("is_active")
        response = self.client.post(self.url("edit", self.link), data)
        self.assertRedirects(response, self.url("manage_detail", self.link))
        self.link.refresh_from_db()
        self.assertFalse(self.link.is_active)
        self.assertFalse(can_view_resource(self.manager, self.link))

    def test_editing_to_file_clears_external_url(self):
        upload = SimpleUploadedFile("convert.txt", b"bytes", content_type="text/plain")
        with patch.object(private_resource_storage, "save", return_value="resources/convert.txt"):
            response = self.client.post(
                self.url("edit", self.link),
                self.form_data(title=self.link.title, resource_type="FILE", file=upload),
            )
        self.assertRedirects(response, self.url("manage_detail", self.link))
        self.link.refresh_from_db()
        self.assertEqual(self.link.external_url, "")
        self.assertEqual(self.link.resource_type, "FILE")

    def test_target_change_updates_visibility_and_audit(self):
        data = self.form_data(
            title=self.custom.title, visibility="CUSTOM",
            **{
                "targets-INITIAL_FORMS": "1",
                "targets-TOTAL_FORMS": "1",
                "targets-0-id": str(self.custom.targets.get().pk),
                "targets-0-effect": "INCLUDE",
                "targets-0-user": str(self.other.pk),
            },
        )
        response = self.client.post(self.url("edit", self.custom), data)
        self.assertRedirects(response, self.url("manage_detail", self.custom))
        self.assertFalse(can_view_resource(self.member, self.custom))
        self.assertTrue(can_view_resource(self.other, self.custom))
        event = AuditLog.objects.get(
            target_type="Resource", target_id=str(self.custom.pk),
            action=AuditLog.Action.UPDATE,
        )
        self.assertNotEqual(event.old_value["targets"], event.new_value["targets"])

    def test_management_detail_preview_respects_exclusion(self):
        ResourceTarget.objects.create(
            resource=self.custom, effect=ResourceTarget.Effect.EXCLUDE,
            user=self.member,
        )
        response = self.client.get(self.url("manage_detail", self.custom))
        self.assertContains(response, "0 active members currently")
        self.assertEqual(response.context["audience_count"], 0)

    def test_management_views_do_not_change_state_on_get(self):
        self.client.get(self.url("create"))
        self.client.get(self.url("edit", self.link))
        self.client.get(self.url("manage_detail", self.link))
        self.assertEqual(Resource.objects.count(), 2)
        self.assertFalse(AuditLog.objects.filter(target_type="Resource").exists())

    def test_management_resource_url_is_not_public(self):
        self.client.force_login(self.pending)
        self.assertEqual(
            self.client.get(self.url("manage_detail", self.custom)).status_code,
            403,
        )

class ResourceFileLifecycleTests(ResourceTestBase):
    def make_file_resource(
        self,
        filename="resources/old-file.txt",
    ):
        return Resource.objects.create(
            title="Lifecycle Resource",
            resource_type=Resource.ResourceType.FILE,
            file=filename,
            created_by=self.manager,
        )

    def test_replacement_deletes_previous_file_after_commit(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                resource.file = "resources/new-file.txt"
                resource.save()
                delete_file.assert_not_called()

            self.assertEqual(len(callbacks), 1)
            delete_file.assert_called_once_with(
                "resources/old-file.txt"
            )

    def test_switching_file_to_link_deletes_previous_file(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(execute=True):
                resource.resource_type = Resource.ResourceType.LINK
                resource.file = None
                resource.external_url = "https://example.org/new"
                resource.save()

            delete_file.assert_called_once_with(
                "resources/old-file.txt"
            )

    def test_deactivation_does_not_delete_file(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                resource.is_active = False
                resource.save(update_fields=["is_active"])

            self.assertEqual(callbacks, [])
            delete_file.assert_not_called()

    def test_metadata_only_update_does_not_delete_file(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                resource.title = "Updated Title"
                resource.save(update_fields=["title"])

            self.assertEqual(callbacks, [])
            delete_file.assert_not_called()

    def test_deleting_resource_deletes_file_after_commit(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                resource.delete()
                delete_file.assert_not_called()

            self.assertEqual(len(callbacks), 1)
            delete_file.assert_called_once_with(
                "resources/old-file.txt"
            )

    def test_queryset_delete_also_deletes_file(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(execute=True):
                Resource.objects.filter(pk=resource.pk).delete()

            delete_file.assert_called_once_with(
                "resources/old-file.txt"
            )

    def test_shared_file_is_not_deleted_while_referenced(self):
        resource = self.make_file_resource()
        self.make_file_resource(
            filename="resources/old-file.txt"
        )

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(execute=True):
                resource.file = "resources/new-file.txt"
                resource.save()

            delete_file.assert_not_called()

    def test_rolled_back_replacement_does_not_delete_file(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        resource.file = "resources/new-file.txt"
                        resource.save()
                        raise RuntimeError("rollback")

            self.assertEqual(callbacks, [])
            delete_file.assert_not_called()

        resource.refresh_from_db()
        self.assertEqual(
            resource.file.name,
            "resources/old-file.txt",
        )

    def test_invalid_cleanup_path_is_rejected(self):
        with patch.object(
            private_resource_storage,
            "delete",
        ) as delete_file:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                schedule_resource_file_cleanup(
                    "../secret.txt",
                    using="default",
                )

            self.assertEqual(callbacks, [])
            delete_file.assert_not_called()

    def test_cleanup_error_does_not_break_committed_operation(self):
        resource = self.make_file_resource()

        with patch.object(
            private_resource_storage,
            "delete",
            side_effect=OSError("storage unavailable"),
        ) as delete_file:
            with self.assertLogs(
                "resources.services",
                level="ERROR",
            ):
                with self.captureOnCommitCallbacks(execute=True):
                    resource.delete()

            delete_file.assert_called_once_with(
                "resources/old-file.txt"
            )


class OrphanResourceFileCommandTests(ResourceTestBase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

        storage_patch = patch.object(
            private_resource_storage,
            "location",
            self.temporary_directory.name,
        )
        storage_patch.start()
        self.addCleanup(storage_patch.stop)

    def make_stored_file(self, filename, *, age_hours=49):
        path = Path(
            private_resource_storage.path(filename)
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_bytes(b"temporary test data")

        timestamp = time.time() - age_hours * 3600
        os.utime(path, (timestamp, timestamp))

        return path

    def test_dry_run_lists_orphan_without_deleting(self):
        orphan = self.make_stored_file(
            "resources/orphan.txt"
        )

        output = StringIO()

        call_command(
            "cleanup_orphaned_resource_files",
            stdout=output,
        )

        self.assertTrue(orphan.exists())
        self.assertIn(
            "resources/orphan.txt",
            output.getvalue(),
        )

    def test_delete_removes_old_orphan_but_keeps_referenced_and_recent(self):
        orphan = self.make_stored_file(
            "resources/orphan.txt"
        )

        referenced = self.make_stored_file(
            "resources/referenced.txt"
        )

        recent = self.make_stored_file(
            "resources/recent.txt",
            age_hours=1,
        )

        Resource.objects.create(
            title="Referenced File",
            resource_type=Resource.ResourceType.FILE,
            file="resources/referenced.txt",
            created_by=self.manager,
        )

        output = StringIO()

        call_command(
            "cleanup_orphaned_resource_files",
            "--delete",
            stdout=output,
        )

        self.assertFalse(orphan.exists())
        self.assertTrue(referenced.exists())
        self.assertTrue(recent.exists())

        self.assertIn(
            "Deleted: resources/orphan.txt",
            output.getvalue(),
        )

class ResourceCommunityNameTests(ResourceTestBase):
    def set_name(self, user, **values):
        for field, value in values.items():
            setattr(user, field, value)
        user.save(update_fields=list(values))

    def test_target_selector_prefers_eldvatten_name_and_shows_username(self):
        self.set_name(
            self.member,
            display_name="Personal Label",
            eldvatten_name="Shield Bearer",
        )
        form = ResourceTargetForm()
        self.assertEqual(
            form.fields["user"].label_from_instance(self.member),
            "Shield Bearer (@resources_member)",
        )

    def test_target_selector_follows_name_fallbacks(self):
        form = ResourceTargetForm()
        cases = (
            ({"eldvatten_name": "  ", "display_name": "Personal Label"},
             "Personal Label (@resources_member)"),
            ({"eldvatten_name": "", "display_name": "",
              "first_name": "First", "last_name": "Last"},
             "First Last (@resources_member)"),
            ({"eldvatten_name": "", "display_name": "",
              "first_name": "", "last_name": ""},
             "@resources_member"),
        )
        for fields, expected in cases:
            with self.subTest(expected=expected):
                self.set_name(self.member, **fields)
                self.assertEqual(
                    form.fields["user"].label_from_instance(self.member),
                    expected,
                )

    def test_target_selector_sorts_by_community_name(self):
        self.set_name(self.member, eldvatten_name="Zora")
        self.set_name(self.other, eldvatten_name="Alva")
        self.set_name(self.manager, eldvatten_name="Mira")
        form = ResourceTargetForm()
        users = list(form.fields["user"].queryset)
        self.assertEqual(
            [user.pk for user in users],
            [self.other.pk, self.manager.pk, self.member.pk],
        )

    def test_target_selector_excludes_pending_and_inactive_accounts(self):
        form = ResourceTargetForm()
        selected_ids = set(
            form.fields["user"].queryset.values_list("pk", flat=True)
        )
        self.assertEqual(
            selected_ids,
            {self.manager.pk, self.member.pk, self.other.pk},
        )
        self.assertNotIn(self.pending.pk, selected_ids)
        self.assertNotIn(self.inactive_user.pk, selected_ids)

    def test_management_detail_displays_creator_and_target_community_names(self):
        self.set_name(self.manager, eldvatten_name="Resource Keeper")
        self.set_name(self.member, eldvatten_name="Stone Weaver")
        self.client.force_login(self.manager)
        response = self.client.get(self.url("manage_detail", self.custom))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resource Keeper")
        self.assertContains(response, "Stone Weaver")
        self.assertContains(response, "@resources_member")

    def test_audience_is_ordered_by_community_name(self):
        self.set_name(self.member, eldvatten_name="Zora")
        self.set_name(self.other, eldvatten_name="Alva")
        self.client.force_login(self.manager)
        response = self.client.get(self.url("manage_detail", self.link))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [user.pk for user in response.context["audience"]],
            [self.other.pk, self.manager.pk, self.member.pk],
        )

    def test_renaming_member_does_not_change_resource_access(self):
        before = (
            can_view_resource(self.member, self.custom),
            can_view_resource(self.other, self.custom),
        )
        self.set_name(
            self.member,
            eldvatten_name="Renamed Citizen",
            display_name="Changed Display",
        )
        self.assertEqual(
            (
                can_view_resource(self.member, self.custom),
                can_view_resource(self.other, self.custom),
            ),
            before,
        )
        self.assertEqual(self.custom.targets.get().user_id, self.member.pk)

    def test_management_detail_escapes_html_in_community_name(self):
        self.set_name(
            self.member,
            eldvatten_name="<script>alert('x')</script>",
        )
        self.client.force_login(self.manager)
        response = self.client.get(self.url("manage_detail", self.custom))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert('x')</script>")
        self.assertContains(response, "&lt;script&gt;", html=False)

