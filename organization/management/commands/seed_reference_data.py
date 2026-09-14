from django.core.management.base import BaseCommand
from django.db import transaction

from organization.models import (
    ChapterStatus,
    CitizenshipClass,
    HouseholdLeadershipType,
    Office,
    OrderRank,
    SocialRank,
)


class Command(BaseCommand):
    help = "Create required EldVatten organization reference data."

    @transaction.atomic
    def handle(self, *args, **options):
        chapter_statuses = [
            ("Normal", True),
            ("Honorary", True),
            ("Suspended", False),
            ("Dissolved", False),
        ]

        for name, allows_new_citizens in chapter_statuses:
            status, created = ChapterStatus.objects.get_or_create(
                name=name,
                defaults={
                    "allows_new_citizens": allows_new_citizens,
                    "is_selectable": True,
                },
            )

            if not created and (
                status.allows_new_citizens != allows_new_citizens
            ):
                status.allows_new_citizens = allows_new_citizens
                status.save(
                    update_fields=[
                        "allows_new_citizens",
                        "updated_at",
                    ]
                )

        for name in [
            "Active Citizen",
            "Honorary Citizen",
            "Initiate Citizen",
            "Allied Individual",
        ]:
            CitizenshipClass.objects.get_or_create(
                name=name,
                defaults={
                    "is_assignable": True,
                },
            )

        for name in [
            "Lysingr",
            "Karl",
            "Thegn",
            "Jarl",
            "Godi",
        ]:
            SocialRank.objects.get_or_create(
                name=name,
                defaults={
                    "is_assignable": True,
                },
            )

        for name in [
            "Lawspeaker",
            "Hersir",
            "Stallari",
            "Kesserer",
            "Skafari",
            "Skald",
            "Vard",
        ]:
            Office.objects.get_or_create(
                name=name,
                defaults={
                    "is_assignable": True,
                },
            )

        HouseholdLeadershipType.objects.get_or_create(
            name="Leading Jarl",
            defaults={
                "is_assignable": True,
            },
        )

        order_ranks = [
            ("Larling", 1),
            ("Gesallen", 2),
            ("Ledar", 3),
        ]

        for name, rank_order in order_ranks:
            rank, created = OrderRank.objects.get_or_create(
                name=name,
                defaults={
                    "rank_order": rank_order,
                    "is_assignable": True,
                },
            )

            if not created and rank.rank_order != rank_order:
                rank.rank_order = rank_order
                rank.save(
                    update_fields=[
                        "rank_order",
                        "updated_at",
                    ]
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Organization reference data seeded successfully."
            )
        )