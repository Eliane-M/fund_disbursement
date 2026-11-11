import hashlib
import os
import uuid

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.models import File, FilePurpose
from apps.fund_disbursement.models import (
    DisbursementRecord,
    EvidenceFile,
    EvidenceSubmission,
    EvidenceSubmissionStatus,
    Fund,
    FundLifecycleStatus,
    Installment,
    InstallmentStatus,
    KPIResult,
    MilestoneStatus,
    ReviewDecision,
    ReviewDecisionType,
)

# Fund lifecycle: which transitions are allowed from each current status.
ALLOWED_FUND_TRANSITIONS = {
    FundLifecycleStatus.DRAFT: {FundLifecycleStatus.ACTIVE, FundLifecycleStatus.CANCELLED},
    FundLifecycleStatus.ACTIVE: {
        FundLifecycleStatus.COMPLETED,
        FundLifecycleStatus.CANCELLED,
        FundLifecycleStatus.SUSPENDED,
    },
    FundLifecycleStatus.SUSPENDED: {FundLifecycleStatus.ACTIVE, FundLifecycleStatus.CANCELLED},
    FundLifecycleStatus.COMPLETED: set(),
    FundLifecycleStatus.CANCELLED: set(),
}


def _open_milestone(milestone):
    """Unlock a milestone for evidence submission (sets its 1:1 installment to awaiting_evidence)."""
    milestone.status = MilestoneStatus.OPEN
    milestone.save(update_fields=["status", "updated_at"])
    installment = milestone.installment
    installment.status = InstallmentStatus.AWAITING_EVIDENCE
    installment.unlocked_at = timezone.now()
    installment.save(update_fields=["status", "unlocked_at"])


def _open_milestones_unlocked_by(milestone):
    for next_milestone in milestone.unlocks.all():
        _open_milestone(next_milestone)


@transaction.atomic
def transition_fund(*, fund, status):
    allowed = ALLOWED_FUND_TRANSITIONS.get(fund.lifecycle_status, set())
    if status not in allowed:
        raise ValidationError({"status": f"Cannot move a {fund.lifecycle_status} fund to {status}."})

    if status == FundLifecycleStatus.ACTIVE and fund.lifecycle_status == FundLifecycleStatus.DRAFT:
        if not fund.milestones.exists():
            raise ValidationError({"detail": "Add at least one milestone before activating."})
        fund.activated_at = timezone.now()
        # Milestones with no prerequisite (unlocks_after_milestone is null) start
        # open immediately; others stay locked until their prerequisite is approved.
        # A "parallel" fund is simply one where every milestone has no prerequisite.
        for milestone in fund.milestones.filter(unlocks_after_milestone__isnull=True):
            _open_milestone(milestone)

    fund.lifecycle_status = status
    if status == FundLifecycleStatus.COMPLETED:
        fund.completed_at = timezone.now()
    fund.save()
    return fund


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOADS = 5
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".zip",
}


def validate_uploads(uploads):
    if len(uploads) > MAX_UPLOADS:
        raise ValidationError({"detail": f"Attach at most {MAX_UPLOADS} files."})
    for upload in uploads:
        ext = os.path.splitext(upload.name)[1].lower()
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            raise ValidationError({"detail": f"'{upload.name}' isn't an allowed file type."})
        if upload.size > MAX_UPLOAD_BYTES:
            raise ValidationError({"detail": f"'{upload.name}' is larger than 10 MB."})


def store_evidence_upload(*, organization, upload, user):
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    safe_name = os.path.basename(upload.name)
    key = default_storage.save(f"evidence/{organization.id}/{uuid.uuid4().hex}_{safe_name}", upload)
    return File.objects.create(
        organization=organization,
        storage_key=key,
        original_filename=safe_name,
        mime_type=upload.content_type or "application/octet-stream",
        size_bytes=upload.size,
        checksum_sha256=digest.hexdigest(),
        purpose=FilePurpose.EVIDENCE,
        uploaded_by=user,
    )


