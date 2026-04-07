from decimal import Decimal

from django.db import migrations


MEMBER_NAMES = [
    "AKSHAY",
    "CHIRAG",
    "DHAVAL",
    "HARDIK",
    "HARSH",
    "JAY",
    "MAULIK",
    "MAYANK",
    "MITUL",
    "OM",
    "PARTH",
    "PRATIK",
    "PRIYANK",
    "ROHIT",
    "RONAK",
    "RUTVIK",
    "BHAVIK",
    "DHRUV",
]


def sync_members(apps, schema_editor):
    Member = apps.get_model("core", "Member")

    typo_member = Member.objects.filter(full_name="DHVAL").first()
    corrected_member = Member.objects.filter(full_name="DHAVAL").first()
    if typo_member and not corrected_member:
        typo_member.full_name = "DHAVAL"
        typo_member.monthly_contribution_amount = Decimal("1000.00")
        typo_member.is_active = True
        typo_member.save(update_fields=["full_name", "monthly_contribution_amount", "is_active"])

    bhavin_member = Member.objects.filter(full_name="BHAVIN").first()
    bhavik_member = Member.objects.filter(full_name="BHAVIK").first()
    if bhavin_member and not bhavik_member:
        bhavin_member.full_name = "BHAVIK"
        bhavin_member.monthly_contribution_amount = Decimal("1000.00")
        bhavin_member.is_active = True
        bhavin_member.save(update_fields=["full_name", "monthly_contribution_amount", "is_active"])

    for name in MEMBER_NAMES:
        Member.objects.update_or_create(
            full_name=name,
            defaults={
                "monthly_contribution_amount": Decimal("1000.00"),
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_seed_members_and_upfront_interest"),
    ]

    operations = [
        migrations.RunPython(sync_members, migrations.RunPython.noop),
    ]
