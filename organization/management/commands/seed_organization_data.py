from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from organization.models import (
    Chapter,
    ChapterStatus,
    GovernanceBody,
    Household,
    Order,
)


class Command(BaseCommand):
    help = "Create required EldVatten organizational entities."

    @transaction.atomic
    def handle(self, *args, **options):
        required_status_names = [
            "Normal",
            "Suspended",
        ]

        statuses = {
            status.name: status
            for status in ChapterStatus.objects.filter(
                name__in=required_status_names
            )
        }

        missing_statuses = [
            name
            for name in required_status_names
            if name not in statuses
        ]

        if missing_statuses:
            raise CommandError(
                "Required organization reference data is missing: "
                + ", ".join(missing_statuses)
                + ". Run seed_reference_data first."
            )

        chapters = [
            ("Fyr Draca Chapter", "Normal"),
            ("Indiana Chapter", "Suspended"),
            ("Seattle Chapter", "Normal"),
        ]

        for name, status_name in chapters:
            Chapter.objects.get_or_create(
                name=name,
                defaults={
                    "status": statuses[status_name],
                },
            )

        for name in [
            "House Hvit Hrafn",
            "House Kraken",
            "House Stormhammer",
            "House Three Horns",
            "House Svartur Hrafn",
            "House Silver Zigenare",
        ]:
            Household.objects.get_or_create(
                name=name,
                defaults={
                    "is_assignable": True,
                },
            )

        for name in [
            "Godi Council",
            "Lagstifstande Council",
        ]:
            GovernanceBody.objects.get_or_create(
                name=name,
                defaults={
                    "is_assignable": True,
                },
            )

        ranked_orders = [
            "Order of Air",
            "Order of Earth",
            "Order of Fire",
            "Order of Water",
        ]

        for name in ranked_orders:
            order, created = Order.objects.get_or_create(
                name=name,
                defaults={
                    "uses_ranks": True,
                    "is_assignable": True,
                },
            )

            if not created and not order.uses_ranks:
                order.uses_ranks = True
                order.save(
                    update_fields=[
                        "uses_ranks",
                        "updated_at",
                    ]
                )

        krig_grisar, created = Order.objects.get_or_create(
            name="Krig Grisar",
            defaults={
                "uses_ranks": False,
                "is_assignable": True,
            },
        )

        if not created and krig_grisar.uses_ranks:
            krig_grisar.uses_ranks = False
            krig_grisar.save(
                update_fields=[
                    "uses_ranks",
                    "updated_at",
                ]
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Organization data seeded successfully."
            )
        )