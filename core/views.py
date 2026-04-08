from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .auth_utils import EDITOR_SESSION_KEY, editor_required, password_matches
from .forms import (
    CombinedPaymentForm,
    ContributionForm,
    InstallmentPaymentForm,
    InterestPayoutAllForm,
    LoanForm,
    MemberRemovalForm,
    MemberForm,
)
from .models import FundAdjustment, Installment, Loan, Member, MemberInterestPayout, MonthlyContribution


def refresh_open_loan_statuses():
    for loan in Loan.objects.exclude(status=Loan.Status.CLOSED):
        loan.refresh_status()


def month_key(value):
    return value.strftime("%Y-%m")


def month_label(value):
    return value.strftime("%b %Y")


def member_with_totals_queryset():
    contribution_totals = MonthlyContribution.objects.filter(
        member=OuterRef("pk")
    ).values("member").annotate(
        total=Coalesce(Sum("amount_paid"), Value(Decimal("0.00")))
    ).values("total")[:1]
    loan_principal_totals = Loan.objects.filter(
        member=OuterRef("pk")
    ).values("member").annotate(
        total=Coalesce(Sum("principal_amount"), Value(Decimal("0.00")))
    ).values("total")[:1]
    interest_totals = Loan.objects.filter(
        member=OuterRef("pk")
    ).values("member").annotate(
        total=Coalesce(Sum("interest_amount"), Value(Decimal("0.00")))
    ).values("total")[:1]
    cash_received_totals = Loan.objects.filter(
        member=OuterRef("pk")
    ).values("member").annotate(
        total=Coalesce(Sum("net_disbursed_amount"), Value(Decimal("0.00")))
    ).values("total")[:1]
    installment_totals = Installment.objects.filter(
        loan__member=OuterRef("pk")
    ).values("loan__member").annotate(
        total=Coalesce(Sum("amount_paid"), Value(Decimal("0.00")))
    ).values("total")[:1]
    savings_payment_counts = MonthlyContribution.objects.filter(
        member=OuterRef("pk"),
        amount_paid__gt=0,
    ).values("member").annotate(total=Count("id")).values("total")[:1]
    installment_payment_counts = Installment.objects.filter(
        loan__member=OuterRef("pk"),
        amount_paid__gt=0,
    ).values("loan__member").annotate(total=Count("id")).values("total")[:1]
    latest_saving_paid_on = MonthlyContribution.objects.filter(
        member=OuterRef("pk"),
        amount_paid__gt=0,
    ).order_by("-paid_on").values("paid_on")[:1]
    latest_installment_paid_on = Installment.objects.filter(
        loan__member=OuterRef("pk"),
        amount_paid__gt=0,
    ).order_by("-paid_on").values("paid_on")[:1]

    return Member.objects.annotate(
        total_contributed=Coalesce(Subquery(contribution_totals), Value(Decimal("0.00"))),
        total_principal_loaned=Coalesce(Subquery(loan_principal_totals), Value(Decimal("0.00"))),
        total_interest_collected=Coalesce(Subquery(interest_totals), Value(Decimal("0.00"))),
        total_cash_received=Coalesce(Subquery(cash_received_totals), Value(Decimal("0.00"))),
        total_installment_paid=Coalesce(Subquery(installment_totals), Value(Decimal("0.00"))),
        savings_payment_count=Coalesce(Subquery(savings_payment_counts), Value(0)),
        loan_payment_count=Coalesce(Subquery(installment_payment_counts), Value(0)),
        latest_saving_paid_on=Subquery(latest_saving_paid_on),
        latest_installment_paid_on=Subquery(latest_installment_paid_on),
    )


