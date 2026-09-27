from django.db import models

from apps.core.models.base import UUIDPrimaryKey
from apps.core.models.organization import Organization


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELLED = "cancelled", "Cancelled"


class Plan(UUIDPrimaryKey):
    code = models.CharField(max_length=64, unique=True)
    name = models.TextField()
    price_per_month = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    max_respondents = models.IntegerField(null=True, blank=True)
    max_seats = models.IntegerField(null=True, blank=True)
    includes_assessment = models.BooleanField(default=True)
    includes_disbursement = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "plans"

    def __str__(self):
        return self.name


class OrganizationSubscription(UUIDPrimaryKey):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(
        max_length=16,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIALING,
    )
    current_period_start = models.DateField(null=True, blank=True)
    current_period_end = models.DateField(null=True, blank=True)
    seats = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "organization_subscriptions"
        indexes = [models.Index(fields=["organization"], name="ix_subscriptions_org")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=SubscriptionStatus.values),
                name="organization_subscriptions_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.organization} · {self.plan} ({self.status})"
