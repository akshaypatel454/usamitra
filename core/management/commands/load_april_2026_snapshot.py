from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from core.models import FundAdjustment, Installment, Loan, Member, MemberInterestPayout, MonthlyContribution


SNAPSHOT_DATE = date(2026, 4, 1)
LAST_MONTH_DATE = date(2026, 3, 1)
SNAPSHOT_AVAILABLE_CASH = Decimal("3298.00")
HISTORICAL_TAG = "[APR2026-HISTORICAL]"
MEMBER_ALIASES = {
    "PARH": "PARTH",
}

LOAN_DEFINITIONS = [
    {
        "member": "PRIYANK",
        "principal_amount": Decimal("6060.00"),
        "interest_amount": Decimal("60.00"),
        "net_disbursed_amount": Decimal("6000.00"),
        "installment_count": 1,
        "installment_amount": Decimal("6060.00"),
        "paid_installments": 0,
        "label": "One-month 6000 cash loan repaid 6060 next month",
    },
    {
        "member": "RONAK",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 9,
        "label": "11000 round",
    },
    {
        "member": "ROHIT",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 7,
        "label": "11000 round",
    },
    {
        "member": "PRIYANK",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 6,
        "label": "11000 round",
    },
    {
        "member": "AKSHAY",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 5,
        "label": "11000 round",
    },
    {
        "member": "DHRUV",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 5,
        "label": "11000 round",
    },
    {
        "member": "CHIRAG",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 3,
        "label": "11000 round",
    },
    {
        "member": "BHAVIK",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 2,
        "label": "11000 round",
    },
    {
        "member": "MAYANK",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 0,
        "label": "11000 round",
    },
    {
        "member": "MAULIK",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 0,
        "label": "11000 round",
    },
    {
        "member": "OM",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 0,
        "label": "11000 round",
    },
    {
        "member": "ROHIT",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 0,
        "label": "11000 round second loan",
    },
    {
        "member": "DHRUV",
        "principal_amount": Decimal("11000.00"),
        "interest_amount": Decimal("605.00"),
        "net_disbursed_amount": Decimal("10395.00"),
        "installment_count": 11,
        "installment_amount": Decimal("1000.00"),
        "paid_installments": 0,
        "label": "11000 round second loan",
    },
    {
        "member": "CHIRAG",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 19,
        "label": "50000 round one",
    },
    {
        "member": "ROHIT",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 18,
        "label": "50000 round one",
    },
    {
        "member": "HARSH",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 17,
        "label": "50000 round one",
    },
    {
        "member": "PRIYANK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 16,
        "label": "50000 round one",
    },
    {
        "member": "MAULIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 15,
        "label": "50000 round one",
    },
    {
        "member": "AKSHAY",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 14,
        "label": "50000 round one",
    },
    {
        "member": "MITUL",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 13,
        "label": "50000 round one",
    },
    {
        "member": "BHAVIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 12,
        "label": "50000 round one",
    },
    {
        "member": "RUTVIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 11,
        "label": "50000 round one",
    },
    {
        "member": "PARTH",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 10,
        "label": "50000 round one",
    },
    {
        "member": "HARDIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 10,
        "label": "50000 round one",
    },
    {
        "member": "DHAVAL",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 9,
        "label": "50000 round one",
    },
    {
        "member": "DHRUV",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 8,
        "label": "50000 round one",
    },
    {
        "member": "BHAVIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 6,
        "label": "50000 round two",
    },
    {
        "member": "RONAK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 5,
        "label": "50000 round two",
    },
    {
        "member": "PARH",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 5,
        "label": "50000 round two",
    },
    {
        "member": "HARDIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 4,
        "label": "50000 round two",
    },
    {
        "member": "OM",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 4,
        "label": "50000 round two",
    },
    {
        "member": "MAULIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 3,
        "label": "50000 round two",
    },
    {
        "member": "ROHIT",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 3,
        "label": "50000 round two",
    },
    {
        "member": "AKSHAY",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 2,
        "label": "50000 round two",
    },
    {
        "member": "RUTVIK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 2,
        "label": "50000 round two",
    },
    {
        "member": "MAYANK",
        "principal_amount": Decimal("50000.00"),
        "interest_amount": Decimal("5000.00"),
        "net_disbursed_amount": Decimal("45000.00"),
        "installment_count": 20,
        "installment_amount": Decimal("2500.00"),
        "paid_installments": 1,
        "label": "50000 round two",
    },
]


def canonical_name(name):
    return MEMBER_ALIASES.get(name.upper(), name.upper())


def add_months(value, months):
    month_index = (value.year * 12 + value.month - 1) + months
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


