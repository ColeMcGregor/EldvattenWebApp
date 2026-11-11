
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from feedback.models import SubmissionThrottle


class Command(BaseCommand):
    help = "Delete expired bug-report submission throttle records."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=24)

        deleted_count, _ = (
            SubmissionThrottle.objects
            .filter(updated_at__lt=cutoff)
            .delete()
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} expired throttle records."
            )
        )
