
def has_any_permission(user, permissions):
    if not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser:
        return True

    return any(
        user.has_perm(permission)
        for permission in permissions
    )


def has_permission_prefix(user, prefixes):
    if not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser:
        return True

    return any(
        permission.startswith(prefix)
        for permission in user.get_all_permissions()
        for prefix in prefixes
    )


def can_access_administration(user):
    if not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser or user.is_staff:
        return True

    from .sections import get_administration_sections

    return any(
        section["allowed"]
        for section in get_administration_sections(user)
    )
