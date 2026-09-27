from django.conf import settings
from django.db import models

from apps.core.models.organization import Organization


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor_role = models.TextField(blank=True)
    action = models.TextField()
    entity_type = models.TextField()
    entity_id = models.UUIDField(null=True, blank=True)
    summary = models.TextField(blank=True)
    before_state = models.JSONField(null=True, blank=True)
    after_state = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="ix_audit_org_time"),
            models.Index(fields=["entity_type", "entity_id"], name="ix_audit_entity"),
        ]

    def __str__(self):
        return f"{self.action} · {self.entity_type}"
