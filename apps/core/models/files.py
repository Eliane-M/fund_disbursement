from django.conf import settings
from django.db import models

from apps.core.models.base import CreatedAtModel
from apps.core.models.organization import Organization


class FilePurpose(models.TextChoices):
    EVIDENCE = "evidence", "Evidence"
    REPORT_PDF = "report_pdf", "Report PDF"
    LOGO = "logo", "Logo"
    IMPORT = "import", "Import"
    OTHER = "other", "Other"


class FileScanStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CLEAN = "clean", "Clean"
    INFECTED = "infected", "Infected"
    SKIPPED = "skipped", "Skipped"


class File(CreatedAtModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="files",
    )
    storage_key = models.TextField(unique=True)
    original_filename = models.TextField()
    mime_type = models.TextField()
    size_bytes = models.BigIntegerField()
    checksum_sha256 = models.TextField(blank=True)
    purpose = models.CharField(
        max_length=16,
        choices=FilePurpose.choices,
        default=FilePurpose.EVIDENCE,
    )
    scan_status = models.CharField(
        max_length=16,
        choices=FileScanStatus.choices,
        default=FileScanStatus.PENDING,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_files",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "files"
        constraints = [
            models.UniqueConstraint(fields=["id", "organization"], name="files_id_org_uniq"),
            models.CheckConstraint(condition=models.Q(size_bytes__gte=0), name="files_size_bytes_gte_0"),
            models.CheckConstraint(
                condition=models.Q(purpose__in=FilePurpose.values),
                name="files_purpose_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(scan_status__in=FileScanStatus.values),
                name="files_scan_status_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization"],
                name="ix_files_org",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self):
        return self.original_filename
