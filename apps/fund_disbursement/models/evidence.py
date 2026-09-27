from django.conf import settings
from django.db import models

from apps.core.models.base import UUIDPrimaryKey


class EvidenceSubmissionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    INFO_REQUESTED = "info_requested", "Info requested"


class ReviewDecisionType(models.TextChoices):
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    INFO_REQUESTED = "info_requested", "Info requested"


class EvidenceRequirementType(UUIDPrimaryKey):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evidence_requirement_types",
    )
    label = models.TextField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "evidence_requirement_types"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "label"],
                name="evidence_requirement_types_org_label_uniq",
            ),
        ]

    def __str__(self):
        return self.label


class MilestoneEvidenceRequirement(UUIDPrimaryKey):
    milestone = models.ForeignKey(
        "fund_disbursement.Milestone",
        on_delete=models.CASCADE,
        related_name="evidence_requirements",
    )
    requirement_type = models.ForeignKey(
        EvidenceRequirementType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="milestone_requirements",
    )
    label = models.TextField()
    is_mandatory = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        db_table = "milestone_evidence_requirements"
        indexes = [models.Index(fields=["milestone"], name="ix_evidence_reqs_milestone")]

    def __str__(self):
        return self.label


class EvidenceSubmission(UUIDPrimaryKey):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="evidence_submissions",
    )
    installment = models.ForeignKey(
        "fund_disbursement.Installment",
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    milestone = models.ForeignKey(
        "fund_disbursement.Milestone",
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    attempt_no = models.IntegerField(default=1)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evidence_submissions",
    )
    respondent_note = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=EvidenceSubmissionStatus.choices,
        default=EvidenceSubmissionStatus.SUBMITTED,
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "evidence_submissions"
        constraints = [
            models.UniqueConstraint(
                fields=["installment", "attempt_no"],
                name="evidence_submissions_installment_attempt_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=EvidenceSubmissionStatus.values),
                name="evidence_submissions_status_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status", "submitted_at"],
                name="ix_submissions_queue",
            ),
        ]

    def __str__(self):
        return f"Submission {self.attempt_no} · {self.status}"


class EvidenceFile(UUIDPrimaryKey):
    submission = models.ForeignKey(
        EvidenceSubmission,
        on_delete=models.CASCADE,
        related_name="files",
    )
    file = models.ForeignKey(
        "core.File",
        on_delete=models.PROTECT,
        related_name="evidence_files",
    )
    requirement = models.ForeignKey(
        MilestoneEvidenceRequirement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files",
    )
    external_url = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "evidence_files"
        indexes = [models.Index(fields=["submission"], name="ix_evidence_files_submission")]

    def __str__(self):
        return str(self.file_id)


class KPIResult(UUIDPrimaryKey):
    submission = models.ForeignKey(
        EvidenceSubmission,
        on_delete=models.CASCADE,
        related_name="kpi_results",
    )
    milestone_kpi = models.ForeignKey(
        "fund_disbursement.MilestoneKPI",
        on_delete=models.CASCADE,
        related_name="results",
    )
    reported_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    reported_text = models.TextField(blank=True)
    meets_target = models.BooleanField(null=True, blank=True)
    reviewer_note = models.TextField(blank=True)

    class Meta:
        db_table = "kpi_results"
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "milestone_kpi"],
                name="kpi_results_submission_kpi_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.milestone_kpi_id} · {self.reported_value}"


class ReviewDecision(UUIDPrimaryKey):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="review_decisions",
    )
    submission = models.ForeignKey(
        EvidenceSubmission,
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    installment = models.ForeignKey(
        "fund_disbursement.Installment",
        on_delete=models.CASCADE,
        related_name="review_decisions",
    )
    reviewer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="review_decisions",
    )
    reviewer_name = models.TextField()
    decision = models.CharField(max_length=16, choices=ReviewDecisionType.choices)
    comment = models.TextField(blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "review_decisions"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(decision__in=ReviewDecisionType.values),
                name="review_decisions_decision_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["installment", "-decided_at"], name="ix_decisions_installment"),
            models.Index(fields=["reviewer_user", "-decided_at"], name="ix_decisions_reviewer"),
        ]

    def __str__(self):
        return f"{self.decision} · {self.reviewer_name}"
