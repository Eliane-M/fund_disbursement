import threading
import uuid

from django.db import connections, transaction
from django.db.models import Avg, Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import MembershipRole, MembershipStatus, OrganizationMembership
from apps.core.models import Notification, NotificationChannel, NotificationStatus
from apps.maturity_assessment import scoring
from accounts.services import ensure_respondent_account
from apps.maturity_assessment.emails import (
    send_assessment_invitation_email,
    send_assessment_submitted_email,
)
from apps.maturity_assessment.models import (
    Assessment,
    AssessmentInvitation,
    AssessmentStatus,
    AssessmentVersion,
    InvitationStatus,
    Report,
    ReportShareStatus,
)


def _build_snapshot(assessment):
    capabilities = []
    for cap in assessment.capabilities.filter(is_archived=False).order_by("display_order"):
        capabilities.append(
            {
                "id": str(cap.id),
                "name": cap.name,
                "weight_pct": str(cap.weight_pct),
                "target_score": str(cap.target_score) if cap.target_score is not None else None,
                "sub_capabilities": [
                    {"id": str(sub.id), "name": sub.name}
                    for sub in cap.sub_capabilities.filter(is_archived=False).order_by("display_order")
                ],
            }
        )
    questions = [
        {
            "id": str(q.id),
            "capability_id": str(q.capability_id),
            "question_type": q.question_type,
            "max_points": str(q.max_points),
        }
        for q in assessment.questions.filter(is_archived=False).order_by("page_no", "display_order")
    ]
    bands = [
        {"id": str(b.id), "label": b.label, "min_score": str(b.min_score), "max_score": str(b.max_score)}
        for b in assessment.maturity_bands.all().order_by("display_order")
    ]
    return {"capabilities": capabilities, "questions": questions, "maturity_bands": bands}


@transaction.atomic
def publish_assessment(assessment, user):
    if not assessment.capabilities.filter(is_archived=False).exists():
        raise ValidationError({"detail": "Add at least one capability before publishing."})
    if not assessment.questions.filter(is_archived=False).exists():
        raise ValidationError({"detail": "Add at least one question before publishing."})

    next_version_no = (assessment.versions.aggregate(n=Max("version_no"))["n"] or 0) + 1
    version = AssessmentVersion.objects.create(
        assessment=assessment,
        version_no=next_version_no,
        snapshot=_build_snapshot(assessment),
        published_by=user,
    )
    assessment.current_version = version
    assessment.status = AssessmentStatus.LIVE
    assessment.published_at = timezone.now()
    assessment.save(update_fields=["current_version", "status", "published_at", "updated_at"])
    return version


def archive_assessment(assessment):
    assessment.status = AssessmentStatus.ARCHIVED
    assessment.archived_at = timezone.now()
    assessment.save(update_fields=["status", "archived_at", "updated_at"])
    return assessment


def send_invitation(invitation, temp_password=None):
    send_assessment_invitation_email(invitation, temp_password=temp_password)
    invitation.sent_at = timezone.now()
    invitation.save(update_fields=["sent_at"])
    return invitation


@transaction.atomic
def create_invitation(assessment, respondent, invited_by, due_date=None):
    if assessment.status != AssessmentStatus.LIVE or assessment.current_version_id is None:
        raise ValidationError({"detail": "Publish the assessment before inviting respondents."})
    if respondent.organization_id != assessment.organization_id:
        raise ValidationError({"respondent": "Respondent must belong to the same organization."})
    if not respondent.primary_contact_email:
        raise ValidationError({"respondent": "Add a primary contact email to this respondent before inviting them."})
    invitation = AssessmentInvitation.objects.create(
        organization=assessment.organization,
        assessment=assessment,
        assessment_version=assessment.current_version,
        respondent=respondent,
        access_token=uuid.uuid4().hex,
        status=InvitationStatus.INVITED,
        due_date=due_date,
        invited_by=invited_by,
    )
    _, temp_password = ensure_respondent_account(respondent=respondent, invited_by=invited_by)
    return send_invitation(invitation, temp_password=temp_password)


def update_report_share_status(report, share_status, user):
    update_fields = ["share_status"]
    report.share_status = share_status
    if share_status == ReportShareStatus.SHARED:
        report.shared_at = timezone.now()
        report.shared_by = user
        update_fields += ["shared_at", "shared_by"]
        if not report.share_token:
            report.share_token = uuid.uuid4().hex
            update_fields.append("share_token")
    report.save(update_fields=update_fields)
    return report


