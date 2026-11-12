from ipaddress import ip_address, ip_network

from django.conf import settings

from .models import AuditLog


def _parse_ip(value):
    if not value:
        return None

    try:
        return ip_address(value.strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _is_trusted_proxy(address):
    if address is None:
        return False

    trusted_proxies = getattr(
        settings,
        "AUDIT_TRUSTED_PROXY_CIDRS",
        (),
    )

    for network in trusted_proxies:
        if address in ip_network(network, strict=False):
            return True

    return False


def get_request_ip(request):
    if request is None:
        return None

    remote_address = _parse_ip(
        request.META.get("REMOTE_ADDR")
    )

    if remote_address is None:
        return None

    if not _is_trusted_proxy(remote_address):
        return str(remote_address)

    forwarded_for = request.META.get(
        "HTTP_X_FORWARDED_FOR",
        "",
    )

    if not forwarded_for:
        return str(remote_address)

    forwarded_addresses = forwarded_for.split(",")

    for value in reversed(forwarded_addresses):
        candidate = _parse_ip(value)

        if candidate is None:
            return str(remote_address)

        if not _is_trusted_proxy(candidate):
            return str(candidate)

    return str(remote_address)


def record_audit_event(
    *,
    action,
    target_type,
    source,
    method,
    actor=None,
    request=None,
    target_id="",
    target_label="",
    old_value=None,
    new_value=None,
    effective_at=None,
    notes="",
):
    actor_label = ""

    if actor is not None:
        actor_label = actor.community_name

    return AuditLog.objects.create(
        actor=actor,
        actor_label=actor_label,
        ip_address=get_request_ip(request),
        action=action,
        target_type=target_type,
        target_id=(
            str(target_id)
            if target_id is not None
            else ""
        ),
        target_label=target_label,
        old_value=old_value,
        new_value=new_value,
        effective_at=effective_at,
        source=source,
        method=method,
        request_path=(
            request.path
            if request is not None
            else ""
        ),
        notes=notes,
    )
