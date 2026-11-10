
from django.urls import reverse


ADMINISTRATION_SECTIONS = (
    {
        "slug": "accounts",
        "title": "Accounts & Members",
        "description": "Account approvals, access, and roles",
        "permissions": (
            "accounts.approve_membership",
            "accounts.change_user",
            "accounts.add_user",
            "accounts.delete_user",
        ),
    },
    {
        "slug": "tavern",
        "title": "The Tavern",
        "description": "Boards, reports, and moderation",
        "permissions": (
            "community.moderate_forum",
            "community.manage_forum_categories",
            "community.manage_forum_boards",
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
        "description": "Audit history and system administration",
        "permissions": (
            "audit.view_auditlog",
        ),
    },
)


def administration_sections(user):
    if not user.is_authenticated or not user.is_active:
        return []

    permissions = user.get_all_permissions()
    sections = []

    for section in ADMINISTRATION_SECTIONS:
        required = section.get("permissions", ())
        prefixes = section.get("permission_prefixes", ())

        allowed = (
            user.is_superuser
            or any(
                permission in permissions
                for permission in required
            )
            or any(
                permission.startswith(prefix)
                for permission in permissions
                for prefix in prefixes
            )
        )

        sections.append({
            **section,
            "allowed": allowed,
        })

    return sections


def can_access_administration(user):
    if not user.is_authenticated or not user.is_active:
        return False

    return user.is_staff or any(
        section["allowed"]
        for section in administration_sections(user)
    )


def administration_section_links(user, slug):
    permissions = user.get_all_permissions()

    def allowed(*required):
        return user.is_superuser or any(
            name in permissions
            for name in required
        )

    links = []

    if slug == "tavern":
        links.append({
            "title": "The Tavern",
            "description": (
                "Open the forum to manage content "
                "using existing controls."
            ),
            "url": reverse("community:forum_index"),
        })

    elif slug == "events":
        if allowed(
            "events.add_event",
            "events.view_event",
        ):
            links.append({
                "title": "Events",
                "description": (
                    "View events and available "
                    "management actions."
                ),
                "url": reverse("events:event_list"),
            })

        if allowed("events.add_event") and allowed(
            "events.view_event"
        ):
            links.append({
                "title": "Create event",
                "description": "Create a new event.",
                "url": reverse("events:event_create"),
            })

    elif slug == "voting":
        if allowed("voting.view_vote"):
            links.append({
                "title": "Manage votes",
                "description": (
                    "View existing votes and their "
                    "management controls."
                ),
                "url": reverse("voting:vote_manage_list"),
            })

    elif slug == "actions":
        if allowed("actions.view_action"):
            links.append({
                "title": "Manage actions",
                "description": (
                    "View assignments and action "
                    "management controls."
                ),
                "url": reverse("actions:manage_list"),
            })

    elif slug == "resources":
        if allowed("resources.manage_resources"):
            links.append({
                "title": "Manage resources",
                "description": (
                    "Manage files, links, and visibility."
                ),
                "url": reverse("resources:manage_list"),
            })

    elif slug == "system":
        if user.is_staff and allowed(
            "audit.view_auditlog"
        ):
            links.append({
                "title": "Audit history (Django Admin)",
                "description": "View the technical audit log.",
                "url": reverse(
                    "admin:audit_auditlog_changelist"
                ),
            })

        if user.is_staff and user.is_superuser:
            links.append({
                "title": "Django Admin",
                "description": "Technical site administration.",
                "url": reverse("admin:index"),
            })

    return links