def get_fund_totals():
    contribution_total = MonthlyContribution.objects.aggregate(
        total=Sum("amount_paid")
    )["total"] or Decimal("0.00")
    installment_total = Installment.objects.aggregate(
        total=Sum("amount_paid")
    )["total"] or Decimal("0.00")
    interest_collected_total = Loan.objects.aggregate(
        total=Sum("interest_amount")
    )["total"] or Decimal("0.00")
    interest_paid_out_total = MemberInterestPayout.objects.aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    net_disbursed_total = Loan.objects.aggregate(
        total=Sum("net_disbursed_amount")
    )["total"] or Decimal("0.00")
    adjustment_total = FundAdjustment.objects.aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")
    outstanding_installments_total = Installment.objects.aggregate(
        total=Coalesce(Sum("amount_due"), Value(Decimal("0.00")))
        - Coalesce(Sum("amount_paid"), Value(Decimal("0.00")))
    )["total"] or Decimal("0.00")
    available_cash_now = (
        contribution_total
        + installment_total
        + interest_collected_total
        - net_disbursed_total
        - interest_paid_out_total
        + adjustment_total
    )
    return {
        "contribution_total": contribution_total,
        "installment_total": installment_total,
        "interest_collected_total": interest_collected_total,
        "interest_paid_out_total": interest_paid_out_total,
        "net_disbursed_total": net_disbursed_total,
        "adjustment_total": adjustment_total,
        "outstanding_installments_total": outstanding_installments_total,
        "available_cash_now": available_cash_now,
        "total_cash": available_cash_now + outstanding_installments_total,
    }


