from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import TimestampedModel


class AssessmentRespondentType(models.TextChoices):
    ORGANIZATION = "organization", "Organization"
    INDIVIDUAL = "individual", "Individual"
    ANY = "any", "Any"


class AssessmentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    LIVE = "live", "Live"
    ARCHIVED = "archived", "Archived"


class Assessment(TimestampedModel):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    category = models.ForeignKey(
        "maturity_assessment.Category",
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    name = models.TextField()
    version_label = models.TextField(default="v1")
    description = models.TextField(blank=True)
    respondent_type = models.CharField(
        max_length=16,
        choices=AssessmentRespondentType.choices,
        default=AssessmentRespondentType.ORGANIZATION,
    )
    status = models.CharField(
        max_length=16,
        choices=AssessmentStatus.choices,
        default=AssessmentStatus.DRAFT,
    )
    gap_threshold_pct = models.DecimalField(max_digits=5, decimal_places=2, default=55)
    auto_share_reports = models.BooleanField(null=True, blank=True)
    default_target_score = models.DecimalField(max_digits=5, decimal_places=2, default=75)
    cloned_from_assessment = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clones",
    )
    current_version = models.ForeignKey(
        "maturity_assessment.AssessmentVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_assessments",
    )

    class Meta:
        db_table = "assessments"
        constraints = [
            models.UniqueConstraint(fields=["id", "organization"], name="assessments_id_org_uniq"),
            models.CheckConstraint(
                condition=models.Q(respondent_type__in=AssessmentRespondentType.values),
                name="assessments_respondent_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=AssessmentStatus.values),
                name="assessments_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(gap_threshold_pct__gte=0, gap_threshold_pct__lte=100),
                name="assessments_gap_threshold_range",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="ix_assessments_org_status"),
        ]

    def clean(self):
        if self.category_id and self.category.organization_id != self.organization_id:
            raise ValidationError("Category must belong to the same organization.")

    def __str__(self):
        return f"{self.name} ({self.version_label})"
