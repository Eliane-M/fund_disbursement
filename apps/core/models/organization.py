from django.conf import settings as django_settings
from django.db import models

from apps.core.models.base import TimestampedModel


class OrganizationStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    CLOSED = "closed", "Closed"


class PlatformModule(models.TextChoices):
    PLATFORM = "platform", "Platform"
    ASSESSMENT = "assessment", "Assessment"
    DISBURSEMENT = "disbursement", "Disbursement"
    DASHBOARDS_HUB = "dashboards_hub", "Dashboards hub"


class Organization(TimestampedModel):
    tenant_no = models.PositiveIntegerField(unique=True, editable=False)
    name = models.TextField()
    slug = models.SlugField(max_length=255, unique=True)
    sector_focus = models.TextField(blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    default_currency = models.CharField(max_length=3, default="USD")
    timezone = models.CharField(max_length=64, default="Africa/Kigali")
    locale = models.CharField(max_length=16, default="en")
    auto_share_reports = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.TRIAL,
    )
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    onboarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "organizations"
        constraints = [
            models.UniqueConstraint(fields=["id", "status"], name="organizations_id_status_uniq"),
            models.CheckConstraint(
                condition=models.Q(status__in=OrganizationStatus.values),
                name="organizations_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["status"], name="ix_organizations_status")]

    def save(self, *args, **kwargs):
        if not self.tenant_no:
            last = (
                Organization.objects.order_by("-tenant_no")
                .values_list("tenant_no", flat=True)
                .first()
            )
            self.tenant_no = (last or 999) + 1
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (#{self.tenant_no})"


class OrganizationModule(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="modules",
    )
    module = models.CharField(
        max_length=32,
        choices=[
            (PlatformModule.ASSESSMENT, PlatformModule.ASSESSMENT.label),
            (PlatformModule.DISBURSEMENT, PlatformModule.DISBURSEMENT.label),
            (PlatformModule.DASHBOARDS_HUB, PlatformModule.DASHBOARDS_HUB.label),
        ],
    )
    is_enabled = models.BooleanField(default=True)
    enabled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organization_modules"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "module"],
                name="organization_modules_pkey",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    module__in=[
                        PlatformModule.ASSESSMENT,
                        PlatformModule.DISBURSEMENT,
                        PlatformModule.DASHBOARDS_HUB,
                    ]
                ),
                name="organization_modules_module_valid",
            ),
        ]

    def __str__(self):
        return f"{self.organization} · {self.module}"


class OrganizationSetting(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="settings",
    )
    module = models.CharField(max_length=32, choices=PlatformModule.choices)
    settings = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_organization_settings",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_settings"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "module"],
                name="organization_settings_pkey",
            ),
            models.CheckConstraint(
                condition=models.Q(module__in=PlatformModule.values),
                name="organization_settings_module_valid",
            ),
        ]

    def __str__(self):
        return f"{self.organization} · {self.module} settings"
