from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .auth_utils import EDITOR_SESSION_KEY
from .forms import InstallmentPaymentForm, LoanForm
from .models import FundAdjustment, Installment, Loan, Member, MemberInterestPayout, MonthlyContribution


class LoanFormTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(full_name="AKSHAY")

    def test_loan_form_uses_manual_upfront_interest_and_principal_only_installments(self):
        form = LoanForm(
            data={
                "member": self.member.id,
                "principal_amount": "12000",
                "interest_amount": "1200",
                "issued_on": "2026-04-01",
                "installment_count": 6,
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        loan = form.save()

        self.assertEqual(loan.interest_amount, Decimal("1200.00"))
        self.assertEqual(loan.net_disbursed_amount, Decimal("10800.00"))
        self.assertEqual(loan.interest_rate_percent, Decimal("0.00"))
        self.assertEqual(loan.installment_amount, Decimal("2000.00"))
        self.assertEqual(loan.installments.count(), 6)
        self.assertEqual(loan.installments.first().amount_due, Decimal("2000.00"))
        self.assertEqual(loan.installments.last().due_date, date(2026, 10, 1))

    def test_loan_form_rejects_interest_greater_than_principal(self):
        form = LoanForm(
            data={
                "member": self.member.id,
                "principal_amount": "1000",
                "interest_amount": "1000.01",
                "issued_on": "2026-04-01",
                "installment_count": 1,
                "notes": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("interest_amount", form.errors)


class AccessControlTests(TestCase):
    def enable_editor_access(self):
        session = self.client.session
        session[EDITOR_SESSION_KEY] = True
        session.save()

    def test_home_page_is_public(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_read_only_user_cannot_open_edit_pages(self):
        contribution_response = self.client.get("/payments/new/")

        self.assertEqual(contribution_response.status_code, 403)

    def test_editor_password_unlock_allows_edit_pages(self):
        self.enable_editor_access()

        response = self.client.get("/payments/new/")

        self.assertEqual(response.status_code, 200)

    def test_editor_can_open_existing_record_edit_page(self):
        member = Member.objects.create(full_name="AKSHAY")
        contribution = MonthlyContribution.objects.create(
            member=member,
            month=date(2026, 4, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 4, 1),
            status=MonthlyContribution.Status.PAID,
        )
        self.enable_editor_access()

        response = self.client.get(f"/contributions/{contribution.id}/edit/")

        self.assertEqual(response.status_code, 200)


class InstallmentPaymentFormTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(full_name="CHIRAG")
        self.loan = Loan.objects.create(
            member=self.member,
            principal_amount=Decimal("11000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("605.00"),
            net_disbursed_amount=Decimal("10395.00"),
            issued_on=date(2026, 4, 1),
            installment_count=11,
            installment_amount=Decimal("1000.00"),
        )
        self.installment = Installment.objects.create(
            loan=self.loan,
            installment_number=1,
            due_date=date(2026, 5, 1),
            amount_due=Decimal("1000.00"),
        )

    def test_installment_payment_marks_installment_paid(self):
        form = InstallmentPaymentForm(
            data={
                "installment": self.installment.id,
                "amount_paid": "1000.00",
                "paid_on": "2026-05-01",
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        installment = form.save()
        self.loan.refresh_from_db()

        self.assertEqual(installment.status, Installment.Status.PAID)
        self.assertEqual(installment.amount_paid, Decimal("1000.00"))
        self.assertEqual(installment.paid_on, date(2026, 5, 1))
        self.assertEqual(self.loan.status, Loan.Status.CLOSED)

    def test_installment_payment_marks_installment_partial(self):
        Installment.objects.create(
            loan=self.loan,
            installment_number=2,
            due_date=date(2026, 6, 1),
            amount_due=Decimal("1000.00"),
        )
        form = InstallmentPaymentForm(
            data={
                "installment": self.installment.id,
                "amount_paid": "500.00",
                "paid_on": "2026-05-01",
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        installment = form.save()
        self.loan.refresh_from_db()

        self.assertEqual(installment.status, Installment.Status.PARTIAL)
        self.assertEqual(installment.amount_paid, Decimal("500.00"))
        self.assertEqual(self.loan.status, Loan.Status.ACTIVE)

    def test_installment_payment_rejects_overpayment(self):
        form = InstallmentPaymentForm(
            data={
                "installment": self.installment.id,
                "amount_paid": "1000.01",
                "paid_on": timezone.localdate().isoformat(),
                "notes": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("amount_paid", form.errors)

    def test_installment_payment_closes_loan_when_last_installment_is_paid(self):
        Installment.objects.create(
            loan=self.loan,
            installment_number=2,
            due_date=date(2026, 6, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 6, 1),
            status=Installment.Status.PAID,
        )
        self.loan.status = Loan.Status.ACTIVE
        self.loan.save(update_fields=["status"])

        form = InstallmentPaymentForm(
            data={
                "installment": self.installment.id,
                "amount_paid": "1000.00",
                "paid_on": "2026-05-01",
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.loan.refresh_from_db()

        self.assertEqual(self.loan.status, Loan.Status.CLOSED)

    def test_loan_form_blocks_schedule_change_after_payment_exists(self):
        self.installment.amount_paid = Decimal("500.00")
        self.installment.status = Installment.Status.PARTIAL
        self.installment.paid_on = date(2026, 5, 1)
        self.installment.save()
        form = LoanForm(
            data={
                "member": self.member.id,
                "principal_amount": "12000.00",
                "interest_amount": "605.00",
                "issued_on": "2026-04-01",
                "installment_count": 11,
                "notes": "",
            },
            loan=self.loan,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_installment_payment_returns_overdue_loan_to_active_when_caught_up(self):
        self.installment.due_date = date(2026, 3, 1)
        self.installment.save(update_fields=["due_date"])
        self.loan.refresh_status()
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, Loan.Status.OVERDUE)

        form = InstallmentPaymentForm(
            data={
                "installment": self.installment.id,
                "amount_paid": "1000.00",
                "paid_on": "2026-04-01",
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.loan.refresh_from_db()

        self.assertEqual(self.loan.status, Loan.Status.CLOSED)


class CombinedPaymentViewTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(full_name="AKSHAY")
        session = self.client.session
        session[EDITOR_SESSION_KEY] = True
        session.save()

    @staticmethod
    def next_month_start():
        today = timezone.localdate()
        return today.replace(
            year=today.year + (today.month // 12),
            month=1 if today.month == 12 else today.month + 1,
            day=1,
        )

    def test_full_payment_auto_applies_saving_and_all_upcoming_installments(self):
        next_month = self.next_month_start()
        loan = Loan.objects.create(
            member=self.member,
            principal_amount=Decimal("6000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("0.00"),
            net_disbursed_amount=Decimal("6000.00"),
            issued_on=date(next_month.year, next_month.month - 1 if next_month.month > 1 else 12, 1),
            installment_count=2,
            installment_amount=Decimal("3000.00"),
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=next_month,
            amount_due=Decimal("3000.00"),
            status=Installment.Status.PENDING,
        )
        Installment.objects.create(
            loan=loan,
            installment_number=2,
            due_date=date(next_month.year, next_month.month, 28),
            amount_due=Decimal("3000.00"),
            status=Installment.Status.PENDING,
        )

        response = self.client.post(
            "/payments/new/",
            data={
                "member": self.member.id,
                "amount_paid": "7000.00",
                "paid_on": timezone.localdate().isoformat(),
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        contribution = MonthlyContribution.objects.get(member=self.member, month=next_month)
        self.assertEqual(contribution.amount_paid, Decimal("1000.00"))
        self.assertEqual(contribution.status, MonthlyContribution.Status.PAID)
        self.assertEqual(
            Installment.objects.filter(loan=loan, status=Installment.Status.PAID).count(),
            2,
        )

    def test_partial_payment_requires_allocation_target(self):
        next_month = self.next_month_start()
        loan = Loan.objects.create(
            member=self.member,
            principal_amount=Decimal("1000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("0.00"),
            net_disbursed_amount=Decimal("1000.00"),
            issued_on=timezone.localdate(),
            installment_count=1,
            installment_amount=Decimal("1000.00"),
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=next_month,
            amount_due=Decimal("1000.00"),
            status=Installment.Status.PENDING,
        )

        response = self.client.post(
            "/payments/new/",
            data={
                "member": self.member.id,
                "amount_paid": "500.00",
                "paid_on": timezone.localdate().isoformat(),
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select whether it is for saving or a loan installment")

    def test_partial_payment_can_be_applied_to_saving(self):
        next_month = self.next_month_start()

        response = self.client.post(
            "/payments/new/",
            data={
                "member": self.member.id,
                "amount_paid": "500.00",
                "paid_on": timezone.localdate().isoformat(),
                "allocation_target": "saving",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        contribution = MonthlyContribution.objects.get(member=self.member, month=next_month)
        self.assertEqual(contribution.amount_paid, Decimal("500.00"))
        self.assertEqual(contribution.status, MonthlyContribution.Status.PARTIAL)


class ActiveLoansReportTests(TestCase):
    def test_active_loans_report_shows_remaining_principal_and_next_due(self):
        member = Member.objects.create(full_name="MAYANK")
        loan = Loan.objects.create(
            member=member,
            principal_amount=Decimal("11000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("605.00"),
            net_disbursed_amount=Decimal("10395.00"),
            issued_on=date(2026, 4, 1),
            installment_count=11,
            installment_amount=Decimal("1000.00"),
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=date(2026, 5, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 5, 1),
            status=Installment.Status.PAID,
        )
        Installment.objects.create(
            loan=loan,
            installment_number=2,
            due_date=date(2026, 6, 1),
            amount_due=Decimal("1000.00"),
            status=Installment.Status.PENDING,
        )

        response = self.client.get("/reports/active-loans/")

        self.assertEqual(response.status_code, 200)
        report_loan = response.context["loans"][0]
        self.assertEqual(report_loan.remaining_principal, Decimal("1000.00"))
        self.assertEqual(report_loan.next_due_installment_number, 2)
        self.assertEqual(report_loan.next_due_date, date(2026, 6, 1))

    def test_active_loans_report_includes_overdue_loans(self):
        member = Member.objects.create(full_name="OM")
        loan = Loan.objects.create(
            member=member,
            principal_amount=Decimal("3000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("100.00"),
            net_disbursed_amount=Decimal("2900.00"),
            issued_on=date(2026, 1, 1),
            installment_count=3,
            installment_amount=Decimal("1000.00"),
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=date(2026, 2, 1),
            amount_due=Decimal("1000.00"),
            status=Installment.Status.PENDING,
        )

        response = self.client.get("/reports/active-loans/")

        self.assertEqual(response.status_code, 200)
        report_loan = response.context["loans"][0]
        self.assertEqual(report_loan.status, Loan.Status.OVERDUE)


class MonthlySummaryReportTests(TestCase):
    def test_monthly_summary_report_rolls_cash_forward_by_month(self):
        member = Member.objects.create(full_name="RONAK")
        MonthlyContribution.objects.create(
            member=member,
            month=date(2026, 4, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 4, 3),
            status="paid",
        )
        loan = Loan.objects.create(
            member=member,
            principal_amount=Decimal("11000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("605.00"),
            net_disbursed_amount=Decimal("10395.00"),
            issued_on=date(2026, 4, 5),
            installment_count=11,
            installment_amount=Decimal("1000.00"),
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=date(2026, 5, 5),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 5, 5),
            status=Installment.Status.PAID,
        )
        MonthlyContribution.objects.create(
            member=member,
            month=date(2026, 5, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 5, 3),
            status="paid",
        )

        response = self.client.get("/reports/monthly-summary/")

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 2)

        april_row = rows[0]
        self.assertEqual(april_row["label"], "Apr 2026")
        self.assertEqual(april_row["contributions_received"], Decimal("1000.00"))
        self.assertEqual(april_row["interest_collected"], Decimal("605.00"))
        self.assertEqual(april_row["cash_given"], Decimal("10395.00"))
        self.assertEqual(april_row["ending_cash"], Decimal("-8790.00"))

        may_row = rows[1]
        self.assertEqual(may_row["label"], "May 2026")
        self.assertEqual(may_row["contributions_received"], Decimal("1000.00"))
        self.assertEqual(may_row["installments_received"], Decimal("1000.00"))
        self.assertEqual(may_row["ending_cash"], Decimal("-6790.00"))


class MemberDetailTests(TestCase):
    def test_member_detail_shows_totals_and_histories(self):
        member = Member.objects.create(full_name="PRIYANK", phone="1234567890")
        MonthlyContribution.objects.create(
            member=member,
            month=date(2026, 4, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 4, 2),
            status=MonthlyContribution.Status.PAID,
        )
        loan = Loan.objects.create(
            member=member,
            principal_amount=Decimal("5000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("250.00"),
            net_disbursed_amount=Decimal("4750.00"),
            issued_on=date(2026, 4, 3),
            installment_count=5,
            installment_amount=Decimal("1000.00"),
            status=Loan.Status.ACTIVE,
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=date(2026, 5, 3),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 5, 3),
            status=Installment.Status.PAID,
        )
        Installment.objects.create(
            loan=loan,
            installment_number=2,
            due_date=date(2026, 6, 3),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status=Installment.Status.PENDING,
        )

        response = self.client.get(f"/members/{member.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["member"].full_name, "PRIYANK")
        self.assertEqual(response.context["outstanding_principal"], Decimal("4000.00"))
        self.assertEqual(response.context["contributions"].count(), 1)
        self.assertEqual(response.context["loans"].count(), 1)
        self.assertEqual(response.context["installments"].count(), 2)

    def test_member_report_totals_do_not_double_count_across_related_tables(self):
        member = Member.objects.create(full_name="HARSH")
        MonthlyContribution.objects.create(
            member=member,
            month=date(2026, 4, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 4, 1),
            status=MonthlyContribution.Status.PAID,
        )
        MonthlyContribution.objects.create(
            member=member,
            month=date(2026, 5, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 5, 1),
            status=MonthlyContribution.Status.PAID,
        )
        loan = Loan.objects.create(
            member=member,
            principal_amount=Decimal("3000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("150.00"),
            net_disbursed_amount=Decimal("2850.00"),
            issued_on=date(2026, 4, 3),
            installment_count=3,
            installment_amount=Decimal("1000.00"),
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=date(2026, 5, 3),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 5, 3),
            status=Installment.Status.PAID,
        )
        Installment.objects.create(
            loan=loan,
            installment_number=2,
            due_date=date(2026, 6, 3),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("500.00"),
            paid_on=date(2026, 6, 3),
            status=Installment.Status.PARTIAL,
        )

        response = self.client.get("/reports/members/")

        self.assertEqual(response.status_code, 200)
        report_member = response.context["members"].get(pk=member.pk)
        self.assertEqual(report_member.total_contributed, Decimal("2000.00"))
        self.assertEqual(report_member.total_principal_loaned, Decimal("3000.00"))
        self.assertEqual(report_member.total_interest_collected, Decimal("150.00"))
        self.assertEqual(report_member.total_cash_received, Decimal("2850.00"))
        self.assertEqual(report_member.total_installment_paid, Decimal("1500.00"))


class EditorCrudViewsTests(TestCase):
    def setUp(self):
        self.member = Member.objects.create(full_name="JAY")
        session = self.client.session
        session[EDITOR_SESSION_KEY] = True
        session.save()

    def test_editor_can_update_contribution(self):
        contribution = MonthlyContribution.objects.create(
            member=self.member,
            month=date(2026, 4, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("400.00"),
            paid_on=date(2026, 4, 2),
            status=MonthlyContribution.Status.PARTIAL,
        )

        response = self.client.post(
            f"/contributions/{contribution.id}/edit/",
            data={
                "member": self.member.id,
                "month": "2026-04-01",
                "amount_paid": "1000.00",
                "paid_on": "2026-04-02",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        contribution.refresh_from_db()
        self.assertEqual(contribution.amount_paid, Decimal("1000.00"))
        self.assertEqual(contribution.status, MonthlyContribution.Status.PAID)

    def test_editor_can_delete_installment(self):
        loan = Loan.objects.create(
            member=self.member,
            principal_amount=Decimal("2000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("100.00"),
            net_disbursed_amount=Decimal("1900.00"),
            issued_on=date(2026, 4, 1),
            installment_count=2,
            installment_amount=Decimal("1000.00"),
        )
        installment = Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=date(2026, 5, 1),
            amount_due=Decimal("1000.00"),
        )

        response = self.client.post(f"/installments/{installment.id}/delete/")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Installment.objects.filter(pk=installment.pk).exists())

    def test_editor_can_add_member(self):
        response = self.client.post(
            "/members/new/",
            data={
                "full_name": "NEW MEMBER",
                "email": "",
                "phone": "",
                "monthly_contribution_amount": "1000.00",
                "joined_on": "2026-04-07",
                "is_active": "on",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Member.objects.filter(full_name="NEW MEMBER").exists())

    def test_editor_can_give_interest_to_everybody(self):
        response = self.client.post(
            "/interest-payouts/new/",
            data={
                "amount": "123.00",
                "payout_date": "2026-04-07",
                "notes": "bulk test",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            MemberInterestPayout.objects.filter(
                payout_date=date(2026, 4, 7),
                amount=Decimal("123.00"),
            ).count(),
            Member.objects.filter(is_active=True).count(),
        )

    def test_editor_can_skip_next_savings_for_everyone(self):
        response = self.client.post("/savings/skip-next/")

        self.assertEqual(response.status_code, 302)
        skipped = MonthlyContribution.objects.filter(
            month=date(2026, 5, 1),
            amount_due=Decimal("0.00"),
        )
        self.assertEqual(skipped.count(), Member.objects.filter(is_active=True).count())

    def test_member_remove_uses_cash_plus_outstanding_installments_divided_by_active_members(self):
        other_member = Member.objects.create(full_name="PARTH")
        MonthlyContribution.objects.create(
            member=self.member,
            month=date(2026, 4, 1),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("1000.00"),
            paid_on=date(2026, 4, 1),
            status=MonthlyContribution.Status.PAID,
        )
        loan = Loan.objects.create(
            member=other_member,
            principal_amount=Decimal("2000.00"),
            interest_rate_percent=Decimal("0.00"),
            interest_amount=Decimal("100.00"),
            net_disbursed_amount=Decimal("1900.00"),
            issued_on=date(2026, 4, 2),
            installment_count=2,
            installment_amount=Decimal("1000.00"),
        )
        Installment.objects.create(
            loan=loan,
            installment_number=1,
            due_date=date(2026, 5, 2),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("500.00"),
            paid_on=date(2026, 5, 2),
            status=Installment.Status.PARTIAL,
        )
        Installment.objects.create(
            loan=loan,
            installment_number=2,
            due_date=date(2026, 6, 2),
            amount_due=Decimal("1000.00"),
            amount_paid=Decimal("0.00"),
            status=Installment.Status.PENDING,
        )

        response = self.client.get(f"/members/{self.member.id}/remove/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["available_cash_now"], Decimal("-300.00"))
        self.assertEqual(response.context["outstanding_installments_total"], Decimal("1500.00"))
        self.assertEqual(response.context["active_member_count"], 20)
        self.assertEqual(response.context["settlement_share"], Decimal("60.00"))

        post_response = self.client.post(
            f"/members/{self.member.id}/remove/",
            data={
                "payout_amount": "60.00",
                "payout_date": "2026-04-07",
                "notes": "",
            },
        )

        self.assertEqual(post_response.status_code, 302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)

    def test_member_remove_records_actual_payout_as_negative_adjustment(self):
        response = self.client.post(
            f"/members/{self.member.id}/remove/",
            data={
                "payout_amount": "250.00",
                "payout_date": "2026-04-07",
                "notes": "paid in cash",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        adjustment = FundAdjustment.objects.latest("id")
        self.assertEqual(adjustment.adjustment_date, date(2026, 4, 7))
        self.assertEqual(adjustment.amount, Decimal("-250.00"))
        self.assertIn("paid in cash", adjustment.notes)


class SeedMemberTests(TestCase):
    def test_seed_members_exist(self):
        expected_names = {
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
        }

        self.assertEqual(
            set(Member.objects.values_list("full_name", flat=True)),
            expected_names,
        )
        self.assertEqual(Member.objects.count(), 18)
        self.assertEqual(
            Loan.objects.count(),
            0,
        )


class HistoricalSnapshotTests(TestCase):
    def test_snapshot_loader_includes_april_2026_and_excludes_may_2023(self):
        call_command("load_april_2026_snapshot")

        member = Member.objects.get(full_name="AKSHAY")
        contribution_months = list(
            MonthlyContribution.objects.filter(member=member)
            .order_by("month")
            .values_list("month", flat=True)
        )

        self.assertEqual(len(contribution_months), 35)
        self.assertEqual(contribution_months[0], date(2023, 6, 1))
        self.assertEqual(contribution_months[-1], date(2026, 4, 1))

    def test_dashboard_upcoming_dues_sum_all_next_month_loans_plus_savings_from_snapshot(self):
        call_command("load_april_2026_snapshot")

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        akshay = next(
            member for member in response.context["member_upcoming_dues"]
            if member.full_name == "AKSHAY"
        )
        self.assertEqual(akshay.next_month_installment_total, Decimal("6000.00"))
        self.assertEqual(akshay.savings_due, Decimal("1000.00"))
        self.assertEqual(akshay.total_upcoming_due, Decimal("7000.00"))

    def test_snapshot_loader_sets_available_cash_to_3298(self):
        call_command("load_april_2026_snapshot")

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["available_cash_now"], Decimal("3298.00"))