@transaction.atomic
def submit_evidence(*, installment, note, files, kpi_results, submitted_by, uploads=()):
    milestone = installment.milestone
    last_attempt = installment.submissions.aggregate(n=Max("attempt_no"))["n"] or 0

    submission = EvidenceSubmission.objects.create(
        organization=installment.fund.organization,
        installment=installment,
        milestone=milestone,
        attempt_no=last_attempt + 1,
        submitted_by=submitted_by,
        respondent_note=note,
        status=EvidenceSubmissionStatus.SUBMITTED,
    )

    EvidenceFile.objects.bulk_create(
        [
            EvidenceFile(
                submission=submission,
                external_url=f.get("external_url", ""),
                requirement_id=f.get("requirement"),
            )
            for f in files
        ]
    )
    for upload in uploads:
        stored = store_evidence_upload(
            organization=installment.fund.organization, upload=upload, user=submitted_by
        )
        EvidenceFile.objects.create(submission=submission, file=stored)
    KPIResult.objects.bulk_create(
        [
            KPIResult(
                submission=submission,
                milestone_kpi_id=kr["milestone_kpi"],
                reported_value=kr.get("reported_value"),
                reported_text=kr.get("reported_text", ""),
            )
            for kr in kpi_results
        ]
    )

    installment.status = InstallmentStatus.UNDER_REVIEW
    installment.save(update_fields=["status"])
    milestone.status = MilestoneStatus.UNDER_REVIEW
    milestone.save(update_fields=["status", "updated_at"])
    return submission


@transaction.atomic
def decide_submission(*, submission, decision, comment, reviewer):
    installment = submission.installment
    milestone = submission.milestone

    ReviewDecision.objects.create(
        organization=installment.fund.organization,
        submission=submission,
        installment=installment,
        reviewer_user=reviewer,
        reviewer_name=reviewer.full_name or reviewer.email,
        decision=decision,
        comment=comment,
    )

    submission.reviewed_at = timezone.now()

    if decision == ReviewDecisionType.APPROVED:
        submission.status = EvidenceSubmissionStatus.APPROVED
        installment.status = InstallmentStatus.READY_FOR_DISBURSEMENT
        installment.approved_at = timezone.now()
        installment.approved_by = reviewer
        installment.save(update_fields=["status", "approved_at", "approved_by"])
        milestone.status = MilestoneStatus.APPROVED
        milestone.completed_at = timezone.now()
        milestone.save(update_fields=["status", "completed_at", "updated_at"])
        _open_milestones_unlocked_by(milestone)
    elif decision == ReviewDecisionType.REJECTED:
        submission.status = EvidenceSubmissionStatus.REJECTED
        installment.status = InstallmentStatus.REJECTED
        installment.save(update_fields=["status"])
        milestone.status = MilestoneStatus.REJECTED
        milestone.save(update_fields=["status", "updated_at"])
    else:
        submission.status = EvidenceSubmissionStatus.INFO_REQUESTED
        installment.status = InstallmentStatus.INFO_REQUESTED
        installment.save(update_fields=["status"])
        milestone.status = MilestoneStatus.INFO_REQUESTED
        milestone.save(update_fields=["status", "updated_at"])

    submission.save(update_fields=["status", "reviewed_at"])
    return submission


@transaction.atomic
def record_disbursement(*, installment, amount_paid, currency, fx_rate_to_fund_ccy, payment_reference,
                         payment_method, paid_at, note, recorded_by):
    if installment.status != InstallmentStatus.READY_FOR_DISBURSEMENT:
        raise ValidationError({"detail": "This installment isn't approved and ready for disbursement yet."})

    record = DisbursementRecord.objects.create(
        organization=installment.fund.organization,
        installment=installment,
        amount_paid=amount_paid,
        currency=currency or installment.currency,
        fx_rate_to_fund_ccy=fx_rate_to_fund_ccy,
        payment_reference=payment_reference,
        payment_method=payment_method,
        paid_at=paid_at,
        recorded_by=recorded_by,
        note=note,
    )
    installment.status = InstallmentStatus.DISBURSED
    installment.disbursed_at = timezone.now()
    installment.save(update_fields=["status", "disbursed_at"])
    return record


def dashboard_stats(organization_id):
    active_funds = Fund.objects.filter(
        organization_id=organization_id, lifecycle_status=FundLifecycleStatus.ACTIVE
    ).count()
    total_committed = Fund.objects.filter(organization_id=organization_id).aggregate(s=Sum("total_amount"))["s"] or 0
    total_disbursed = DisbursementRecord.objects.filter(organization_id=organization_id).aggregate(
        s=Sum("amount_paid")
    )["s"] or 0
    pending_review = Installment.objects.filter(
        fund__organization_id=organization_id,
        status__in=[
            InstallmentStatus.AWAITING_EVIDENCE,
            InstallmentStatus.UNDER_REVIEW,
            InstallmentStatus.INFO_REQUESTED,
        ],
    ).count()
    return {
        "active_funds": active_funds,
        "total_committed": float(total_committed),
        "total_disbursed": float(total_disbursed),
        "installments_pending_review": pending_review,
    }