class Command(BaseCommand):
    help = "Load the historical Savings Fund snapshot as of April 1, 2026."

    @transaction.atomic
    def handle(self, *args, **options):
        members = {
            member.full_name: member
            for member in Member.objects.all()
        }
        if len(members) != 18:
            raise RuntimeError("Expected the 18 seeded members before loading the historical snapshot.")

        contribution_months = [add_months(SNAPSHOT_DATE, offset - 34) for offset in range(35)]
        contribution_count = 0
        for member in members.values():
            member.joined_on = date(2023, 5, 1)
            member.monthly_contribution_amount = Decimal("1000.00")
            member.is_active = True
            member.save(update_fields=["joined_on", "monthly_contribution_amount", "is_active"])
            for month in contribution_months:
                MonthlyContribution.objects.update_or_create(
                    member=member,
                    month=month,
                    defaults={
                        "amount_due": Decimal("1000.00"),
                        "amount_paid": Decimal("1000.00"),
                        "paid_on": month,
                        "status": MonthlyContribution.Status.PAID,
                        "notes": f"{HISTORICAL_TAG} Historical monthly savings installment.",
                    },
                )
                contribution_count += 1
            MemberInterestPayout.objects.update_or_create(
                member=member,
                payout_date=LAST_MONTH_DATE,
                notes=f"{HISTORICAL_TAG} Interest payout distributed equally to all members.",
                defaults={"amount": Decimal("4000.00")},
            )

        created_loans = 0
        created_installments = 0
        for index, definition in enumerate(LOAN_DEFINITIONS, start=1):
            member = members[canonical_name(definition["member"])]
            paid_installments = definition["paid_installments"]
            issued_on = add_months(SNAPSHOT_DATE, -paid_installments)
            note = (
                f"{HISTORICAL_TAG} Snapshot loan #{index}. "
                f"{definition['label']}. Paid installments as of 2026-04-01: {paid_installments}."
            )

            loan = Loan.objects.filter(notes=note).first()
            if loan is None:
                loan = Loan.objects.create(
                    member=member,
                    principal_amount=definition["principal_amount"],
                    interest_rate_percent=Decimal("0.00"),
                    interest_amount=definition["interest_amount"],
                    net_disbursed_amount=definition["net_disbursed_amount"],
                    issued_on=issued_on,
                    installment_count=definition["installment_count"],
                    installment_amount=definition["installment_amount"],
                    notes=note,
                )
                created_loans += 1
            else:
                loan.member = member
                loan.principal_amount = definition["principal_amount"]
                loan.interest_rate_percent = Decimal("0.00")
                loan.interest_amount = definition["interest_amount"]
                loan.net_disbursed_amount = definition["net_disbursed_amount"]
                loan.issued_on = issued_on
                loan.installment_count = definition["installment_count"]
                loan.installment_amount = definition["installment_amount"]
                loan.notes = note
                loan.save()

            for installment_number in range(1, definition["installment_count"] + 1):
                due_date = add_months(issued_on, installment_number)
                is_paid = installment_number <= paid_installments
                amount_due = definition["installment_amount"]
                amount_paid = amount_due if is_paid else Decimal("0.00")
                status = Installment.Status.PAID if is_paid else Installment.Status.PENDING
                installment, created = Installment.objects.update_or_create(
                    loan=loan,
                    installment_number=installment_number,
                    defaults={
                        "due_date": due_date,
                        "amount_due": amount_due,
                        "amount_paid": amount_paid,
                        "paid_on": due_date if is_paid else None,
                        "status": status,
                        "notes": f"{HISTORICAL_TAG} Historical installment snapshot.",
                    },
                )
                if created:
                    created_installments += 1

            loan.refresh_status()

        contribution_total = MonthlyContribution.objects.aggregate(total_sum=Sum("amount_paid"))["total_sum"] or Decimal("0.00")
        installment_total = Installment.objects.aggregate(total_sum=Sum("amount_paid"))["total_sum"] or Decimal("0.00")
        interest_total = Loan.objects.aggregate(total_sum=Sum("interest_amount"))["total_sum"] or Decimal("0.00")
        interest_paid_out_total = MemberInterestPayout.objects.aggregate(total_sum=Sum("amount"))["total_sum"] or Decimal("0.00")
        net_disbursed_total = Loan.objects.aggregate(total_sum=Sum("net_disbursed_amount"))["total_sum"] or Decimal("0.00")
        current_balance = (
            contribution_total
            + installment_total
            + interest_total
            - net_disbursed_total
            - interest_paid_out_total
        )
        balance_to_zero = SNAPSHOT_AVAILABLE_CASH - current_balance
        FundAdjustment.objects.filter(
            adjustment_date=SNAPSHOT_DATE,
            notes__startswith=HISTORICAL_TAG,
        ).delete()
        FundAdjustment.objects.create(
            adjustment_date=SNAPSHOT_DATE,
            amount=balance_to_zero,
            notes=f"{HISTORICAL_TAG} Balance snapshot cash to {SNAPSHOT_AVAILABLE_CASH} as of 2026-04-01.",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded April 2026 snapshot: {contribution_count} contribution rows, "
                f"{created_loans} loans created, {created_installments} installments created."
            )
        )
