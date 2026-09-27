from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import TimestampedModel


class FundingType(models.TextChoices):
    GRANT = "grant", "Grant"
    LOAN = "loan", "Loan"
    EQUITY_LINKED = "equity_linked", "Equity-linked"
    OTHER = "other", "Other"


class Sequencing(models.TextChoices):
    SEQUENTIAL = "sequential", "Sequential"
    PARALLEL = "parallel", "Parallel"


class FundLifecycleStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    SUSPENDED = "suspended", "Suspended"


class FundHealthStatus(models.TextChoices):
    ON_TRACK = "on_track", "On track"
    AT_RISK = "at_risk", "At risk"
    DELAYED = "delayed", "Delayed"
    COMPLETED = "completed", "Completed"


class Fund(TimestampedModel):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="funds",
    )
    recipient = models.ForeignKey(
        "core.Respondent",
        on_delete=models.PROTECT,
        related_name="funds",
    )
    agreement_reference = models.TextField(null=True, blank=True)
    title = models.TextField(blank=True)
    funding_type = models.CharField(
        max_length=16,
        choices=FundingType.choices,
        default=FundingType.GRANT,
    )
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    sequencing = models.CharField(
        max_length=16,
        choices=Sequencing.choices,
        default=Sequencing.SEQUENTIAL,
    )
    lifecycle_status = models.CharField(
        max_length=16,
        choices=FundLifecycleStatus.choices,
        default=FundLifecycleStatus.DRAFT,
    )
    health_status = models.CharField(
        max_length=16,
        choices=FundHealthStatus.choices,
        default=FundHealthStatus.ON_TRACK,
    )
    linked_report = models.ForeignKey(
        "maturity_assessment.Report",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="linked_funds",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_funds",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "funds"
        constraints = [
            models.UniqueConstraint(fields=["id", "organization"], name="funds_id_org_uniq"),
            models.UniqueConstraint(
                fields=["organization", "agreement_reference"],
                name="funds_org_agreement_uniq",
            ),
            models.CheckConstraint(condition=models.Q(total_amount__gt=0), name="funds_total_amount_positive"),
            models.CheckConstraint(
                condition=models.Q(funding_type__in=FundingType.values),
                name="funds_funding_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(sequencing__in=Sequencing.values),
                name="funds_sequencing_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(lifecycle_status__in=FundLifecycleStatus.values),
                name="funds_lifecycle_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(health_status__in=FundHealthStatus.values),
                name="funds_health_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "lifecycle_status"], name="ix_funds_org_status"),
            models.Index(fields=["recipient"], name="ix_funds_recipient"),
        ]

    def clean(self):
        if self.recipient_id and self.recipient.organization_id != self.organization_id:
            raise ValidationError("Recipient must belong to the same organization.")

    def __str__(self):
        return self.agreement_reference or self.title or str(self.id)
