import json

from django.core.files.storage import default_storage
from django.db.models import Count, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import MembershipRole, MembershipStatus, OrganizationMembership
from apps.core.permissions import assert_org_member, require_organization_id
from apps.fund_disbursement import services
from apps.fund_disbursement.models import (
    DisbursementRecord,
    EvidenceFile,
    EvidenceRequirementType,
    EvidenceSubmission,
    Fund,
    Installment,
    InstallmentStatus,
    Milestone,
    MilestoneEvidenceRequirement,
    MilestoneKPI,
)
from apps.fund_disbursement.serializers import (
    DecideSubmissionSerializer,
    DisbursementRecordSerializer,
    EvidenceRequirementTypeSerializer,
    EvidenceSubmissionSerializer,
    FundLifecycleSerializer,
    FundListSerializer,
    FundSerializer,
    InstallmentSerializer,
    MilestoneEvidenceRequirementSerializer,
    MilestoneKPISerializer,
    MilestoneSerializer,
    RecordDisbursementSerializer,
    ReviewDecisionSerializer,
    ReviewQueueItemSerializer,
    SubmitEvidenceSerializer,
)

WRITE_ROLES = (MembershipRole.ORG_ADMIN, MembershipRole.REVIEWER)
# Org-level fund data is internal: respondents get their own scoped /my/ endpoints.
STAFF_ROLES = WRITE_ROLES


def _get_fund_for(request, fund_id, roles=STAFF_ROLES):
    fund = get_object_or_404(Fund, pk=fund_id)
    assert_org_member(request.user, fund.organization_id, roles=roles)
    return fund


def _get_milestone_for(request, milestone_id, roles=STAFF_ROLES):
    milestone = get_object_or_404(Milestone.objects.select_related("fund"), pk=milestone_id)
    assert_org_member(request.user, milestone.fund.organization_id, roles=roles)
    return milestone


def _get_installment_for(request, installment_id, roles=STAFF_ROLES):
    installment = get_object_or_404(
        Installment.objects.select_related("fund", "milestone"), pk=installment_id
    )
    assert_org_member(request.user, installment.fund.organization_id, roles=roles)
    return installment


def _get_submission_for(request, submission_id, roles=STAFF_ROLES):
    submission = get_object_or_404(
        EvidenceSubmission.objects.select_related("installment__fund", "milestone"), pk=submission_id
    )
    assert_org_member(request.user, submission.organization_id, roles=roles)
    return submission


@api_view(["GET"])
def dashboard(request):
    organization_id = require_organization_id(request)
    assert_org_member(request.user, organization_id, roles=STAFF_ROLES)
    return Response(services.dashboard_stats(organization_id))


# --- Evidence requirement types (org-level catalog) -------------------------


class EvidenceRequirementTypeListCreateView(generics.ListCreateAPIView):
    serializer_class = EvidenceRequirementTypeSerializer

    def get_queryset(self):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=STAFF_ROLES)
        return EvidenceRequirementType.objects.filter(organization_id=organization_id, is_active=True).order_by(
            "label"
        )

    def perform_create(self, serializer):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=WRITE_ROLES)
        serializer.save(organization_id=organization_id)


# --- Funds -------------------------------------------------------------


class FundListCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        return FundListSerializer if self.request.method == "GET" else FundSerializer

    def get_queryset(self):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=STAFF_ROLES)
        return (
            Fund.objects.filter(organization_id=organization_id)
            .annotate(
                milestone_count=Count("milestones", distinct=True),
                disbursed_total=Sum("installments__disbursement_records__amount_paid"),
            )
            .select_related("recipient")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=WRITE_ROLES)
        serializer.save(organization_id=organization_id, created_by=self.request.user)


class FundDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = FundSerializer
    queryset = Fund.objects.select_related("recipient")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT") else STAFF_ROLES
        assert_org_member(self.request.user, obj.organization_id, roles=roles)
        return obj


@api_view(["POST"])
def fund_lifecycle(request, pk):
    fund = _get_fund_for(request, pk, roles=WRITE_ROLES)
    serializer = FundLifecycleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    services.transition_fund(fund=fund, status=serializer.validated_data["status"])
    return Response(FundSerializer(fund).data)