def outstanding_due_total_subquery(month_start, month_end):
    return (
        Installment.objects.filter(
            loan__member=OuterRef("pk"),
            due_date__gte=month_start,
            due_date__lt=month_end,
        )
        .exclude(status=Installment.Status.PAID)
        .values("loan__member")
        .annotate(
            total=Sum(
                ExpressionWrapper(
                    F("amount_due") - F("amount_paid"),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
        )
        .values("total")[:1]
    )


def dashboard(request):
    refresh_open_loan_statuses()
    today = timezone.localdate()
    current_month = today.replace(day=1)
    next_month = today.replace(year=today.year + (today.month // 12), month=1 if today.month == 12 else today.month + 1, day=1)
    month_after_next = next_month.replace(
        year=next_month.year + (next_month.month // 12),
        month=1 if next_month.month == 12 else next_month.month + 1,
        day=1,
    )

    fund_totals = get_fund_totals()
    contribution_total = fund_totals["contribution_total"]
    installment_total = fund_totals["installment_total"]
    interest_collected_total = fund_totals["interest_collected_total"]
    interest_paid_out_total = fund_totals["interest_paid_out_total"]
    net_disbursed_total = fund_totals["net_disbursed_total"]
    contribution_paid_this_month = MonthlyContribution.objects.filter(
        paid_on__gte=current_month,
        paid_on__lt=next_month,
    ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0")
    installment_paid_this_month = Installment.objects.filter(
        paid_on__gte=current_month,
        paid_on__lt=next_month,
    ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0")
    interest_collected_this_month = Loan.objects.filter(
        issued_on__gte=current_month,
        issued_on__lt=next_month,
    ).aggregate(total=Sum("interest_amount"))["total"] or Decimal("0")
    cash_given_this_month = Loan.objects.filter(
        issued_on__gte=current_month,
        issued_on__lt=next_month,
    ).aggregate(total=Sum("net_disbursed_amount"))["total"] or Decimal("0")
    next_month_installment_total = Installment.objects.filter(
        due_date__gte=next_month,
        due_date__lt=month_after_next,
    ).exclude(status=Installment.Status.PAID).aggregate(
        total=Sum(
            ExpressionWrapper(
                F("amount_due") - F("amount_paid"),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            )
        )
    )["total"] or Decimal("0")
    next_month_savings_due_subquery = MonthlyContribution.objects.filter(
        member=OuterRef("pk"),
        month=next_month,
    ).values("amount_due")[:1]
    adjustment_total = fund_totals["adjustment_total"]
    adjustment_this_month = FundAdjustment.objects.filter(
        adjustment_date__gte=current_month,
        adjustment_date__lt=next_month,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    monthly_cash_in = (
        contribution_paid_this_month
        + installment_paid_this_month
        + interest_collected_this_month
        + adjustment_this_month
    )
    this_month_collected = contribution_paid_this_month + installment_paid_this_month
    available_cash_now = fund_totals["available_cash_now"]
    total_cash = fund_totals["total_cash"]
    base_member_upcoming_dues = Member.objects.filter(is_active=True).annotate(
        next_month_installment_total=Coalesce(
            Subquery(outstanding_due_total_subquery(next_month, month_after_next)),
            Value(Decimal("0.00")),
        ),
        savings_due=Coalesce(
            Subquery(next_month_savings_due_subquery),
            F("monthly_contribution_amount"),
        ),
    ).annotate(
        total_upcoming_due=Coalesce(
            Subquery(next_month_savings_due_subquery),
            F("monthly_contribution_amount"),
        ) + Coalesce(
            Subquery(outstanding_due_total_subquery(next_month, month_after_next)),
            Value(Decimal("0.00")),
        )
    ).order_by("full_name")
    due_search = request.GET.get("due_search", "").strip()
    member_upcoming_dues = base_member_upcoming_dues
    if due_search:
        member_upcoming_dues = member_upcoming_dues.filter(full_name__icontains=due_search)
    next_month_savings_total = sum((member.savings_due for member in base_member_upcoming_dues), Decimal("0.00"))
    next_month_total_cash = available_cash_now + next_month_savings_total + next_month_installment_total

    context = {
        "member_count": Member.objects.filter(is_active=True).count(),
        "active_loan_count": Loan.objects.filter(status=Loan.Status.ACTIVE).count(),
        "overdue_installment_count": Installment.objects.filter(
            due_date__lt=today
        ).filter(~Q(status=Installment.Status.PAID)).count(),
        "current_cash": available_cash_now,
        "available_cash_now": available_cash_now,
        "total_cash": total_cash,
        "interest_paid_out_total": interest_paid_out_total,
        "monthly_paid_total": MonthlyContribution.objects.filter(
            month=current_month
        ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0"),
        "monthly_due_total": Member.objects.filter(is_active=True).aggregate(
            total=Sum("monthly_contribution_amount")
        )["total"] or Decimal("0"),
        "interest_collected_total": interest_collected_total,
        "contribution_paid_this_month": contribution_paid_this_month,
        "installment_paid_this_month": installment_paid_this_month,
        "interest_collected_this_month": interest_collected_this_month,
        "cash_given_this_month": cash_given_this_month,
        "next_month_installment_total": next_month_installment_total,
        "next_month_savings_total": next_month_savings_total,
        "next_month_total_cash": next_month_total_cash,
        "this_month_collected": this_month_collected,
        "next_month": next_month,
        "adjustment_total": adjustment_total,
        "adjustment_this_month": adjustment_this_month,
        "monthly_cash_in": monthly_cash_in,
        "monthly_cash_left_after_loans": monthly_cash_in - cash_given_this_month,
        "total_principal_loaned": Loan.objects.aggregate(
            total=Sum("principal_amount")
        )["total"] or Decimal("0"),
        "this_month_cash_disbursed": cash_given_this_month,
        "total_cash_disbursed": net_disbursed_total,
        "recent_loans": Loan.objects.select_related("member").order_by("-issued_on")[:5],
        "recent_dues": Installment.objects.select_related("loan", "loan__member").filter(
            ~Q(status=Installment.Status.PAID)
        ).order_by("due_date")[:8],
        "member_upcoming_dues": member_upcoming_dues,
        "due_search": due_search,
        "member_payment_status": Member.objects.annotate(
            paid_count=Count(
                "contributions",
                filter=Q(contributions__month=current_month)
                & Q(contributions__status=MonthlyContribution.Status.PAID),
            )
        ).order_by("full_name"),
    }
    return render(request, "core/dashboard.html", context)


def editor_access(request):
    if request.method == "POST":
        password = request.POST.get("password", "")
        if password_matches(password):
            request.session[EDITOR_SESSION_KEY] = True
            messages.success(request, "Editor access enabled.")
            return redirect("dashboard")
        messages.error(request, "Incorrect admin password.")
    return render(request, "core/editor_access.html")


def editor_lock(request):
    if request.method == "POST":
        request.session.pop(EDITOR_SESSION_KEY, None)
        messages.success(request, "Editor access disabled.")
    return redirect("dashboard")


@editor_required
def member_create(request):
    form = MemberForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        member = form.save()
        messages.success(request, f"Added member {member.full_name}.")
        return redirect("member-detail", member_id=member.id)
    return render(
        request,
        "core/member_form.html",
        {"form": form, "page_title": "Add Member", "submit_label": "Save Member"},
    )


@editor_required
def member_edit(request, member_id):
    member = get_object_or_404(Member, pk=member_id)
    form = MemberForm(request.POST or None, instance=member)
    if request.method == "POST" and form.is_valid():
        member = form.save()
        messages.success(request, f"Updated member {member.full_name}.")
        return redirect("member-detail", member_id=member.id)
    return render(
        request,
        "core/member_form.html",
        {"form": form, "page_title": "Edit Member", "submit_label": "Save Member"},
    )


@editor_required
def contribution_create(request):
    return redirect("payment-create")


@editor_required
def contribution_edit(request, contribution_id):
    contribution = get_object_or_404(MonthlyContribution, pk=contribution_id)
    form = ContributionForm(request.POST or None, contribution=contribution)
    if request.method == "POST" and form.is_valid():
        contribution = form.save()
        messages.success(request, f"Updated contribution for {contribution.member.full_name}.")
        return redirect("member-detail", member_id=contribution.member_id)
    return render(
        request,
        "core/contribution_form.html",
        {"form": form, "page_title": "Edit Contribution", "submit_label": "Save Contribution"},
    )


@editor_required
def contribution_delete(request, contribution_id):
    contribution = get_object_or_404(MonthlyContribution.objects.select_related("member"), pk=contribution_id)
    member_id = contribution.member_id
    member_name = contribution.member.full_name
    if request.method == "POST":
        contribution.delete()
        messages.success(request, f"Deleted contribution for {member_name}.")
        return redirect("member-detail", member_id=member_id)
    return render(
        request,
        "core/confirm_delete.html",
        {
            "page_title": "Delete Contribution",
            "description": f"Delete contribution for {member_name} for {contribution.month:%b %Y}?",
            "cancel_url": f"/members/{member_id}/",
        },
    )


@editor_required
def loan_create(request):
    form = LoanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        loan = form.save()
        messages.success(request, f"Created loan for {loan.member.full_name}.")
        return redirect("loan-create")
    return render(request, "core/loan_form.html", {"form": form})


@editor_required
def loan_edit(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id)
    form = LoanForm(request.POST or None, loan=loan)
    if request.method == "POST" and form.is_valid():
        loan = form.save()
        messages.success(request, f"Updated loan for {loan.member.full_name}.")
        return redirect("member-detail", member_id=loan.member_id)
    return render(
        request,
        "core/loan_form.html",
        {"form": form, "page_title": "Edit Loan", "submit_label": "Save Loan"},
    )


@editor_required
def loan_delete(request, loan_id):
    loan = get_object_or_404(Loan.objects.select_related("member"), pk=loan_id)
    member_id = loan.member_id
    member_name = loan.member.full_name
    if request.method == "POST":
        loan.delete()
        messages.success(request, f"Deleted loan for {member_name}.")
        return redirect("member-detail", member_id=member_id)
    return render(
        request,
        "core/confirm_delete.html",
        {
            "page_title": "Delete Loan",
            "description": f"Delete loan for {member_name} issued on {loan.issued_on}?",
            "cancel_url": f"/members/{member_id}/",
        },
    )


@editor_required
def installment_payment_create(request):
    return redirect("payment-create")


@editor_required
def payment_create(request):
    upcoming_total = None
    payment_targets = None
    show_allocation = False
    initial = {}
    if request.method == "GET" and request.GET.get("member"):
        initial["member"] = request.GET.get("member")
    form = CombinedPaymentForm(initial=initial)
    if request.method == "GET" and initial.get("member"):
        try:
            member = Member.objects.get(pk=int(initial["member"]), is_active=True)
            seed_form = CombinedPaymentForm(initial={"member": member.pk})
            seed_form.cleaned_data = {"member": member}
            payment_targets = seed_form.get_payment_targets()
            upcoming_total = sum((item["remaining"] for item in payment_targets), Decimal("0.00"))
            form = CombinedPaymentForm(initial={"member": member.pk}, payment_targets=payment_targets)
        except (Member.DoesNotExist, ValueError, TypeError):
            pass
    if request.method == "POST":
        member = None
        try:
            member_id = int(request.POST.get("member", ""))
            member = Member.objects.get(pk=member_id, is_active=True)
        except (Member.DoesNotExist, ValueError, TypeError):
            member = None

        if member is not None:
            seed_form = CombinedPaymentForm(
                data={
                    "member": member.pk,
                    "amount_paid": request.POST.get("amount_paid"),
                    "paid_on": request.POST.get("paid_on"),
                    "notes": request.POST.get("notes", ""),
                    "allocation_target": request.POST.get("allocation_target", ""),
                }
            )
            seed_form.cleaned_data = {"member": member}
            payment_targets = seed_form.get_payment_targets()
            upcoming_total = sum((item["remaining"] for item in payment_targets), Decimal("0.00"))
            form = CombinedPaymentForm(request.POST, payment_targets=payment_targets)
            try:
                entered_amount = Decimal(request.POST.get("amount_paid", "0"))
            except Exception:
                entered_amount = Decimal("0.00")
            show_allocation = entered_amount > 0 and entered_amount < upcoming_total
        else:
            form = CombinedPaymentForm(request.POST)

        if form.is_valid():
            form.save()
            member_name = form.cleaned_data["member"].full_name
            messages.success(request, f"Saved payment for {member_name}.")
            return redirect("payment-create")

    next_month = CombinedPaymentForm.next_month_start()
    month_after_next = next_month.replace(
        year=next_month.year + (next_month.month // 12),
        month=1 if next_month.month == 12 else next_month.month + 1,
        day=1,
    )
    next_month_savings_due_subquery = MonthlyContribution.objects.filter(
        member=OuterRef("pk"),
        month=next_month,
    ).values("amount_due")[:1]
    upcoming_member_summaries = Member.objects.filter(is_active=True).annotate(
        next_month_installment_total=Coalesce(
            Subquery(outstanding_due_total_subquery(next_month, month_after_next)),
            Value(Decimal("0.00")),
        ),
        savings_due=Coalesce(
            Subquery(next_month_savings_due_subquery),
            F("monthly_contribution_amount"),
        ),
    ).annotate(
        total_upcoming_due=Coalesce(
            Subquery(next_month_savings_due_subquery),
            F("monthly_contribution_amount"),
        ) + Coalesce(
            Subquery(outstanding_due_total_subquery(next_month, month_after_next)),
            Value(Decimal("0.00")),
        )
    ).filter(
        total_upcoming_due__gt=0
    ).order_by("full_name")

    return render(
        request,
        "core/payment_form.html",
        {
            "form": form,
            "payment_targets": payment_targets,
            "upcoming_total": upcoming_total,
            "show_allocation": show_allocation,
            "upcoming_member_summaries": upcoming_member_summaries,
            "next_month": next_month,
            "page_title": "Record Payment",
            "submit_label": "Save Payment",
        },
    )


@editor_required
def installment_edit(request, installment_id):
    installment = get_object_or_404(
        Installment.objects.select_related("loan", "loan__member"),
        pk=installment_id,
    )
    form = InstallmentPaymentForm(request.POST or None, installment=installment)
    if request.method == "POST" and form.is_valid():
        installment = form.save()
        messages.success(request, f"Updated installment for {installment.loan.member.full_name}.")
        return redirect("member-detail", member_id=installment.loan.member_id)
    return render(
        request,
        "core/installment_payment_form.html",
        {
            "form": form,
            "page_title": "Edit Installment Payment",
            "submit_label": "Save Installment Payment",
        },
    )


@editor_required
def installment_delete(request, installment_id):
    installment = get_object_or_404(
        Installment.objects.select_related("loan", "loan__member"),
        pk=installment_id,
    )
    member_id = installment.loan.member_id
    member_name = installment.loan.member.full_name
    if request.method == "POST":
        loan = installment.loan
        installment.delete()
        loan.refresh_status()
        messages.success(request, f"Deleted installment for {member_name}.")
        return redirect("member-detail", member_id=member_id)
    return render(
        request,
        "core/confirm_delete.html",
        {
            "page_title": "Delete Installment",
            "description": f"Delete installment #{installment.installment_number} for {member_name} due on {installment.due_date}?",
            "cancel_url": f"/members/{member_id}/",
        },
    )


@editor_required
def member_remove(request, member_id):
    refresh_open_loan_statuses()
    member = get_object_or_404(Member, pk=member_id)
    fund_totals = get_fund_totals()
    active_member_count = Member.objects.filter(is_active=True).count()
    exit_pool_total = (
        fund_totals["available_cash_now"] + fund_totals["outstanding_installments_total"]
    )
    settlement_share = (
        (exit_pool_total / Decimal(active_member_count)).quantize(Decimal("0.01"))
        if active_member_count
        else Decimal("0.00")
    )
    form = MemberRemovalForm(
        request.POST or None,
        initial={
            "payout_amount": settlement_share,
            "payout_date": timezone.localdate(),
        },
    )

    if request.method == "POST" and form.is_valid():
        payout_amount = form.cleaned_data["payout_amount"]
        payout_date = form.cleaned_data["payout_date"]
        payout_notes = form.cleaned_data["notes"]
        if payout_amount > 0:
            FundAdjustment.objects.create(
                adjustment_date=payout_date,
                amount=-payout_amount,
                notes=(
                    f"Member removal payout for {member.full_name}. "
                    f"{payout_notes}".strip()
                ),
            )
        member.is_active = False
        if member.notes:
            member.notes += "\n"
        member.notes += (
            f"Removed from active members on {payout_date} with exit share {settlement_share} and payout {payout_amount}."
        )
        member.save(update_fields=["is_active", "notes"])
        messages.success(
            request,
            f"Marked {member.full_name} inactive. Payout recorded: ${payout_amount}.",
        )
        return redirect("member-detail", member_id=member.id)

    return render(
        request,
        "core/member_remove_confirm.html",
        {
            "member": member,
            "active_member_count": active_member_count,
            "available_cash_now": fund_totals["available_cash_now"],
            "outstanding_installments_total": fund_totals["outstanding_installments_total"],
            "exit_pool_total": exit_pool_total,
            "settlement_share": settlement_share,
            "form": form,
        },
    )


@editor_required
def interest_payout_all_create(request):
    form = InterestPayoutAllForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        amount = form.cleaned_data["amount"]
        payout_date = form.cleaned_data["payout_date"]
        notes = form.cleaned_data["notes"]
        payout_count = 0
        for member in Member.objects.filter(is_active=True).order_by("full_name"):
            MemberInterestPayout.objects.create(
                member=member,
                payout_date=payout_date,
                amount=amount,
                notes=notes or "Bulk payout to all active members.",
            )
            payout_count += 1
        messages.success(request, f"Recorded interest payout for {payout_count} active members.")
        return redirect("interest-payout-report")
    return render(
        request,
        "core/interest_payout_all_form.html",
        {"form": form, "page_title": "Give Interest To Everybody", "submit_label": "Save Interest Payout"},
    )


@editor_required
def skip_next_savings_installments(request):
    next_month = timezone.localdate().replace(day=1)
    next_month = next_month.replace(
        year=next_month.year + (next_month.month // 12),
        month=1 if next_month.month == 12 else next_month.month + 1,
        day=1,
    )
    active_members = list(Member.objects.filter(is_active=True).order_by("full_name"))
    if request.method == "POST":
        for member in active_members:
            MonthlyContribution.objects.update_or_create(
                member=member,
                month=next_month,
                defaults={
                    "amount_due": Decimal("0.00"),
                    "amount_paid": Decimal("0.00"),
                    "paid_on": timezone.localdate(),
                    "status": MonthlyContribution.Status.PAID,
                    "notes": "Upcoming savings installment skipped for all active members.",
                },
            )
        messages.success(request, f"Skipped next month savings installments for {len(active_members)} active members.")
        return redirect("dashboard")
    return render(
        request,
        "core/skip_savings_confirm.html",
        {
            "member_count": len(active_members),
            "next_month": next_month,
        },
    )


def member_report(request):
    next_month = CombinedPaymentForm.next_month_start()
    month_after_next = next_month.replace(
        year=next_month.year + (next_month.month // 12),
        month=1 if next_month.month == 12 else next_month.month + 1,
        day=1,
    )
    next_month_savings_due_subquery = MonthlyContribution.objects.filter(
        member=OuterRef("pk"),
        month=next_month,
    ).values("amount_due")[:1]
    members = member_with_totals_queryset().annotate(
        member_balance=F("total_principal_loaned") - F("total_installment_paid") - F("total_contributed")
    ).annotate(
        outstanding_principal=F("total_principal_loaned") - F("total_installment_paid"),
        next_month_installment_total=Coalesce(
            Subquery(outstanding_due_total_subquery(next_month, month_after_next)),
            Value(Decimal("0.00")),
        ),
        savings_due=Coalesce(
            Subquery(next_month_savings_due_subquery),
            F("monthly_contribution_amount"),
        ),
    ).order_by("full_name")
    return render(request, "core/member_report.html", {"members": members, "next_month": next_month})


def member_detail(request, member_id):
    refresh_open_loan_statuses()
    member = get_object_or_404(member_with_totals_queryset(), pk=member_id)
    contributions = member.contributions.order_by("-month", "-id")
    loans = member.loans.prefetch_related("installments").order_by("-issued_on", "-id")
    installments = Installment.objects.filter(loan__member=member).select_related("loan").order_by("-due_date", "-id")

    context = {
        "member": member,
        "contributions": contributions,
        "loans": loans,
        "installments": installments,
        "outstanding_principal": member.total_principal_loaned - member.total_installment_paid,
    }
    return render(request, "core/member_detail.html", context)


def monthly_summary_report(request):
    refresh_open_loan_statuses()
    monthly_rows = {}

    for contribution in MonthlyContribution.objects.exclude(paid_on__isnull=True).order_by("paid_on", "id"):
        key = month_key(contribution.paid_on)
        row = monthly_rows.setdefault(
            key,
            {
                "month": contribution.paid_on.replace(day=1),
                "contributions_received": Decimal("0.00"),
                "loans_issued_principal": Decimal("0.00"),
                "interest_collected": Decimal("0.00"),
                "cash_given": Decimal("0.00"),
                "installments_received": Decimal("0.00"),
            },
        )
        row["contributions_received"] += contribution.amount_paid

    for loan in Loan.objects.order_by("issued_on", "id"):
        key = month_key(loan.issued_on)
        row = monthly_rows.setdefault(
            key,
            {
                "month": loan.issued_on.replace(day=1),
                "contributions_received": Decimal("0.00"),
                "loans_issued_principal": Decimal("0.00"),
                "interest_collected": Decimal("0.00"),
                "cash_given": Decimal("0.00"),
                "installments_received": Decimal("0.00"),
            },
        )
        row["loans_issued_principal"] += loan.principal_amount
        row["interest_collected"] += loan.interest_amount
        row["cash_given"] += loan.net_disbursed_amount

    for installment in Installment.objects.exclude(paid_on__isnull=True).order_by("paid_on", "id"):
        key = month_key(installment.paid_on)
        row = monthly_rows.setdefault(
            key,
            {
                "month": installment.paid_on.replace(day=1),
                "contributions_received": Decimal("0.00"),
                "loans_issued_principal": Decimal("0.00"),
                "interest_collected": Decimal("0.00"),
                "cash_given": Decimal("0.00"),
                "installments_received": Decimal("0.00"),
            },
        )
        row["installments_received"] += installment.amount_paid

    for adjustment in FundAdjustment.objects.order_by("adjustment_date", "id"):
        key = month_key(adjustment.adjustment_date)
        row = monthly_rows.setdefault(
            key,
            {
                "month": adjustment.adjustment_date.replace(day=1),
                "contributions_received": Decimal("0.00"),
                "loans_issued_principal": Decimal("0.00"),
                "interest_collected": Decimal("0.00"),
                "cash_given": Decimal("0.00"),
                "installments_received": Decimal("0.00"),
                "adjustments": Decimal("0.00"),
            },
        )
        row["adjustments"] = row.get("adjustments", Decimal("0.00")) + adjustment.amount

    rows = []
    running_cash = Decimal("0.00")
    for key in sorted(monthly_rows):
        row = monthly_rows[key]
        row["adjustments"] = row.get("adjustments", Decimal("0.00"))
        row["total_cash_in"] = (
            row["contributions_received"]
            + row["interest_collected"]
            + row["installments_received"]
            + row["adjustments"]
        )
        row["net_change"] = row["total_cash_in"] - row["cash_given"]
        running_cash += row["net_change"]
        row["ending_cash"] = running_cash
        row["label"] = month_label(row["month"])
        rows.append(row)

    month_options = [row["month"] for row in rows]
    selected_month = request.GET.get("month", "").strip()
    if selected_month:
        rows = [row for row in rows if row["month"].strftime("%Y-%m") == selected_month]
    return render(
        request,
        "core/monthly_summary_report.html",
        {
            "rows": rows,
            "month_options": month_options,
            "selected_month": selected_month,
        },
    )


def active_loans_report(request):
    refresh_open_loan_statuses()
    next_due_installments = Installment.objects.filter(
        loan=OuterRef("pk")
    ).exclude(status=Installment.Status.PAID).order_by("due_date", "installment_number")
    last_installment_dates = Installment.objects.filter(
        loan=OuterRef("pk")
    ).order_by("-due_date").values("due_date")[:1]
    loans = Loan.objects.filter(
        status__in=[Loan.Status.ACTIVE, Loan.Status.OVERDUE]
    ).select_related("member").annotate(
        total_installments_paid=Coalesce(Sum("installments__amount_paid"), Value(Decimal("0.00"))),
        remaining_principal=Coalesce(
            Sum("installments__amount_due"),
            Value(Decimal("0.00")),
        ) - Coalesce(Sum("installments__amount_paid"), Value(Decimal("0.00"))),
        next_due_date=Subquery(next_due_installments.values("due_date")[:1]),
        next_due_amount=Subquery(next_due_installments.values("amount_due")[:1]),
        next_due_installment_number=Subquery(next_due_installments.values("installment_number")[:1]),
        next_due_status=Subquery(next_due_installments.values("status")[:1]),
        end_date=Subquery(last_installment_dates),
    ).order_by("next_due_date", "member__full_name", "-issued_on")
    return render(request, "core/active_loans_report.html", {"loans": loans})


def loan_disbursement_report(request):
    loans = Loan.objects.select_related("member").order_by("-issued_on", "-id")
    return render(request, "core/loan_disbursement_report.html", {"loans": loans})


def interest_payout_report(request):
    payouts = MemberInterestPayout.objects.select_related("member").order_by("-payout_date", "member__full_name", "-id")
    return render(request, "core/interest_payout_report.html", {"payouts": payouts})


def overdue_report(request):
    refresh_open_loan_statuses()
    installments = Installment.objects.select_related("loan", "loan__member").filter(
        due_date__lt=timezone.localdate()
    ).filter(~Q(status=Installment.Status.PAID)).order_by("due_date")
    return render(request, "core/overdue_report.html", {"installments": installments})
