from django.contrib import admin

from apps.fund_disbursement.models import (
    DisbursementRecord,
    EvidenceFile,
    EvidenceRequirementType,
    EvidenceSubmission,
    Fund,
    Installment,
    KPIResult,
    LoanRepayment,
    Milestone,
    MilestoneEvidenceRequirement,
    MilestoneKPI,
    ReviewDecision,
)


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = (
        "agreement_reference",
        "recipient",
        "total_amount",
        "currency",
        "lifecycle_status",
        "health_status",
    )
    list_filter = ("funding_type", "lifecycle_status", "health_status")
    search_fields = ("agreement_reference", "title")


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("title", "fund", "sequence_position", "status", "due_date")
    list_filter = ("status",)


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ("installment_no", "fund", "amount", "currency", "status")
    list_filter = ("status",)


@admin.register(MilestoneKPI)
class MilestoneKPIAdmin(admin.ModelAdmin):
    list_display = ("name", "milestone", "metric_type", "comparator", "target_value")


@admin.register(EvidenceRequirementType)
class EvidenceRequirementTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "organization", "is_active")
    list_filter = ("is_active",)


@admin.register(MilestoneEvidenceRequirement)
class MilestoneEvidenceRequirementAdmin(admin.ModelAdmin):
    list_display = ("label", "milestone", "is_mandatory")


@admin.register(EvidenceSubmission)
class EvidenceSubmissionAdmin(admin.ModelAdmin):
    list_display = ("installment", "attempt_no", "status", "submitted_at")
    list_filter = ("status",)


@admin.register(EvidenceFile)
class EvidenceFileAdmin(admin.ModelAdmin):
    list_display = ("submission", "file", "uploaded_at")


@admin.register(KPIResult)
class KPIResultAdmin(admin.ModelAdmin):
    list_display = ("milestone_kpi", "submission", "reported_value", "meets_target")


@admin.register(ReviewDecision)
class ReviewDecisionAdmin(admin.ModelAdmin):
    list_display = ("decision", "reviewer_name", "installment", "decided_at")
    list_filter = ("decision",)
    readonly_fields = [field.name for field in ReviewDecision._meta.fields]


@admin.register(DisbursementRecord)
class DisbursementRecordAdmin(admin.ModelAdmin):
    list_display = ("payment_reference", "installment", "amount_paid", "currency", "paid_at")


@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = ("fund", "due_date", "amount_due", "amount_paid", "status")
    list_filter = ("status",)
