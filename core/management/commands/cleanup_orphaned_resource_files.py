import os
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from resources.models import Resource
from resources.storage import private_resource_storage


class Command(BaseCommand):
    help = "Find old private Resource files that no Resource record references."

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete eligible orphan files. Without this flag, report only.",
        )
        parser.add_argument(
            "--min-age-hours",
            type=int,
            default=48,
            help="Minimum file age in hours (default: 48).",
        )

    def handle(self, *args, **options):
        min_age_hours = options["min_age_hours"]
        should_delete = options["delete"]

        if min_age_hours < 0:
            raise CommandError("--min-age-hours cannot be negative.")

        resource_directory = Path(
            private_resource_storage.path("resources")
        )

        if not resource_directory.exists():
            self.stdout.write("No Resource storage directory exists.")
            return

        if not resource_directory.is_dir() or resource_directory.is_symlink():
            raise CommandError("Resource storage directory is not a normal directory.")

        storage_root = Path(private_resource_storage.location).resolve()
        resource_root = resource_directory.resolve()

        if resource_root.parent != storage_root:
            raise CommandError("Resource storage directory is outside private storage.")

        referenced_files = set(
            Resource.objects.exclude(file__isnull=True)
            .exclude(file="")
            .values_list("file", flat=True)
        )

        cutoff_time = time.time() - min_age_hours * 3600
        candidates = 0
        deleted = 0

        for current_directory, subdirectories, filenames in os.walk(
            resource_root,
            topdown=True,
            followlinks=False,
        ):
            current_path = Path(current_directory)
            subdirectories[:] = [
                name
                for name in subdirectories
                if not (current_path / name).is_symlink()
            ]

            for filename in filenames:
                path = current_path / filename

                if path.is_symlink() or not path.is_file():
                    continue

                relative_name = path.relative_to(storage_root).as_posix()

                if relative_name in referenced_files:
                    continue

                if path.stat().st_mtime > cutoff_time:
                    continue

                candidates += 1

                if not should_delete:
                    self.stdout.write(f"Orphan candidate: {relative_name}")
                    continue

                # Recheck immediately before deletion in case a Resource
                # began referencing this file after the initial scan.
                if Resource.objects.filter(file=relative_name).exists():
                    continue

                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_mtime > cutoff_time
                ):
                    continue

                try:
                    private_resource_storage.delete(relative_name)
                except OSError as error:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Could not delete {relative_name}: {error}"
                        )
                    )
                    continue

                deleted += 1
                self.stdout.write(f"Deleted: {relative_name}")

        if should_delete:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Found {candidates} eligible orphan files; "
                    f"deleted {deleted}."
                )
            )
        else:
            self.stdout.write(
                f"Found {candidates} eligible orphan files. "
                "Dry run only; nothing deleted."
            )
