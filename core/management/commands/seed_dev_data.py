from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AccountStatus
from organization.models import (
    Chapter,
    CitizenshipClass,
    CitizenshipRecord,
    CommunityGroup,
    GovernanceBody,
    GovernanceMembership,
    GroupMembership,
    Household,
    HouseholdLeadership,
    HouseholdLeadershipType,
    HouseholdMembership,
    InitiateSponsorship,
    Office,
    Order,
    OrderMembership,
    OrderRank,
    SocialRank,
    UserOffice,
    UserSocialRank,
)


User = get_user_model()


TEST_PASSWORD = "Eldvatten!123_"
SUPERUSER_PASSWORD = "testpassword"

TEST_USER_COUNT = 52

TEST_STARTED_AT = date(
    2026,
    1,
    1,
)

TEST_GROUP_NAME = "Test Custom Group"


FORUM_PERMISSION_CODENAMES = (
    "manage_forum_categories",
    "manage_forum_boards",
    "moderate_forum",
    "view_archived_forum_content",
    "hard_delete_forum_content",
)


ALL_FORUM_PERMISSION_USERS = {
    40,
    41,
    42,
}


FORUM_PERMISSION_USERS = {
    "manage_forum_categories": {
        43,
        44,
        45,
    },
    "manage_forum_boards": {
        46,
        47,
        48,
    },
    "moderate_forum": {
        49,
        50,
        51,
    },
    "view_archived_forum_content": {
        43,
        46,
        49,
    },
    "hard_delete_forum_content": {
        44,
        47,
        50,
    },
}


STAFF_ONLY_USERS = {
    52,
}


ACCOUNT_STATUS_OVERRIDES = {
    3: AccountStatus.PENDING,
    24: AccountStatus.PENDING,
    43: AccountStatus.PENDING,

    6: AccountStatus.SUSPENDED,
    27: AccountStatus.SUSPENDED,
    46: AccountStatus.SUSPENDED,

    9: AccountStatus.DISABLED,
    30: AccountStatus.DISABLED,
    49: AccountStatus.DISABLED,
}