# --- Milestones, KPIs, evidence requirements (builder) ----------------------


class MilestoneListCreateView(generics.ListCreateAPIView):
    serializer_class = MilestoneSerializer

    def get_queryset(self):
        _get_fund_for(self.request, self.kwargs["fund_id"])
        return (
            Milestone.objects.filter(fund_id=self.kwargs["fund_id"])
            .select_related("installment")
            .prefetch_related("kpis", "evidence_requirements")
            .order_by("sequence_position")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["fund"] = _get_fund_for(self.request, self.kwargs["fund_id"])
        return context

    def perform_create(self, serializer):
        fund = _get_fund_for(self.request, self.kwargs["fund_id"], roles=WRITE_ROLES)
        serializer.save(fund=fund)


class MilestoneDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MilestoneSerializer
    queryset = Milestone.objects.select_related("fund", "installment").prefetch_related(
        "kpis", "evidence_requirements"
    )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["fund"] = self.get_object().fund
        return context

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.fund.organization_id, roles=roles)
        return obj

    def perform_destroy(self, instance):
        instance.delete()


class MilestoneKPIListCreateView(generics.ListCreateAPIView):
    serializer_class = MilestoneKPISerializer

    def get_queryset(self):
        _get_milestone_for(self.request, self.kwargs["milestone_id"])
        return MilestoneKPI.objects.filter(milestone_id=self.kwargs["milestone_id"]).order_by("display_order")

    def perform_create(self, serializer):
        milestone = _get_milestone_for(self.request, self.kwargs["milestone_id"], roles=WRITE_ROLES)
        serializer.save(milestone=milestone)


class MilestoneKPIDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MilestoneKPISerializer
    queryset = MilestoneKPI.objects.select_related("milestone__fund")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.milestone.fund.organization_id, roles=roles)
        return obj


class MilestoneEvidenceRequirementListCreateView(generics.ListCreateAPIView):
    serializer_class = MilestoneEvidenceRequirementSerializer

    def get_queryset(self):
        _get_milestone_for(self.request, self.kwargs["milestone_id"])
        return MilestoneEvidenceRequirement.objects.filter(
            milestone_id=self.kwargs["milestone_id"]
        ).order_by("display_order")

    def perform_create(self, serializer):
        milestone = _get_milestone_for(self.request, self.kwargs["milestone_id"], roles=WRITE_ROLES)
        serializer.save(milestone=milestone)


class MilestoneEvidenceRequirementDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MilestoneEvidenceRequirementSerializer
    queryset = MilestoneEvidenceRequirement.objects.select_related("milestone__fund")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.milestone.fund.organization_id, roles=roles)
        return obj


# --- Installments, evidence, review -----------------------------------------


class InstallmentListView(generics.ListAPIView):
    serializer_class = InstallmentSerializer

    def get_queryset(self):
        _get_fund_for(self.request, self.kwargs["fund_id"])
        return (
            Installment.objects.filter(fund_id=self.kwargs["fund_id"])
            .select_related("milestone")
            .order_by("installment_no")
        )


class InstallmentDetailView(generics.RetrieveAPIView):
    serializer_class = InstallmentSerializer
    queryset = Installment.objects.select_related("fund", "milestone")

    def get_object(self):
        obj = super().get_object()
        assert_org_member(self.request.user, obj.fund.organization_id, roles=STAFF_ROLES)
        return obj

    def retrieve(self, request, *args, **kwargs):
        installment = self.get_object()
        submissions = installment.submissions.order_by("-attempt_no").prefetch_related("files", "kpi_results")
        decisions = installment.review_decisions.order_by("-decided_at")
        disbursements = installment.disbursement_records.order_by("-paid_at")
        return Response(
            {
                **InstallmentSerializer(installment).data,
                "submissions": EvidenceSubmissionSerializer(submissions, many=True).data,
                "decisions": ReviewDecisionSerializer(decisions, many=True).data,
                "disbursements": DisbursementRecordSerializer(disbursements, many=True).data,
            }
        )


