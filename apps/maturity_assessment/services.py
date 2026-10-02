import uuid

from django.db import transaction
from django.db.models import Avg, Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError

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


def create_invitation(assessment, respondent, invited_by, due_date=None):
    if assessment.status != AssessmentStatus.LIVE or assessment.current_version_id is None:
        raise ValidationError({"detail": "Publish the assessment before inviting respondents."})
    if respondent.organization_id != assessment.organization_id:
        raise ValidationError({"respondent": "Respondent must belong to the same organization."})
    return AssessmentInvitation.objects.create(
        organization=assessment.organization,
        assessment=assessment,
        assessment_version=assessment.current_version,
        respondent=respondent,
        access_token=uuid.uuid4().hex,
        status=InvitationStatus.INVITED,
        due_date=due_date,
        invited_by=invited_by,
    )


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
