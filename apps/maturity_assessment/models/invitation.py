from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import CreatedAtModel, UUIDPrimaryKey


class InvitationStatus(models.TextChoices):
    INVITED = "invited", "Invited"
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class AssessmentInvitation(CreatedAtModel):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="assessment_invitations",
    )
    assessment = models.ForeignKey(
        "maturity_assessment.Assessment",
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    assessment_version = models.ForeignKey(
        "maturity_assessment.AssessmentVersion",
        on_delete=models.PROTECT,
        related_name="invitations",
    )
    respondent = models.ForeignKey(
        "core.Respondent",
        on_delete=models.CASCADE,
        related_name="assessment_invitations",
    )
    access_token = models.TextField(unique=True)
    status = models.CharField(
        max_length=16,
        choices=InvitationStatus.choices,
        default=InvitationStatus.INVITED,
    )
    due_date = models.DateField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_assessment_invitations",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    reminder_count = models.IntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "assessment_invitations"
        constraints = [
            models.UniqueConstraint(
                fields=["id", "organization"],
                name="assessment_invitations_id_org_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=InvitationStatus.values),
                name="assessment_invitations_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="ix_invitations_org_status"),
            models.Index(fields=["respondent"], name="ix_invitations_respondent"),
        ]

    def clean(self):
        if self.assessment_id and self.assessment.organization_id != self.organization_id:
            raise ValidationError("Assessment must belong to the same organization.")
        if self.respondent_id and self.respondent.organization_id != self.organization_id:
            raise ValidationError("Respondent must belong to the same organization.")

    def __str__(self):
        return f"{self.respondent_id} · {self.assessment_id} · {self.status}"


class Response(UUIDPrimaryKey):
    invitation = models.ForeignKey(
        AssessmentInvitation,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    question = models.ForeignKey(
        "maturity_assessment.Question",
        on_delete=models.PROTECT,
        related_name="responses",
    )
    answer_value = models.JSONField(null=True, blank=True)
    is_not_applicable = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now=True)

    # Manual grading for scored free-text answers: auto-scored question types
    # (yes_no, select, likert, numeric) are computed from answer_value/options
    # and never touch these fields. A scored free-text question instead sits
    # "pending review" (reviewer_score is null) until a reviewer reads the
    # answer and assigns points — see Question.is_scored + QuestionType.FREE_TEXT.
    reviewer_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_responses",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "responses"
        constraints = [
            models.UniqueConstraint(
                fields=["invitation", "question"],
                name="responses_invitation_question_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["invitation"], name="ix_responses_invitation"),
            models.Index(
                fields=["question"],
                name="ix_responses_pending_review",
                condition=models.Q(reviewer_score__isnull=True),
            ),
        ]

    @property
    def needs_review(self):
        return self.question.is_scored and self.question.question_type == "free_text" and self.reviewer_score is None

    def __str__(self):
        return f"{self.invitation_id} · {self.question_id}"


class ResponseSelectedOption(models.Model):
    response = models.ForeignKey(
        Response,
        on_delete=models.CASCADE,
        related_name="selected_options",
    )
    question_option = models.ForeignKey(
        "maturity_assessment.QuestionOption",
        on_delete=models.PROTECT,
        related_name="response_selections",
    )

    class Meta:
        db_table = "response_selected_options"
        constraints = [
            models.UniqueConstraint(
                fields=["response", "question_option"],
                name="response_selected_options_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.response_id} · {self.question_option_id}"


class ScoreResult(UUIDPrimaryKey):
    invitation = models.ForeignKey(
        AssessmentInvitation,
        on_delete=models.CASCADE,
        related_name="score_results",
    )
    capability = models.ForeignKey(
        "maturity_assessment.Capability",
        on_delete=models.CASCADE,
        related_name="score_results",
    )
    sub_capability = models.ForeignKey(
        "maturity_assessment.SubCapability",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="score_results",
    )
    questions_scored = models.IntegerField(default=0)
    raw_points = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_points = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    score_10 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    score_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weighted_points = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    target_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_gap = models.BooleanField(default=False)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "score_results"
        constraints = [
            models.UniqueConstraint(
                fields=["invitation", "capability", "sub_capability"],
                name="score_results_invitation_cap_sub_uniq",
                condition=models.Q(sub_capability__isnull=False),
            ),
            models.UniqueConstraint(
                fields=["invitation", "capability"],
                name="score_results_invitation_cap_rollup_uniq",
                condition=models.Q(sub_capability__isnull=True),
            ),
        ]
        indexes = [models.Index(fields=["invitation"], name="ix_score_results_invitation")]

    def __str__(self):
        return f"{self.invitation_id} · {self.capability_id}"
