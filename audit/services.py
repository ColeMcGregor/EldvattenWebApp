from ipaddress import ip_address

from .models import AuditLog


def get_request_ip(request):
    if request is None:
        return None

    # TODO: this needs to be changed to only trust IPs forwarded from known proxy, CloudFlare
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
    else:
        candidate = request.META.get("REMOTE_ADDR")

    if not candidate:
        return None

    try:
        return str(ip_address(candidate))
    except ValueError:
        return None


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
        actor_label = getattr(actor, "display_name", "") or actor.get_username()

    return AuditLog.objects.create(
        actor=actor,
        actor_label=actor_label,
        ip_address=get_request_ip(request),
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else "",
        target_label=target_label,
        old_value=old_value,
        new_value=new_value,
        effective_at=effective_at,
        source=source,
        method=method,
        request_path=request.path if request is not None else "",
        notes=notes,
    )