from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import TimestampedModel, UUIDPrimaryKey


class MilestoneStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    LOCKED = "locked", "Locked"
    OPEN = "open", "Open"
    EVIDENCE_SUBMITTED = "evidence_submitted", "Evidence submitted"
    UNDER_REVIEW = "under_review", "Under review"
    INFO_REQUESTED = "info_requested", "Info requested"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class InstallmentStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    AWAITING_EVIDENCE = "awaiting_evidence", "Awaiting evidence"
    UNDER_REVIEW = "under_review", "Under review"
    INFO_REQUESTED = "info_requested", "Info requested"
    APPROVED = "approved", "Approved"
    READY_FOR_DISBURSEMENT = "ready_for_disbursement", "Ready for disbursement"
    DISBURSED = "disbursed", "Disbursed"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class MetricType(models.TextChoices):
    NUMBER = "number", "Number"
    PERCENTAGE = "percentage", "Percentage"
    CURRENCY = "currency", "Currency"
    BOOLEAN = "boolean", "Boolean"
    DATE = "date", "Date"
    TEXT = "text", "Text"


class Comparator(models.TextChoices):
    GTE = "gte", "Greater than or equal"
    LTE = "lte", "Less than or equal"
    EQ = "eq", "Equal"
    GT = "gt", "Greater than"
    LT = "lt", "Less than"
    BETWEEN = "between", "Between"


class Milestone(TimestampedModel):
    fund = models.ForeignKey(
        "fund_disbursement.Fund",
        on_delete=models.CASCADE,
        related_name="milestones",
    )
    sequence_position = models.IntegerField()
    title = models.TextField()
    deliverable_description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    unlocks_after_milestone = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unlocks",
    )
    status = models.CharField(
        max_length=32,
        choices=MilestoneStatus.choices,
        default=MilestoneStatus.NOT_STARTED,
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "milestones"
        constraints = [
            models.UniqueConstraint(fields=["fund", "sequence_position"], name="milestones_fund_sequence_uniq"),
            models.UniqueConstraint(fields=["id", "fund"], name="milestones_id_fund_uniq"),
            models.CheckConstraint(
                condition=models.Q(sequence_position__gt=0),
                name="milestones_sequence_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=MilestoneStatus.values),
                name="milestones_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["fund", "sequence_position"], name="ix_milestones_fund"),
            models.Index(
                fields=["due_date"],
                name="ix_milestones_due",
                condition=~models.Q(status__in=["completed", "cancelled"]),
            ),
        ]

    def clean(self):
        if (
            self.unlocks_after_milestone_id
            and self.unlocks_after_milestone.fund_id != self.fund_id
        ):
            raise ValidationError("Unlock predecessor must belong to the same fund.")

    def __str__(self):
        return f"{self.sequence_position}. {self.title}"


class Installment(TimestampedModel):
    fund = models.ForeignKey(
        "fund_disbursement.Fund",
        on_delete=models.CASCADE,
        related_name="installments",
    )
    milestone = models.OneToOneField(
        Milestone,
        on_delete=models.CASCADE,
        related_name="installment",
    )
    installment_no = models.IntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=32,
        choices=InstallmentStatus.choices,
        default=InstallmentStatus.NOT_STARTED,
    )
    unlocked_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_installments",
    )
    disbursed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "installments"
        constraints = [
            models.UniqueConstraint(fields=["fund", "installment_no"], name="installments_fund_no_uniq"),
            models.CheckConstraint(
                condition=models.Q(installment_no__gt=0),
                name="installments_no_positive",
            ),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="installments_amount_positive"),
            models.CheckConstraint(
                condition=models.Q(status__in=InstallmentStatus.values),
                name="installments_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["fund", "installment_no"], name="ix_installments_fund"),
            models.Index(
                fields=["status"],
                name="ix_installments_review_queue",
                condition=models.Q(status__in=["under_review", "awaiting_evidence"]),
            ),
        ]

    def clean(self):
        if self.milestone_id and self.milestone.fund_id != self.fund_id:
            raise ValidationError("Milestone must belong to the same fund.")

    def __str__(self):
        return f"Installment {self.installment_no}"


class MilestoneKPI(UUIDPrimaryKey):
    milestone = models.ForeignKey(
        Milestone,
        on_delete=models.CASCADE,
        related_name="kpis",
    )
    name = models.TextField()
    metric_type = models.CharField(
        max_length=16,
        choices=MetricType.choices,
        default=MetricType.NUMBER,
    )
    comparator = models.CharField(
        max_length=16,
        choices=Comparator.choices,
        default=Comparator.GTE,
    )
    target_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    target_value_max = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    target_text = models.TextField(blank=True)
    unit = models.TextField(blank=True)
    display_order = models.IntegerField(default=0)

    class Meta:
        db_table = "milestone_kpis"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(metric_type__in=MetricType.values),
                name="milestone_kpis_metric_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(comparator__in=Comparator.values),
                name="milestone_kpis_comparator_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(comparator=Comparator.BETWEEN)
                | models.Q(target_value_max__isnull=False),
                name="milestone_kpis_between_requires_max",
            ),
        ]
        indexes = [models.Index(fields=["milestone", "display_order"], name="ix_kpis_milestone")]

    def __str__(self):
        return self.name
