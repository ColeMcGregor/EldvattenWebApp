
from django.urls import reverse

from .permissions import (
    has_any_permission,
    has_permission_prefix,
)


ADMINISTRATION_SECTIONS = (
    {
        "slug": "accounts",
        "title": "Accounts & Members",
        "description": "Account approvals, access, and roles",
        "permissions": (
            "accounts.approve_membership",
            "accounts.add_user",
            "accounts.change_user",
            "accounts.delete_user",
        ),
    },
    {
        "slug": "tavern",
        "title": "The Tavern",
        "description": "Boards, reports, and moderation",
        "permissions": (
            "community.manage_forum_categories",
            "community.manage_forum_boards",
            "community.moderate_forum",
            "community.view_archived_forum_content",
            "community.hard_delete_forum_content",
        ),
    },
    {
        "slug": "events",
        "title": "Events",
        "description": "Create and manage events",
        "permissions": (
            "events.add_event",
            "events.change_event",
            "events.delete_event",
            "events.record_attendance",
        ),
    },
    {
        "slug": "voting",
        "title": "Voting",
        "description": "Votes, eligibility, and results",
        "permissions": (
            "voting.add_vote",
            "voting.change_vote",
            "voting.delete_vote",
        ),
    },
    {
        "slug": "actions",
        "title": "Actions",
        "description": "Assignments and deadlines",
        "permissions": (
            "actions.add_action",
            "actions.change_action",
            "actions.delete_action",
        ),
    },
    {
        "slug": "resources",
        "title": "Resources",
        "description": "Files, links, and visibility",
        "permissions": (
            "resources.manage_resources",
        ),
    },
    {
        "slug": "organization",
        "title": "Organization",
        "description": "Chapters, offices, and households",
        "permission_prefixes": (
            "organization.add_",
            "organization.change_",
            "organization.delete_",
        ),
    },
    {
        "slug": "system",
        "title": "Audit & System",
        "description": (
            "Audit history, bug reports, and "
            "system administration"
        ),
        "permissions": (
            "audit.view_auditlog",
        ),
    },
)


def get_administration_sections(user):
    sections = []

    for section in ADMINISTRATION_SECTIONS:
        allowed = (
            has_any_permission(
                user,
                section.get("permissions", ()),
            )
            or has_permission_prefix(
                user,
                section.get("permission_prefixes", ()),
            )
        )

        sections.append({
            **section,
            "allowed": allowed,
        })

    return sections


def get_section_links(user, section_slug):
    if not user.is_authenticated or not user.is_active:
        return []

    section = next(
        (
            section
            for section in get_administration_sections(user)
            if section["slug"] == section_slug
        ),
        None,
    )

    if section is None or not section["allowed"]:
        return []

    links = []

    def allowed(*permissions):
        return has_any_permission(user, permissions)

    if section_slug == "accounts":
        pass

    elif section_slug == "tavern":
        links.append({
            "title": "The Tavern",
            "description": (
                "Open the forum and access available "
                "moderation controls."
            ),
            "url": reverse("community:forum_index"),
        })

    elif section_slug == "events":
        links.append({
            "title": "Events",
            "description": (
                "View events and available management "
                "controls."
            ),
            "url": reverse("events:event_list"),
        })

        if allowed("events.add_event"):
            links.append({
                "title": "Create Event",
                "description": "Create a new event.",
                "url": reverse("events:event_create"),
            })

    elif section_slug == "voting":
        if allowed("voting.view_vote"):
            links.append({
                "title": "Manage Votes",
                "description": (
                    "View votes and their management controls."
                ),
                "url": reverse(
                    "voting:vote_manage_list"
                ),
            })

        if allowed("voting.add_vote"):
            links.append({
                "title": "Create Vote",
                "description": "Create a new vote.",
                "url": reverse("voting:vote_create"),
            })

    elif section_slug == "actions":
        if allowed("actions.view_action"):
            links.append({
                "title": "Manage Actions",
                "description": (
                    "View assignments and action "
                    "management controls."
                ),
                "url": reverse("actions:manage_list"),
            })

        if (
            user.is_superuser
            or (
                user.has_perm("actions.add_action")
                and user.has_perm("actions.view_action")
            )
        ):
            links.append({
                "title": "Create Action",
                "description": (
                    "Create a new action."
                ),
                "url": reverse("actions:create"),
            })

    elif section_slug == "resources":
        if allowed("resources.manage_resources"):
            links.append({
                "title": "Manage Resources",
                "description": (
                    "Manage files, links, and visibility."
                ),
                "url": reverse("resources:manage_list"),
            })

    elif section_slug == "system":
        if allowed("audit.view_auditlog"):
            links.append({
                "title": "Audit Logs",
                "description": (
                    "Search, filter, and inspect recorded "
                    "administrative activity."
                ),
                "url": reverse(
                    "administration:audit_log_list"
                ),
            })

        if user.is_staff and user.is_superuser:
            links.append({
                "title": "Bug Reports",
                "description": (
                    "Review submitted bug reports, "
                    "investigate issues, and update their status."
                ),
                "url": reverse(
                    "administration:bug_report_list"
                ),
            })

            links.append({
                "title": "Django Admin",
                "description": (
                    "Open technical site administration."
                ),
                "url": reverse("admin:index"),
            })

    return links
