from django.conf import settings
from django.db import models

from apps.core.models.base import TimestampedModel


class Category(TimestampedModel):
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.TextField()
    description = models.TextField(blank=True)
    auto_share_reports = models.BooleanField(default=True)
    cloned_from_category = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clones",
    )
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_categories",
    )

    class Meta:
        db_table = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="categories_org_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["id", "organization"],
                name="categories_id_org_uniq",
            ),
        ]

    def __str__(self):
        return self.name
