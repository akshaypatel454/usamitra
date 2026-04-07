from datetime import date
from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import Installment, Loan, Member, MonthlyContribution


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            "full_name",
            "email",
            "phone",
            "monthly_contribution_amount",
            "joined_on",
            "is_active",
            "notes",
        ]
        widgets = {
            "joined_on": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class InterestPayoutAllForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    payout_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


def next_month_same_day(value):
    year = value.year + (value.month // 12)
    month = 1 if value.month == 12 else value.month + 1
    if value.month != 12:
        year = value.year
    day = min(value.day, 28)
    return date(year, month, day)


class ContributionForm(forms.Form):
    member = forms.ModelChoiceField(queryset=Member.objects.filter(is_active=True).order_by("full_name"))
    month = forms.DateField(
        initial=lambda: timezone.localdate().replace(day=1),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    amount_paid = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"))
    paid_on = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, contribution=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.contribution = contribution
        if contribution:
            self.fields["member"].initial = contribution.member
            self.fields["month"].initial = contribution.month
            self.fields["amount_paid"].initial = contribution.amount_paid
            self.fields["paid_on"].initial = contribution.paid_on
            self.fields["notes"].initial = contribution.notes

    def clean(self):
        cleaned_data = super().clean()
        member = cleaned_data.get("member")
        month = cleaned_data.get("month")
        if member and month:
            normalized_month = month.replace(day=1)
            queryset = MonthlyContribution.objects.filter(member=member, month=normalized_month)
            if self.contribution:
                queryset = queryset.exclude(pk=self.contribution.pk)
            if queryset.exists():
                raise forms.ValidationError("A contribution already exists for this member and month.")
        return cleaned_data

    def save(self):
        member = self.cleaned_data["member"]
        month = self.cleaned_data["month"].replace(day=1)
        amount_paid = self.cleaned_data["amount_paid"]
        paid_on = self.cleaned_data["paid_on"]
        notes = self.cleaned_data["notes"]

        if self.contribution:
            contribution = self.contribution
        else:
            contribution, _ = MonthlyContribution.objects.get_or_create(
                member=member,
                month=month,
                defaults={"amount_due": member.monthly_contribution_amount},
            )
        contribution.amount_due = member.monthly_contribution_amount
        contribution.member = member
        contribution.month = month
        contribution.amount_paid = amount_paid
        contribution.paid_on = paid_on
        contribution.notes = notes
        if amount_paid >= contribution.amount_due:
            contribution.status = MonthlyContribution.Status.PAID
        elif amount_paid > 0:
            contribution.status = MonthlyContribution.Status.PARTIAL
        else:
            contribution.status = MonthlyContribution.Status.PENDING
        contribution.save()
        return contribution


class InstallmentPaymentForm(forms.Form):
    installment = forms.ModelChoiceField(
        queryset=Installment.objects.select_related("loan", "loan__member")
        .filter(loan__status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE])
        .exclude(status=Installment.Status.PAID)
        .order_by("due_date", "loan__member__full_name", "installment_number"),
        label="Installment",
    )
    amount_paid = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    paid_on = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, installment=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.installment = installment
        if installment:
            self.fields["installment"].queryset = Installment.objects.select_related(
                "loan", "loan__member"
            ).filter(pk=installment.pk)
            self.fields["installment"].initial = installment
            self.fields["amount_paid"].initial = installment.amount_paid
            self.fields["paid_on"].initial = installment.paid_on
            self.fields["notes"].initial = installment.notes
        self.fields["installment"].label_from_instance = (
            lambda installment: f"{installment.loan.member.full_name} | Due {installment.due_date:%Y-%m-%d} | Installment {installment.installment_number} | Due ${installment.amount_due}"
        )

    def clean_amount_paid(self):
        amount_paid = self.cleaned_data["amount_paid"]
        installment = self.cleaned_data.get("installment")
        if installment and amount_paid > installment.amount_due:
            raise forms.ValidationError("Payment cannot be greater than the installment amount due.")
        return amount_paid

    def save(self):
        installment = self.installment or self.cleaned_data["installment"]
        installment.amount_paid = self.cleaned_data["amount_paid"]
        installment.paid_on = self.cleaned_data["paid_on"]
        installment.notes = self.cleaned_data["notes"]
        if installment.amount_paid >= installment.amount_due:
            installment.status = Installment.Status.PAID
        elif installment.amount_paid > 0:
            installment.status = Installment.Status.PARTIAL
        else:
            installment.status = Installment.Status.PENDING
        installment.save()
        installment.loan.refresh_status()
        return installment


class LoanForm(forms.Form):
    member = forms.ModelChoiceField(queryset=Member.objects.filter(is_active=True).order_by("full_name"))
    principal_amount = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("1"))
    interest_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0"),
        initial=Decimal("0.00"),
        help_text="Enter the total interest to deduct upfront before cash is given out.",
    )
    issued_on = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    installment_count = forms.IntegerField(min_value=1, max_value=120, initial=6)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, loan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan
        if loan:
            self.fields["member"].initial = loan.member
            self.fields["principal_amount"].initial = loan.principal_amount
            self.fields["interest_amount"].initial = loan.interest_amount
            self.fields["issued_on"].initial = loan.issued_on
            self.fields["installment_count"].initial = loan.installment_count
            self.fields["notes"].initial = loan.notes

    def clean(self):
        cleaned_data = super().clean()
        principal_amount = cleaned_data.get("principal_amount")
        interest_amount = cleaned_data.get("interest_amount")

        if (
            principal_amount is not None
            and interest_amount is not None
            and interest_amount > principal_amount
        ):
            self.add_error(
                "interest_amount",
                "Upfront interest cannot be greater than the principal amount.",
            )

        if self.loan and self.loan.installments.filter(amount_paid__gt=0).exists():
            schedule_changed = any(
                [
                    principal_amount != self.loan.principal_amount,
                    cleaned_data.get("issued_on") != self.loan.issued_on,
                    cleaned_data.get("installment_count") != self.loan.installment_count,
                ]
            )
            if schedule_changed:
                raise forms.ValidationError(
                    "You cannot change principal, issue date, or installment count after installment payments have been recorded."
                )
        return cleaned_data

    def save(self):
        member = self.cleaned_data["member"]
        principal_amount = self.cleaned_data["principal_amount"]
        interest_amount = self.cleaned_data["interest_amount"]
        issued_on = self.cleaned_data["issued_on"]
        installment_count = self.cleaned_data["installment_count"]
        notes = self.cleaned_data["notes"]

        net_disbursed_amount = principal_amount - interest_amount
        installment_amount = (principal_amount / installment_count).quantize(Decimal("0.01"))
        if self.loan:
            loan = self.loan
            schedule_changed = any(
                [
                    principal_amount != loan.principal_amount,
                    issued_on != loan.issued_on,
                    installment_count != loan.installment_count,
                ]
            )
            loan.member = member
            loan.principal_amount = principal_amount
            loan.interest_rate_percent = Decimal("0.00")
            loan.interest_amount = interest_amount
            loan.net_disbursed_amount = net_disbursed_amount
            loan.issued_on = issued_on
            loan.installment_count = installment_count
            loan.installment_amount = installment_amount
            loan.notes = notes
            loan.save()
            if schedule_changed:
                loan.installments.all().delete()
                due_date = next_month_same_day(issued_on)
                remaining = principal_amount
                for index in range(1, installment_count + 1):
                    amount_due = installment_amount if index < installment_count else remaining
                    Installment.objects.create(
                        loan=loan,
                        installment_number=index,
                        due_date=due_date,
                        amount_due=amount_due,
                    )
                    remaining -= amount_due
                    due_date = next_month_same_day(due_date)
            loan.refresh_status()
        else:
            loan = Loan.objects.create(
                member=member,
                principal_amount=principal_amount,
                interest_rate_percent=Decimal("0.00"),
                interest_amount=interest_amount,
                net_disbursed_amount=net_disbursed_amount,
                issued_on=issued_on,
                installment_count=installment_count,
                installment_amount=installment_amount,
                notes=notes,
            )

            due_date = next_month_same_day(issued_on)
            remaining = principal_amount
            for index in range(1, installment_count + 1):
                amount_due = installment_amount if index < installment_count else remaining
                Installment.objects.create(
                    loan=loan,
                    installment_number=index,
                    due_date=due_date,
                    amount_due=amount_due,
                )
                remaining -= amount_due
                due_date = next_month_same_day(due_date)

        return loan
