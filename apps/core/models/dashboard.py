from django.conf import settings
from django.db import models

from apps.core.models.base import CreatedAtModel, UUIDPrimaryKey
from apps.core.models.organization import Organization


class DashboardLinkKind(models.TextChoices):
    FUNDER = "funder", "Funder"
    INTERNAL_BI = "internal_bi", "Internal BI"
    PARTNER = "partner", "Partner"
    GOVERNMENT = "government", "Government"
    OTHER = "other", "Other"


def default_visible_roles():
    return ["org_admin", "reviewer"]


class DashboardLinkGroup(UUIDPrimaryKey):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="dashboard_link_groups",
    )
    name = models.TextField()
    display_order = models.IntegerField(default=0)

    class Meta:
        db_table = "dashboard_link_groups"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="dashboard_link_groups_org_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["id", "organization"],
                name="dashboard_link_groups_id_org_uniq",
            ),
        ]

    def __str__(self):
        return self.name


class DashboardLink(CreatedAtModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="dashboard_links",
    )
    group = models.ForeignKey(
        DashboardLinkGroup,
        on_delete=models.CASCADE,
        related_name="links",
    )
    title = models.TextField()
    url = models.TextField()
    initials = models.TextField(blank=True)
    link_kind = models.CharField(
        max_length=16,
        choices=DashboardLinkKind.choices,
        blank=True,
    )
    description = models.TextField(blank=True)
    visible_to_roles = models.JSONField(default=default_visible_roles)
    display_order = models.IntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_dashboard_links",
    )

    class Meta:
        db_table = "dashboard_links"
        indexes = [
            models.Index(
                fields=["organization", "group", "display_order"],
                name="ix_dashboard_links_org",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(link_kind="") | models.Q(link_kind__in=DashboardLinkKind.values),
                name="dashboard_links_kind_valid",
            ),
        ]

    def __str__(self):
        return self.title


class DashboardLinkVisit(models.Model):
    id = models.BigAutoField(primary_key=True)
    link = models.ForeignKey(
        DashboardLink,
        on_delete=models.CASCADE,
        related_name="visits",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dashboard_link_visits",
    )
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dashboard_link_visits"
        indexes = [
            models.Index(fields=["link", "user", "-opened_at"], name="ix_link_visits_link_user"),
        ]

    def __str__(self):
        return f"{self.link} · {self.user}"