def _read_evidence_request(request):
    """Parse an evidence submission sent as JSON (links only) or multipart (files + links)."""
    uploads = []
    payload = request.data
    if request.content_type and request.content_type.startswith("multipart"):
        try:
            kpi_results = json.loads(request.data.get("kpi_results") or "[]")
        except ValueError:
            raise ValidationError({"detail": "kpi_results must be valid JSON."})
        payload = {
            "respondent_note": request.data.get("respondent_note", ""),
            "files": [{"external_url": u} for u in request.data.getlist("links") if u.strip()],
            "kpi_results": kpi_results,
        }
        uploads = request.FILES.getlist("uploads")
        services.validate_uploads(uploads)

    serializer = SubmitEvidenceSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if not (data["files"] or uploads or data["respondent_note"].strip()):
        raise ValidationError({"detail": "Add a file, a link or a note."})
    return data, uploads


@api_view(["POST"])
def submit_evidence(request, pk):
    installment = _get_installment_for(request, pk, roles=WRITE_ROLES)
    if installment.status not in (InstallmentStatus.AWAITING_EVIDENCE, InstallmentStatus.INFO_REQUESTED):
        raise ValidationError({"detail": "This installment isn't currently accepting evidence."})

    data, uploads = _read_evidence_request(request)
    submission = services.submit_evidence(
        installment=installment,
        note=data["respondent_note"],
        files=data["files"],
        kpi_results=data["kpi_results"],
        submitted_by=request.user,
        uploads=uploads,
    )
    return Response(EvidenceSubmissionSerializer(submission).data, status=201)


@api_view(["GET"])
def evidence_file_download(request, pk):
    """Uploaded evidence is only readable by the org's staff or the recipient."""
    evidence = get_object_or_404(
        EvidenceFile.objects.select_related("file", "submission__installment__fund"), pk=pk
    )
    fund = evidence.submission.installment.fund
    is_staff = OrganizationMembership.objects.filter(
        user=request.user,
        organization_id=fund.organization_id,
        role__in=STAFF_ROLES,
        status=MembershipStatus.ACTIVE,
    ).exists()
    is_recipient = _my_fund_queryset(request.user).filter(pk=fund.pk).exists()
    if not (is_staff or is_recipient) or evidence.file is None:
        raise Http404
    return FileResponse(
        default_storage.open(evidence.file.storage_key, "rb"),
        as_attachment=True,
        filename=evidence.file.original_filename,
    )


@api_view(["POST"])
def decide_submission(request, pk):
    submission = _get_submission_for(request, pk, roles=WRITE_ROLES)
    serializer = DecideSubmissionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    services.decide_submission(
        submission=submission,
        decision=data["decision"],
        comment=data["comment"],
        reviewer=request.user,
    )
    return Response(EvidenceSubmissionSerializer(submission).data)


@api_view(["GET"])
def review_queue(request):
    organization_id = require_organization_id(request)
    assert_org_member(request.user, organization_id, roles=STAFF_ROLES)
    installments = (
        Installment.objects.filter(
            fund__organization_id=organization_id,
            status__in=[
                InstallmentStatus.AWAITING_EVIDENCE,
                InstallmentStatus.UNDER_REVIEW,
                InstallmentStatus.INFO_REQUESTED,
            ],
        )
        .select_related("fund", "fund__recipient", "milestone")
        .order_by("-unlocked_at")
    )
    return Response(ReviewQueueItemSerializer(installments, many=True).data)


@api_view(["POST"])
def disburse_installment(request, pk):
    installment = _get_installment_for(request, pk, roles=WRITE_ROLES)
    serializer = RecordDisbursementSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    record = services.record_disbursement(
        installment=installment,
        amount_paid=data["amount_paid"],
        currency=data["currency"],
        fx_rate_to_fund_ccy=data.get("fx_rate_to_fund_ccy"),
        payment_reference=data["payment_reference"],
        payment_method=data["payment_method"],
        paid_at=data["paid_at"],
        note=data["note"],
        recorded_by=request.user,
    )
    return Response(DisbursementRecordSerializer(record).data, status=201)


