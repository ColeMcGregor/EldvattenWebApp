import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from audit.services import get_request_ip

from .models import SubmissionThrottle


MINUTE_LIMIT = 1
ANONYMOUS_HOURLY_LIMIT = 3
AUTHENTICATED_HOURLY_LIMIT = 5


class SubmissionRateLimitExceeded(Exception):
    def __init__(self, retry_after):
        self.retry_after = max(1, retry_after)

        super().__init__(
            "Bug report submission limit exceeded."
        )


def get_submission_identity(request):
    if request.user.is_authenticated:
        return (
            f"user:{request.user.pk}",
            AUTHENTICATED_HOURLY_LIMIT,
        )

    client_ip = get_request_ip(request)

    if client_ip is None:
        raise SubmissionRateLimitExceeded(
            retry_after=60,
        )

    return (
        f"ip:{client_ip}",
        ANONYMOUS_HOURLY_LIMIT,
    )


def get_identity_hash(identifier):
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        identifier.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

def lock_submission_identity(identifier_hash):
    lock_key = int.from_bytes(
        bytes.fromhex(identifier_hash)[:8],
        byteorder="big",
        signed=True,
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [lock_key],
        )


def get_submission_quota(
    *,
    identifier_hash,
    period,
    now,
):
    quota, _ = (
        SubmissionThrottle.objects
        .select_for_update()
        .get_or_create(
            identifier=identifier_hash,
            period=period,
            defaults={
                "submission_count": 0,
                "window_started_at": now,
            },
        )
    )

    return quota


def consume_submission_quota(
    *,
    request,
):
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError(
            "Submission quotas must be consumed "
            "inside a database transaction."
        )

    identifier, hourly_limit = get_submission_identity(
        request
    )

    identifier_hash = get_identity_hash(
        identifier
    )

    lock_submission_identity(
        identifier_hash
    )

    now = timezone.now()

    quota_settings = (
        (
            SubmissionThrottle.Period.MINUTE,
            timedelta(minutes=1),
            MINUTE_LIMIT,
        ),
        (
            SubmissionThrottle.Period.HOUR,
            timedelta(hours=1),
            hourly_limit,
        ),
    )

    quotas = []

    for period, duration, limit in quota_settings:
        quota = get_submission_quota(
            identifier_hash=identifier_hash,
            period=period,
            now=now,
        )

        expires_at = (
            quota.window_started_at + duration
        )

        if now >= expires_at:
            quota.submission_count = 0
            quota.window_started_at = now
            expires_at = now + duration

        if quota.submission_count >= limit:
            retry_after = max(
                1,
                int(
                    (expires_at - now).total_seconds()
                ) + 1,
            )

            raise SubmissionRateLimitExceeded(
                retry_after=retry_after,
            )

        quotas.append(quota)

    for quota in quotas:
        quota.submission_count += 1

        quota.save(
            update_fields=[
                "submission_count",
                "window_started_at",
                "updated_at",
            ]
        )
