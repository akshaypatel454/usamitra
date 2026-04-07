from decimal import Decimal

from django.db import migrations, models


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


def seed_members(apps, schema_editor):
    Member = apps.get_model("core", "Member")
    for name in MEMBER_NAMES:
        Member.objects.update_or_create(
            full_name=name,
            defaults={
                "monthly_contribution_amount": Decimal("1000.00"),
                "is_active": True,
            },
        )


def backfill_loan_amounts(apps, schema_editor):
    Loan = apps.get_model("core", "Loan")
    for loan in Loan.objects.all():
        loan.net_disbursed_amount = loan.principal_amount
        loan.interest_amount = Decimal("0.00")
        loan.interest_rate_percent = Decimal("0.00")
        loan.save(
            update_fields=[
                "net_disbursed_amount",
                "interest_amount",
                "interest_rate_percent",
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="loan",
            name="interest_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="loan",
            name="interest_rate_percent",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name="loan",
            name="net_disbursed_amount",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.RunPython(seed_members, migrations.RunPython.noop),
        migrations.RunPython(backfill_loan_amounts, migrations.RunPython.noop),
    ]
