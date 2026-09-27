from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.base import TimestampedModel
from apps.core.models.organization import Organization


class RespondentType(models.TextChoices):
    COMPANY = "company", "Company"
    COOPERATIVE = "cooperative", "Cooperative"
    SME = "sme", "SME"
    CORPORATE = "corporate", "Corporate"
    INDIVIDUAL = "individual", "Individual"


class RespondentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ARCHIVED = "archived", "Archived"


class Respondent(TimestampedModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="respondents",
    )
    respondent_type = models.CharField(
        max_length=16,
        choices=RespondentType.choices,
        default=RespondentType.COMPANY,
    )
    name = models.TextField()
    legal_name = models.TextField(blank=True)
    registration_no = models.TextField(blank=True)
    sector_tag = models.TextField(blank=True)
    category = models.ForeignKey(
        "maturity_assessment.Category",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="respondents",
    )
    primary_contact_name = models.TextField(blank=True)
    primary_contact_email = models.EmailField(blank=True)
    primary_contact_phone = models.TextField(blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    district = models.TextField(blank=True)
    address = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=RespondentStatus.choices,
        default=RespondentStatus.ACTIVE,
    )
    external_reference = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_respondents",
    )

    class Meta:
        db_table = "respondents"
        constraints = [
            models.UniqueConstraint(fields=["id", "organization"], name="respondents_id_org_uniq"),
            models.CheckConstraint(
                condition=models.Q(respondent_type__in=RespondentType.values),
                name="respondents_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RespondentStatus.values),
                name="respondents_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["organization"], name="ix_respondents_org"),
            models.Index(fields=["organization", "name"], name="ix_respondents_org_name"),
        ]

    def clean(self):
        if self.category_id and self.category.organization_id != self.organization_id:
            raise ValidationError("Category must belong to the same organization.")

    def __str__(self):
        return self.name
