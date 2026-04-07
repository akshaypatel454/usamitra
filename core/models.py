from django.db import models
from django.utils import timezone


class Member(models.Model):
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    monthly_contribution_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1000,
    )
    joined_on = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class MonthlyContribution(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="contributions",
    )
    month = models.DateField(help_text="Use the first day of the month.")
    amount_due = models.DecimalField(max_digits=10, decimal_places=2, default=1000)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_on = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-month", "member__full_name"]
        unique_together = ("member", "month")

    def __str__(self):
        return f"{self.member.full_name} - {self.month:%Y-%m}"


class Loan(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"
        OVERDUE = "overdue", "Overdue"

    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="loans",
    )
    principal_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    interest_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    issued_on = models.DateField(default=timezone.localdate)
    installment_count = models.PositiveIntegerField(default=1)
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_on", "-id"]

    def __str__(self):
        return f"{self.member.full_name} loan {self.principal_amount}"

    def refresh_status(self):
        if not self.pk:
            return

        has_installments = self.installments.exists()
        unpaid_installments = self.installments.exclude(status=Installment.Status.PAID)
        all_paid = not unpaid_installments.exists()
        has_overdue_installments = unpaid_installments.filter(
            due_date__lt=timezone.localdate()
        ).exists()
        if has_installments and all_paid:
            next_status = self.Status.CLOSED
        elif has_overdue_installments:
            next_status = self.Status.OVERDUE
        else:
            next_status = self.Status.ACTIVE
        if self.status != next_status:
            self.status = next_status
            self.save(update_fields=["status"])


class Installment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"

    loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name="installments",
    )
    installment_number = models.PositiveIntegerField()
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_on = models.DateField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["due_date", "loan_id", "installment_number"]
        unique_together = ("loan", "installment_number")

    def __str__(self):
        return f"{self.loan.member.full_name} installment {self.installment_number}"


class FundAdjustment(models.Model):
    adjustment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["adjustment_date", "id"]

    def __str__(self):
        return f"{self.adjustment_date} adjustment {self.amount}"


class MemberInterestPayout(models.Model):
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="interest_payouts",
    )
    payout_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-payout_date", "member__full_name", "-id"]

    def __str__(self):
        return f"{self.member.full_name} interest payout {self.amount}"