def dashboard_stats(organization_id):
    active_assessments = Assessment.objects.filter(
        organization_id=organization_id, status=AssessmentStatus.LIVE
    ).count()
    respondents_invited = AssessmentInvitation.objects.filter(organization_id=organization_id).count()
    avg_score = Report.objects.filter(organization_id=organization_id).aggregate(avg=Avg("overall_score"))["avg"]
    reports_shared = Report.objects.filter(
        organization_id=organization_id, share_status=ReportShareStatus.SHARED
    ).count()
    return {
        "active_assessments": active_assessments,
        "respondents_invited": respondents_invited,
        "avg_maturity_score": round(float(avg_score), 1) if avg_score is not None else None,
        "reports_shared": reports_shared,
    }


# --- Respondent submission ----------------------------------------------


STAFF_ROLES_FOR_REVIEW = (MembershipRole.ORG_ADMIN, MembershipRole.REVIEWER)


def reviewers_for(organization_id):
    """Everyone who can act on a submission: reviewers and org admins."""
    return (
        OrganizationMembership.objects.filter(
            organization_id=organization_id,
            role__in=STAFF_ROLES_FOR_REVIEW,
            status=MembershipStatus.ACTIVE,
        )
        .select_related("user")
        .order_by("role")
    )


def notify_submission(invitation, report, pending_review):
    """In-app notification for every reviewer, plus an email. A failed send must
    not roll back the submission, so delivery errors are recorded, not raised."""
    memberships = list(reviewers_for(invitation.organization_id))
    if not memberships:
        return []

    subject = f"{invitation.respondent.name} submitted {invitation.assessment.name}"
    payload = {
        "invitation_id": str(invitation.id),
        "report_id": str(report.id),
        "respondent_name": invitation.respondent.name,
        "assessment_name": invitation.assessment.name,
        "overall_score": str(report.overall_score),
        "maturity_band_label": report.maturity_band_label,
        "pending_review": pending_review,
    }
    notifications = Notification.objects.bulk_create(
        [
            Notification(
                organization_id=invitation.organization_id,
                recipient_user=membership.user,
                recipient_email=membership.user.email,
                channel=NotificationChannel.IN_APP,
                template_key="assessment.submitted",
                subject=subject,
                payload=payload,
                related_entity_type="assessment_invitation",
                related_entity_id=invitation.id,
                status=NotificationStatus.SENT,
                sent_at=timezone.now(),
            )
            for membership in memberships
        ]
    )

    recipients = [m.user.email for m in memberships if m.user.email]
    if recipients:
        _send_in_background(invitation, report, pending_review, recipients, notifications)
    return notifications


def _send_in_background(invitation, report, pending_review, recipients, notifications):
    """SMTP can take ~20s to time out, and the respondent is waiting on the
    submit response — so delivery runs off the request. The in-app notification
    is already saved, so a failed send only costs the email copy."""

    def deliver():
        try:
            send_assessment_submitted_email(invitation, report, pending_review, recipients)
        except Exception as exc:
            Notification.objects.filter(id__in=[n.id for n in notifications]).update(
                last_error=str(exc)[:500]
            )
        finally:
            connections.close_all()

    threading.Thread(target=deliver, daemon=True).start()


@transaction.atomic
def submit_invitation(invitation, user=None):
    """Lock in the respondent's answers, score them and build the report."""
    if invitation.status == InvitationStatus.SUBMITTED:
        raise ValidationError({"detail": "This assessment has already been submitted."})
    if invitation.status in (InvitationStatus.CANCELLED, InvitationStatus.EXPIRED):
        raise ValidationError({"detail": "This invitation is no longer open."})

    missing = scoring.unanswered_required_questions(invitation)
    if missing:
        raise ValidationError(
            {"detail": f"{len(missing)} required question(s) still need an answer."}
        )

    invitation.status = InvitationStatus.SUBMITTED
    invitation.submitted_at = timezone.now()
    invitation.last_activity_at = timezone.now()
    invitation.save(update_fields=["status", "submitted_at", "last_activity_at"])

    report, pending_review = scoring.generate_report(invitation)
    transaction.on_commit(lambda: notify_submission(invitation, report, pending_review))
    return report, pending_review


def touch_in_progress(invitation):
    """Called whenever answers are saved, so the reviewer sees real progress."""
    fields = ["last_activity_at"]
    invitation.last_activity_at = timezone.now()
    if invitation.status == InvitationStatus.INVITED:
        invitation.status = InvitationStatus.IN_PROGRESS
        fields.append("status")
    if invitation.started_at is None:
        invitation.started_at = timezone.now()
        fields.append("started_at")
    invitation.save(update_fields=fields)
    return invitation
