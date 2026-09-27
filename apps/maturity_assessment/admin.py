from django.contrib import admin

from apps.maturity_assessment.models import (
    Assessment,
    AssessmentInvitation,
    AssessmentVersion,
    Capability,
    Category,
    MaturityBand,
    Question,
    QuestionNumericRule,
    QuestionOption,
    Recommendation,
    Report,
    ReportGap,
    Response,
    ResponseSelectedOption,
    ScoreResult,
    SubCapability,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_archived")
    list_filter = ("is_archived",)
    search_fields = ("name",)


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "status", "version_label", "organization")
    list_filter = ("status", "respondent_type")
    search_fields = ("name",)


@admin.register(Capability)
class CapabilityAdmin(admin.ModelAdmin):
    list_display = ("name", "assessment", "weight_pct", "display_order", "is_archived")
    list_filter = ("is_archived",)


@admin.register(SubCapability)
class SubCapabilityAdmin(admin.ModelAdmin):
    list_display = ("name", "capability", "display_order", "is_archived")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("question_text", "assessment", "question_type", "is_scored", "page_no")
    list_filter = ("question_type", "is_scored", "is_archived")
    search_fields = ("question_text",)


@admin.register(QuestionOption)
class QuestionOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "question", "score_value", "display_order")


@admin.register(QuestionNumericRule)
class QuestionNumericRuleAdmin(admin.ModelAdmin):
    list_display = ("question", "min_value", "max_value", "score_value")


@admin.register(MaturityBand)
class MaturityBandAdmin(admin.ModelAdmin):
    list_display = ("label", "assessment", "min_score", "max_score")


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("capability", "band", "assessment")


@admin.register(AssessmentVersion)
class AssessmentVersionAdmin(admin.ModelAdmin):
    list_display = ("assessment", "version_no", "published_at")


@admin.register(AssessmentInvitation)
class AssessmentInvitationAdmin(admin.ModelAdmin):
    list_display = ("respondent", "assessment", "status", "due_date")
    list_filter = ("status",)


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("invitation", "question", "is_not_applicable", "answered_at")


@admin.register(ResponseSelectedOption)
class ResponseSelectedOptionAdmin(admin.ModelAdmin):
    list_display = ("response", "question_option")


@admin.register(ScoreResult)
class ScoreResultAdmin(admin.ModelAdmin):
    list_display = ("invitation", "capability", "score_10", "is_gap")
    list_filter = ("is_gap",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("respondent", "overall_score", "maturity_band_label", "share_status")
    list_filter = ("share_status",)


@admin.register(ReportGap)
class ReportGapAdmin(admin.ModelAdmin):
    list_display = ("report", "capability_name", "score_pct")
