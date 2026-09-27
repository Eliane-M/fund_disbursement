from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import UUIDPrimaryKey


class ReportShareStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SHARED = "shared", "Shared"
    WITHHELD = "withheld", "Withheld"


class Report(UUIDPrimaryKey):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    invitation = models.OneToOneField(
        "maturity_assessment.AssessmentInvitation",
        on_delete=models.CASCADE,
        related_name="report",
    )
    respondent = models.ForeignKey(
        "core.Respondent",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    assessment_version = models.ForeignKey(
        "maturity_assessment.AssessmentVersion",
        on_delete=models.PROTECT,
        related_name="reports",
    )
    overall_score = models.DecimalField(max_digits=5, decimal_places=2)
    maturity_band = models.ForeignKey(
        "maturity_assessment.MaturityBand",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
    )
    maturity_band_label = models.TextField(blank=True)
    share_status = models.CharField(
        max_length=16,
        choices=ReportShareStatus.choices,
        default=ReportShareStatus.DRAFT,
    )
    share_token = models.TextField(unique=True, null=True, blank=True)
    shared_at = models.DateTimeField(null=True, blank=True)
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shared_reports",
    )
    first_viewed_at = models.DateTimeField(null=True, blank=True)
    pdf_file = models.ForeignKey(
        "core.File",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_pdfs",
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reports"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(overall_score__gte=0, overall_score__lte=100),
                name="reports_overall_score_range",
            ),
            models.CheckConstraint(
                condition=models.Q(share_status__in=ReportShareStatus.values),
                name="reports_share_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "-generated_at"], name="ix_reports_org"),
            models.Index(fields=["respondent"], name="ix_reports_respondent"),
        ]

    def clean(self):
        if self.respondent_id and self.respondent.organization_id != self.organization_id:
            raise ValidationError("Respondent must belong to the same organization.")

    def __str__(self):
        return f"Report {self.overall_score} · {self.maturity_band_label}"


class ReportGap(UUIDPrimaryKey):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="gaps")
    capability = models.ForeignKey(
        "maturity_assessment.Capability",
        on_delete=models.CASCADE,
        related_name="report_gaps",
    )
    capability_name = models.TextField()
    score_pct = models.DecimalField(max_digits=5, decimal_places=2)
    recommendation_text = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        db_table = "report_gaps"
        indexes = [models.Index(fields=["report"], name="ix_report_gaps_report")]

    def __str__(self):
        return f"{self.capability_name} · {self.score_pct}"
