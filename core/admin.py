from django.contrib import admin

from .models import Installment, Loan, Member, MonthlyContribution


class MonthlyContributionInline(admin.TabularInline):
    model = MonthlyContribution
    extra = 0


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "monthly_contribution_amount", "is_active")
    search_fields = ("full_name", "phone", "email")
    list_filter = ("is_active",)
    inlines = [MonthlyContributionInline]


@admin.register(MonthlyContribution)
class MonthlyContributionAdmin(admin.ModelAdmin):
    list_display = ("member", "month", "amount_due", "amount_paid", "status", "paid_on")
    list_filter = ("status", "month")
    search_fields = ("member__full_name",)
    date_hierarchy = "month"


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "principal_amount",
        "interest_amount",
        "net_disbursed_amount",
        "issued_on",
        "installment_count",
        "installment_amount",
        "status",
    )
    list_filter = ("status", "issued_on")
    search_fields = ("member__full_name",)
    inlines = [InstallmentInline]


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = (
        "loan",
        "installment_number",
        "due_date",
        "amount_due",
        "amount_paid",
        "status",
    )
    list_filter = ("status", "due_date")
    search_fields = ("loan__member__full_name",)
