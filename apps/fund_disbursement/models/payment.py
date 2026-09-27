from django.conf import settings
from django.db import models

from apps.core.models.base import CreatedAtModel, UUIDPrimaryKey


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    CHEQUE = "cheque", "Cheque"
    CASH = "cash", "Cash"
    OTHER = "other", "Other"


class LoanRepaymentStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    PARTIAL = "partial", "Partial"
    PAID = "paid", "Paid"
    OVERDUE = "overdue", "Overdue"
    WAIVED = "waived", "Waived"


class DisbursementRecord(CreatedAtModel):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="disbursement_records",
    )
    installment = models.ForeignKey(
        "fund_disbursement.Installment",
        on_delete=models.PROTECT,
        related_name="disbursement_records",
    )
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    fx_rate_to_fund_ccy = models.DecimalField(max_digits=14, decimal_places=6, null=True, blank=True)
    payment_reference = models.TextField(blank=True)
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
        blank=True,
    )
    paid_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_disbursements",
    )
    note = models.TextField(blank=True)

    class Meta:
        db_table = "disbursement_records"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_paid__gt=0),
                name="disbursement_records_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(payment_method="")
                | models.Q(payment_method__in=PaymentMethod.values),
                name="disbursement_records_method_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["installment"], name="ix_disbursements_installment"),
            models.Index(fields=["organization", "-paid_at"], name="ix_disbursements_org_date"),
        ]

    def __str__(self):
        return self.payment_reference or f"{self.amount_paid} {self.currency}"


class LoanRepayment(UUIDPrimaryKey):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="loan_repayments",
    )
    fund = models.ForeignKey(
        "fund_disbursement.Fund",
        on_delete=models.CASCADE,
        related_name="loan_repayments",
    )
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=LoanRepaymentStatus.choices,
        default=LoanRepaymentStatus.SCHEDULED,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_loan_repayments",
    )

    class Meta:
        db_table = "loan_repayments"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_due__gt=0),
                name="loan_repayments_amount_due_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=LoanRepaymentStatus.values),
                name="loan_repayments_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["fund", "due_date"], name="ix_repayments_fund")]

    def __str__(self):
        return f"{self.fund_id} · {self.due_date} · {self.status}"
