from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import CreatedAtModel, UUIDPrimaryKey
from apps.core.models.organization import Organization


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    IN_APP = "in_app", "In-app"


class NotificationStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    READ = "read", "Read"
    CANCELLED = "cancelled", "Cancelled"


class Notification(CreatedAtModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    recipient_email = models.EmailField(blank=True)
    channel = models.CharField(
        max_length=16,
        choices=NotificationChannel.choices,
        default=NotificationChannel.EMAIL,
    )
    template_key = models.TextField()
    subject = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    related_entity_type = models.TextField(blank=True)
    related_entity_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=NotificationStatus.choices,
        default=NotificationStatus.QUEUED,
    )
    scheduled_for = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        db_table = "notifications"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(channel__in=NotificationChannel.values),
                name="notifications_channel_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=NotificationStatus.values),
                name="notifications_status_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "scheduled_for"],
                name="ix_notifications_queue",
                condition=models.Q(status="queued"),
            ),
            models.Index(fields=["organization", "-created_at"], name="ix_notifications_org"),
        ]

    def __str__(self):
        return f"{self.template_key} · {self.status}"


class EmailTemplate(UUIDPrimaryKey):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="email_templates",
    )
    template_key = models.TextField()
    locale = models.CharField(max_length=16, default="en")
    subject = models.TextField()
    body_html = models.TextField()
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "email_templates"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "template_key", "locale"],
                name="email_templates_org_key_locale_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.template_key} ({self.locale})"