# --- Recipient (respondent) view -----------------------------------------


def _my_fund_queryset(user):
    """Funds granted to the respondent record(s) linked to this user. Drafts are
    still internal to the organization, so they are never shown."""
    respondent_ids = OrganizationMembership.objects.filter(
        user=user, status=MembershipStatus.ACTIVE, respondent__isnull=False
    ).values_list("respondent_id", flat=True)
    return (
        Fund.objects.filter(recipient_id__in=respondent_ids)
        .exclude(lifecycle_status="draft")
        .select_related("recipient", "organization")
    )


@api_view(["GET"])
def my_funds(request):
    funds = (
        _my_fund_queryset(request.user)
        .annotate(
            milestone_count=Count("milestones", distinct=True),
            disbursed_total=Sum("installments__disbursement_records__amount_paid"),
        )
        .order_by("-created_at")
    )
    data = FundListSerializer(funds, many=True).data
    for row, fund in zip(data, funds):
        row["organization_name"] = fund.organization.name
    return Response(data)


@api_view(["GET"])
def my_fund_detail(request, pk):
    fund = get_object_or_404(_my_fund_queryset(request.user), pk=pk)
    all_milestones = Milestone.objects.filter(fund=fund)
    # Milestones that haven't opened yet stay hidden (their targets, evidence
    # requirements and deadlines) so evidence can't be prepared ahead of time.
    # The respondent still sees how many there are in total.
    milestones = (
        all_milestones.exclude(installment__status=InstallmentStatus.NOT_STARTED)
        .select_related("installment")
        .prefetch_related("kpis", "evidence_requirements")
        .order_by("sequence_position")
    )
    return Response(
        {
            **FundSerializer(fund).data,
            "organization_name": fund.organization.name,
            "milestone_total": all_milestones.count(),
            "milestones": MilestoneSerializer(milestones, many=True).data,
        }
    )


def _get_my_installment(request, pk):
    installment = get_object_or_404(
        Installment.objects.select_related("fund", "milestone"),
        pk=pk,
        fund__in=_my_fund_queryset(request.user),
    )
    if installment.status == InstallmentStatus.NOT_STARTED:
        raise Http404
    return installment


@api_view(["GET"])
def my_installment_detail(request, pk):
    installment = _get_my_installment(request, pk)
    submissions = installment.submissions.order_by("-attempt_no").prefetch_related("files", "kpi_results")
    decisions = installment.review_decisions.order_by("-decided_at")
    disbursements = installment.disbursement_records.order_by("-paid_at")
    return Response(
        {
            **InstallmentSerializer(installment).data,
            "submissions": EvidenceSubmissionSerializer(submissions, many=True).data,
            "decisions": ReviewDecisionSerializer(decisions, many=True).data,
            "disbursements": DisbursementRecordSerializer(disbursements, many=True).data,
        }
    )


@api_view(["POST"])
def my_submit_evidence(request, pk):
    installment = _get_my_installment(request, pk)
    if installment.status not in (InstallmentStatus.AWAITING_EVIDENCE, InstallmentStatus.INFO_REQUESTED):
        raise ValidationError({"detail": "This milestone isn't currently accepting evidence."})

    data, uploads = _read_evidence_request(request)

    kpi_ids = {str(i) for i in installment.milestone.kpis.values_list("id", flat=True)}
    if any(str(r["milestone_kpi"]) not in kpi_ids for r in data["kpi_results"]):
        raise ValidationError({"detail": "A reported result doesn't belong to this milestone."})
    req_ids = {str(i) for i in installment.milestone.evidence_requirements.values_list("id", flat=True)}
    if any(f.get("requirement") and str(f["requirement"]) not in req_ids for f in data["files"]):
        raise ValidationError({"detail": "An evidence file doesn't belong to this milestone."})

    submission = services.submit_evidence(
        installment=installment,
        note=data["respondent_note"],
        files=data["files"],
        kpi_results=data["kpi_results"],
        submitted_by=request.user,
        uploads=uploads,
    )
    return Response(EvidenceSubmissionSerializer(submission).data, status=201)