class Command(BaseCommand):
    help = (
        "Create deterministic EldVatten development users "
        "and organization assignments."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev_data can only run when DEBUG is enabled."
            )

        call_command(
            "seed_reference_data",
        )

        call_command(
            "seed_organization_data",
        )

        su_test, _ = User.objects.get_or_create(
            username="suTest",
        )

        su_test.display_name = "Superuser Test"
        su_test.email = "sutest@example.test"
        su_test.account_status = AccountStatus.MEMBER
        su_test.is_active = True
        su_test.is_staff = True
        su_test.is_superuser = True
        su_test.push_prompt_seen = False

        su_test.set_password(
            SUPERUSER_PASSWORD
        )

        su_test.save()

        staff_user_numbers = (
            ALL_FORUM_PERMISSION_USERS
            | STAFF_ONLY_USERS
            | set().union(
                *FORUM_PERMISSION_USERS.values()
            )
        )

        test_users = []

        for user_number in range(
            1,
            TEST_USER_COUNT + 1,
        ):
            username = (
                f"testuser{user_number:02d}"
            )

            account_status = (
                ACCOUNT_STATUS_OVERRIDES.get(
                    user_number,
                    AccountStatus.MEMBER,
                )
            )

            user, _ = User.objects.get_or_create(
                username=username,
            )

            user.display_name = (
                f"Test User {user_number:02d}"
            )

            user.email = (
                f"{username}@example.test"
            )

            user.account_status = account_status

            user.is_active = (
                account_status
                != AccountStatus.DISABLED
            )

            user.is_staff = (
                user_number
                in staff_user_numbers
            )

            user.is_superuser = False
            user.push_prompt_seen = False

            user.set_password(
                TEST_PASSWORD
            )

            user.save()

            test_users.append(
                user
            )

        forum_permissions = {
            permission.codename: permission
            for permission
            in Permission.objects.filter(
                content_type__app_label="community",
                codename__in=(
                    FORUM_PERMISSION_CODENAMES
                ),
            )
        }

        missing_permission_codenames = (
            set(
                FORUM_PERMISSION_CODENAMES
            )
            - set(
                forum_permissions
            )
        )

        if missing_permission_codenames:
            raise CommandError(
                "Missing forum permissions: "
                + ", ".join(
                    sorted(
                        missing_permission_codenames
                    )
                )
            )

        for user_number, user in enumerate(
            test_users,
            start=1,
        ):
            permission_codenames = set()

            if (
                user_number
                in ALL_FORUM_PERMISSION_USERS
            ):
                permission_codenames.update(
                    FORUM_PERMISSION_CODENAMES
                )

            for (
                codename,
                user_numbers,
            ) in (
                FORUM_PERMISSION_USERS.items()
            ):
                if user_number in user_numbers:
                    permission_codenames.add(
                        codename
                    )

            user.user_permissions.set(
                [
                    forum_permissions[
                        codename
                    ]
                    for codename
                    in permission_codenames
                ]
            )

        citizenship_classes = {
            record.name: record
            for record
            in CitizenshipClass.objects.all()
        }

        social_ranks = {
            record.name: record
            for record
            in SocialRank.objects.all()
        }

        chapters = {
            record.name: record
            for record
            in Chapter.objects.all()
        }

        households = {
            record.name: record
            for record
            in Household.objects.all()
        }

        offices = {
            record.name: record
            for record
            in Office.objects.all()
        }

        governance_bodies = {
            record.name: record
            for record
            in GovernanceBody.objects.all()
        }

        orders = {
            record.name: record
            for record
            in Order.objects.all()
        }

        order_ranks = {
            record.name: record
            for record
            in OrderRank.objects.all()
        }

        leadership_types = {
            record.name: record
            for record
            in HouseholdLeadershipType.objects.all()
        }

        required_names = {
            "citizenship classes": (
                citizenship_classes,
                {
                    "Active Citizen",
                    "Honorary Citizen",
                    "Initiate Citizen",
                    "Allied Individual",
                },
            ),
            "social ranks": (
                social_ranks,
                {
                    "Lysingr",
                    "Karl",
                    "Thegn",
                    "Jarl",
                    "Godi",
                },
            ),
            "chapters": (
                chapters,
                {
                    "Fyr Draca Chapter",
                    "Indiana Chapter",
                    "Seattle Chapter",
                },
            ),
            "households": (
                households,
                {
                    "House Hvit Hrafn",
                    "House Kraken",
                    "House Stormhammer",
                    "House Three Horns",
                    "House Svartur Hrafn",
                    "House Silver Zigenare",
                },
            ),
            "offices": (
                offices,
                {
                    "Lawspeaker",
                    "Hersir",
                    "Stallari",
                    "Kesserer",
                    "Skafari",
                    "Skald",
                    "Vard",
                },
            ),
            "governance bodies": (
                governance_bodies,
                {
                    "Godi Council",
                    "Lagstifstande Council",
                },
            ),
            "orders": (
                orders,
                {
                    "Order of Air",
                    "Order of Earth",
                    "Order of Fire",
                    "Order of Water",
                    "Krig Grisar",
                },
            ),
            "order ranks": (
                order_ranks,
                {
                    "Larling",
                    "Gesallen",
                    "Ledar",
                },
            ),
            "household leadership types": (
                leadership_types,
                {
                    "Leading Jarl",
                },
            ),
        }

        for (
            label,
            (
                records,
                expected_names,
            ),
        ) in required_names.items():
            missing_names = (
                expected_names
                - set(
                    records
                )
            )

            if missing_names:
                raise CommandError(
                    f"Missing {label}: "
                    + ", ".join(
                        sorted(
                            missing_names
                        )
                    )
                )

        test_group, _ = (
            CommunityGroup.objects.update_or_create(
                name=TEST_GROUP_NAME,
                defaults={
                    "description": (
                        "Development-only group "
                        "for access-control testing."
                    ),
                    "is_assignable": True,
                },
            )
        )

        CitizenshipRecord.objects.filter(
            user__in=test_users,
        ).delete()

        UserSocialRank.objects.filter(
            user__in=test_users,
        ).delete()

        UserOffice.objects.filter(
            user__in=test_users,
        ).delete()

        HouseholdMembership.objects.filter(
            user__in=test_users,
        ).delete()

        HouseholdLeadership.objects.filter(
            user__in=test_users,
        ).delete()

        GovernanceMembership.objects.filter(
            user__in=test_users,
        ).delete()

        OrderMembership.objects.filter(
            user__in=test_users,
        ).delete()

        GroupMembership.objects.filter(
            user__in=test_users,
            community_group=test_group,
        ).delete()

        InitiateSponsorship.objects.filter(
            initiate__in=test_users,
        ).delete()

        chapter_names = [
            "Fyr Draca Chapter",
            "Indiana Chapter",
            "Seattle Chapter",
        ]

        household_names = [
            "House Hvit Hrafn",
            "House Kraken",
            "House Stormhammer",
            "House Three Horns",
            "House Svartur Hrafn",
            "House Silver Zigenare",
        ]

        office_names = [
            "Lawspeaker",
            "Hersir",
            "Stallari",
            "Kesserer",
            "Skafari",
            "Skald",
            "Vard",
        ]

        order_names = [
            "Order of Air",
            "Order of Earth",
            "Order of Fire",
            "Order of Water",
            "Krig Grisar",
        ]

        ranked_order_names = {
            "Order of Air",
            "Order of Earth",
            "Order of Fire",
            "Order of Water",
        }

        order_rank_names = [
            "Larling",
            "Gesallen",
            "Ledar",
        ]

        for user_number, user in enumerate(
            test_users,
            start=1,
        ):
            chapter = chapters[
                chapter_names[
                    (
                        user_number
                        - 1
                    )
                    % len(
                        chapter_names
                    )
                ]
            ]

            if user_number <= 39:
                citizenship_name = (
                    "Active Citizen"
                )

            elif user_number <= 44:
                citizenship_name = (
                    "Honorary Citizen"
                )

            elif user_number <= 48:
                citizenship_name = (
                    "Initiate Citizen"
                )

            else:
                citizenship_name = (
                    "Allied Individual"
                )

            if user_number <= 15:
                social_rank_name = "Jarl"

            elif user_number <= 18:
                social_rank_name = "Godi"

            elif user_number <= 39:
                social_rank_name = "Thegn"

            elif user_number <= 44:
                social_rank_name = "Karl"

            elif user_number <= 48:
                social_rank_name = "Lysingr"

            else:
                social_rank_name = "Karl"

            if user_number <= 18:
                household_name = (
                    household_names[
                        (
                            user_number
                            - 1
                        )
                        // 3
                    ]
                )

            else:
                household_name = (
                    household_names[
                        (
                            user_number
                            - 1
                        )
                        % len(
                            household_names
                        )
                    ]
                )

            household = (
                households[
                    household_name
                ]
            )

            CitizenshipRecord.objects.create(
                user=user,
                citizenship_class=(
                    citizenship_classes[
                        citizenship_name
                    ]
                ),
                chapter=chapter,
                started_at=TEST_STARTED_AT,
                changed_by=su_test,
                notes=(
                    "Created by seed_dev_data."
                ),
            )

            UserSocialRank.objects.create(
                user=user,
                social_rank=(
                    social_ranks[
                        social_rank_name
                    ]
                ),
                started_at=TEST_STARTED_AT,
                changed_by=su_test,
                notes=(
                    "Created by seed_dev_data."
                ),
            )

            HouseholdMembership.objects.create(
                user=user,
                household=household,
                started_at=TEST_STARTED_AT,
                changed_by=su_test,
                notes=(
                    "Created by seed_dev_data."
                ),
            )

            if user_number <= 18:
                HouseholdLeadership.objects.create(
                    user=user,
                    household=household,
                    leadership_type=(
                        leadership_types[
                            "Leading Jarl"
                        ]
                    ),
                    started_at=TEST_STARTED_AT,
                    changed_by=su_test,
                    notes=(
                        "Created by seed_dev_data."
                    ),
                )

            if (
                16
                <= user_number
                <= 18
            ):
                GovernanceMembership.objects.create(
                    user=user,
                    governance_body=(
                        governance_bodies[
                            "Godi Council"
                        ]
                    ),
                    started_at=TEST_STARTED_AT,
                    changed_by=su_test,
                    notes=(
                        "Created by seed_dev_data."
                    ),
                )

            if user_number <= 39:
                GovernanceMembership.objects.create(
                    user=user,
                    governance_body=(
                        governance_bodies[
                            "Lagstifstande Council"
                        ]
                    ),
                    started_at=TEST_STARTED_AT,
                    changed_by=su_test,
                    notes=(
                        "Development materialization "
                        "of derived Lagstifstande "
                        "membership."
                    ),
                )

            if (
                19
                <= user_number
                <= 39
            ):
                office_index = (
                    (
                        user_number
                        - 19
                    )
                    // 3
                )

                UserOffice.objects.create(
                    user=user,
                    office=(
                        offices[
                            office_names[
                                office_index
                            ]
                        ]
                    ),
                    chapter=chapter,
                    started_at=TEST_STARTED_AT,
                    changed_by=su_test,
                    notes=(
                        "Created by seed_dev_data."
                    ),
                )

            order_name = (
                order_names[
                    (
                        user_number
                        - 1
                    )
                    % len(
                        order_names
                    )
                ]
            )

            order = orders[
                order_name
            ]

            order_rank = None

            if (
                order_name
                in ranked_order_names
            ):
                order_batch = (
                    (
                        user_number
                        - 1
                    )
                    // len(
                        order_names
                    )
                )

                order_rank_name = (
                    order_rank_names[
                        order_batch
                        % len(
                            order_rank_names
                        )
                    ]
                )

                order_rank = (
                    order_ranks[
                        order_rank_name
                    ]
                )

            OrderMembership.objects.create(
                user=user,
                order=order,
                order_rank=order_rank,
                started_at=TEST_STARTED_AT,
                changed_by=su_test,
                notes=(
                    "Created by seed_dev_data."
                ),
            )

        custom_group_user_numbers = {
            1,
            16,
            19,
            22,
            40,
            52,
        }

        for user_number in (
            custom_group_user_numbers
        ):
            GroupMembership.objects.create(
                user=(
                    test_users[
                        user_number
                        - 1
                    ]
                ),
                community_group=test_group,
                started_at=TEST_STARTED_AT,
                changed_by=su_test,
                notes=(
                    "Created by seed_dev_data."
                ),
            )

        initiate_users = (
            test_users[
                44:48
            ]
        )

        primary_sponsors = [
            test_users[39],
            test_users[40],
            test_users[41],
        ]

        secondary_sponsors = [
            test_users[43],
            test_users[49],
            test_users[50],
        ]

        for index, initiate in enumerate(
            initiate_users
        ):
            InitiateSponsorship.objects.create(
                initiate=initiate,
                sponsor=(
                    primary_sponsors[
                        index
                        % len(
                            primary_sponsors
                        )
                    ]
                ),
                sponsor_type=(
                    InitiateSponsorship
                    .SponsorType
                    .PRIMARY
                ),
                started_at=TEST_STARTED_AT,
                changed_by=su_test,
                notes=(
                    "Created by seed_dev_data."
                ),
            )

            InitiateSponsorship.objects.create(
                initiate=initiate,
                sponsor=(
                    secondary_sponsors[
                        index
                        % len(
                            secondary_sponsors
                        )
                    ]
                ),
                sponsor_type=(
                    InitiateSponsorship
                    .SponsorType
                    .SECONDARY
                ),
                started_at=TEST_STARTED_AT,
                changed_by=su_test,
                notes=(
                    "Created by seed_dev_data."
                ),
            )

        self.validate_coverage(
            test_users=test_users,
            test_group=test_group,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Development data seeded successfully."
            )
        )

        self.stdout.write(
            f"Test users: {len(test_users)}"
        )

        self.stdout.write(
            "Test user password: "
            "Eldvatten!123_"
        )

        self.stdout.write(
            "suTest password: "
            "testpassword"
        )

    def validate_coverage(
        self,
        *,
        test_users,
        test_group,
    ):
        test_user_ids = [
            user.pk
            for user in test_users
        ]

        if (
            len(
                test_user_ids
            )
            != TEST_USER_COUNT
        ):
            raise CommandError(
                f"Expected {TEST_USER_COUNT} "
                f"test users, found "
                f"{len(test_user_ids)}."
            )

        for status in (
            AccountStatus.MEMBER,
            AccountStatus.PENDING,
            AccountStatus.SUSPENDED,
            AccountStatus.DISABLED,
        ):
            count = (
                User.objects.filter(
                    pk__in=test_user_ids,
                    account_status=status,
                )
                .count()
            )

            if count < 3:
                raise CommandError(
                    f"Account status {status} "
                    f"has only {count} "
                    f"test users."
                )

        coverage_checks = (
            (
                "citizenship class",
                CitizenshipClass.objects.all(),
                lambda record:
                    CitizenshipRecord.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        citizenship_class=(
                            record
                        ),
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "social rank",
                SocialRank.objects.all(),
                lambda record:
                    UserSocialRank.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        social_rank=record,
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "chapter",
                Chapter.objects.all(),
                lambda record:
                    CitizenshipRecord.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        chapter=record,
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "household",
                Household.objects.all(),
                lambda record:
                    HouseholdMembership.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        household=record,
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "office",
                Office.objects.all(),
                lambda record:
                    UserOffice.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        office=record,
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "governance body",
                GovernanceBody.objects.all(),
                lambda record:
                    GovernanceMembership.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        governance_body=(
                            record
                        ),
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "order",
                Order.objects.all(),
                lambda record:
                    OrderMembership.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        order=record,
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "order rank",
                OrderRank.objects.all(),
                lambda record:
                    OrderMembership.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        order_rank=record,
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
            (
                "household leadership type",
                (
                    HouseholdLeadershipType
                    .objects
                    .all()
                ),
                lambda record:
                    HouseholdLeadership.objects
                    .filter(
                        user_id__in=(
                            test_user_ids
                        ),
                        leadership_type=(
                            record
                        ),
                        ended_at__isnull=True,
                    )
                    .count(),
            ),
        )

        for (
            label,
            records,
            count_for_record,
        ) in coverage_checks:
            for record in records:
                count = count_for_record(
                    record
                )

                if count < 3:
                    raise CommandError(
                        f"{label.title()} "
                        f"{record} has only "
                        f"{count} test users."
                    )

        for household in (
            Household.objects.all()
        ):
            leader_count = (
                HouseholdLeadership
                .objects
                .filter(
                    user_id__in=(
                        test_user_ids
                    ),
                    household=household,
                    leadership_type__name=(
                        "Leading Jarl"
                    ),
                    ended_at__isnull=True,
                )
                .count()
            )

            if leader_count < 3:
                raise CommandError(
                    f"Household {household} "
                    f"has only "
                    f"{leader_count} "
                    f"test leaders."
                )

        group_member_count = (
            GroupMembership.objects.filter(
                user_id__in=test_user_ids,
                community_group=test_group,
                ended_at__isnull=True,
            )
            .count()
        )

        if group_member_count < 5:
            raise CommandError(
                f"{TEST_GROUP_NAME} has only "
                f"{group_member_count} "
                f"test members."
            )

        for sponsor_type in (
            InitiateSponsorship
            .SponsorType
            .PRIMARY,
            InitiateSponsorship
            .SponsorType
            .SECONDARY,
        ):
            sponsorship_count = (
                InitiateSponsorship
                .objects
                .filter(
                    initiate_id__in=(
                        test_user_ids
                    ),
                    sponsor_type=(
                        sponsor_type
                    ),
                    ended_at__isnull=True,
                )
                .count()
            )

            if sponsorship_count < 3:
                raise CommandError(
                    f"Sponsorship type "
                    f"{sponsor_type} "
                    f"has only "
                    f"{sponsorship_count} "
                    f"test assignments."
                )

        for codename in (
            FORUM_PERMISSION_CODENAMES
        ):
            permission_count = (
                User.objects
                .filter(
                    pk__in=test_user_ids,
                    user_permissions__content_type__app_label=(
                        "community"
                    ),
                    user_permissions__codename=(
                        codename
                    ),
                )
                .distinct()
                .count()
            )

            if permission_count < 3:
                raise CommandError(
                    f"Forum permission "
                    f"{codename} "
                    f"has only "
                    f"{permission_count} "
                    f"test users."
                )