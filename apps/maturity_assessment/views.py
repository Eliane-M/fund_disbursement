from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import MembershipRole, MembershipStatus, OrganizationMembership
from accounts.services import STAFF_ROLES
from apps.core.models import Respondent
from apps.core.permissions import assert_org_member, require_organization_id
from apps.maturity_assessment import scoring, services
from apps.maturity_assessment.models import (
    Assessment,
    AssessmentInvitation,
    Capability,
    Category,
    MaturityBand,
    Question,
    InvitationStatus,
    QuestionOption,
    QuestionType,
    Recommendation,
    Report,
    ReportShareStatus,
    Response as MaResponse,
    ResponseSelectedOption,
    SubCapability,
)
from apps.maturity_assessment.serializers import (
    AssessmentInvitationSerializer,
    AssessmentListSerializer,
    AssessmentSerializer,
    CapabilitySerializer,
    CategorySerializer,
    MaturityBandSerializer,
    GradeResponseSerializer,
    MyInvitationSerializer,
    MyReportDetailSerializer,
    MyReportSerializer,
    MyResponseSerializer,
    PendingResponseSerializer,
    QuestionnaireQuestionSerializer,
    QuestionSerializer,
    ReviewQueueItemSerializer,
    SaveAnswersSerializer,
    RecommendationSerializer,
    ReportDetailSerializer,
    ReportListSerializer,
    ReportShareUpdateSerializer,
    SubCapabilitySerializer,
)

WRITE_ROLES = (MembershipRole.ORG_ADMIN, MembershipRole.REVIEWER)


def _get_assessment_for(request, assessment_id, roles=None):
    assessment = get_object_or_404(Assessment, pk=assessment_id)
    assert_org_member(request.user, assessment.organization_id, roles=roles)
    return assessment


def _get_capability_for(request, capability_id, roles=None):
    capability = get_object_or_404(Capability.objects.select_related("assessment"), pk=capability_id)
    assert_org_member(request.user, capability.assessment.organization_id, roles=roles)
    return capability


@api_view(["GET"])
def dashboard(request):
    organization_id = require_organization_id(request)
    assert_org_member(request.user, organization_id, roles=STAFF_ROLES)
    return Response(services.dashboard_stats(organization_id))


# --- Categories ---------------------------------------------------------


class CategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = CategorySerializer

    def get_queryset(self):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id)
        return Category.objects.filter(organization_id=organization_id, is_archived=False).order_by("name")

    def perform_create(self, serializer):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=WRITE_ROLES)
        serializer.save(organization_id=organization_id, created_by=self.request.user)


class CategoryDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT") else None
        assert_org_member(self.request.user, obj.organization_id, roles=roles)
        return obj


# --- Assessments ---------------------------------------------------------


class AssessmentListCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        return AssessmentListSerializer if self.request.method == "GET" else AssessmentSerializer

    def get_queryset(self):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=STAFF_ROLES)
        return (
            Assessment.objects.filter(organization_id=organization_id)
            .annotate(respondent_count=Count("invitations", distinct=True))
            .select_related("category")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=WRITE_ROLES)
        category = serializer.validated_data.get("category")
        if category is not None and str(category.organization_id) != str(organization_id):
            raise ValidationError({"category": "Category must belong to the same organization."})
        serializer.save(organization_id=organization_id, created_by=self.request.user)


class AssessmentDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = AssessmentSerializer
    queryset = Assessment.objects.all()

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT") else None
        assert_org_member(self.request.user, obj.organization_id, roles=roles)
        return obj


@api_view(["POST"])
def assessment_publish(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    assert_org_member(request.user, assessment.organization_id, roles=WRITE_ROLES)
    services.publish_assessment(assessment, request.user)
    return Response(AssessmentSerializer(assessment).data)


@api_view(["POST"])
def assessment_archive(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    assert_org_member(request.user, assessment.organization_id, roles=WRITE_ROLES)
    services.archive_assessment(assessment)
    return Response(AssessmentSerializer(assessment).data)


# --- Capabilities / sub-capabilities --------------------------------------


class CapabilityListCreateView(generics.ListCreateAPIView):
    serializer_class = CapabilitySerializer

    def get_queryset(self):
        _get_assessment_for(self.request, self.kwargs["assessment_id"])
        return (
            Capability.objects.filter(assessment_id=self.kwargs["assessment_id"], is_archived=False)
            .prefetch_related("sub_capabilities")
            .order_by("display_order")
        )

    def perform_create(self, serializer):
        assessment = _get_assessment_for(self.request, self.kwargs["assessment_id"], roles=WRITE_ROLES)
        serializer.save(assessment=assessment)


class CapabilityDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CapabilitySerializer
    queryset = Capability.objects.select_related("assessment")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.assessment.organization_id, roles=roles)
        return obj

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=["is_archived"])


class SubCapabilityListCreateView(generics.ListCreateAPIView):
    serializer_class = SubCapabilitySerializer

    def get_queryset(self):
        _get_capability_for(self.request, self.kwargs["capability_id"])
        return SubCapability.objects.filter(
            capability_id=self.kwargs["capability_id"], is_archived=False
        ).order_by("display_order")

    def perform_create(self, serializer):
        capability = _get_capability_for(self.request, self.kwargs["capability_id"], roles=WRITE_ROLES)
        serializer.save(capability=capability)


class SubCapabilityDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SubCapabilitySerializer
    queryset = SubCapability.objects.select_related("capability__assessment")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.capability.assessment.organization_id, roles=roles)
        return obj

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=["is_archived"])


# --- Questions -------------------------------------------------------------


class QuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer

    def get_queryset(self):
        _get_assessment_for(self.request, self.kwargs["assessment_id"])
        return (
            Question.objects.filter(assessment_id=self.kwargs["assessment_id"], is_archived=False)
            .prefetch_related("options", "numeric_rules")
            .order_by("page_no", "display_order")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["assessment"] = _get_assessment_for(self.request, self.kwargs["assessment_id"])
        return context

    def perform_create(self, serializer):
        assessment = _get_assessment_for(self.request, self.kwargs["assessment_id"], roles=WRITE_ROLES)
        serializer.save(assessment=assessment)


class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = QuestionSerializer
    queryset = Question.objects.select_related("assessment").prefetch_related("options", "numeric_rules")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.assessment.organization_id, roles=roles)
        return obj

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=["is_archived"])


# --- Maturity bands & recommendations ---------------------------------------


class MaturityBandListCreateView(generics.ListCreateAPIView):
    serializer_class = MaturityBandSerializer

    def get_queryset(self):
        _get_assessment_for(self.request, self.kwargs["assessment_id"])
        return MaturityBand.objects.filter(assessment_id=self.kwargs["assessment_id"]).order_by("display_order")

    def perform_create(self, serializer):
        assessment = _get_assessment_for(self.request, self.kwargs["assessment_id"], roles=WRITE_ROLES)
        serializer.save(assessment=assessment)


class MaturityBandDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = MaturityBandSerializer
    queryset = MaturityBand.objects.select_related("assessment")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.assessment.organization_id, roles=roles)
        return obj


class RecommendationListCreateView(generics.ListCreateAPIView):
    serializer_class = RecommendationSerializer

    def get_queryset(self):
        _get_capability_for(self.request, self.kwargs["capability_id"])
        return Recommendation.objects.filter(capability_id=self.kwargs["capability_id"]).order_by("display_order")

    def perform_create(self, serializer):
        capability = _get_capability_for(self.request, self.kwargs["capability_id"], roles=WRITE_ROLES)
        serializer.save(capability=capability, assessment=capability.assessment)


class RecommendationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RecommendationSerializer
    queryset = Recommendation.objects.select_related("assessment")

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT", "DELETE") else None
        assert_org_member(self.request.user, obj.assessment.organization_id, roles=roles)
        return obj


# --- Invitations -------------------------------------------------------------


class InvitationListCreateView(generics.ListCreateAPIView):
    serializer_class = AssessmentInvitationSerializer

    def get_queryset(self):
        _get_assessment_for(self.request, self.kwargs["assessment_id"])
        return (
            AssessmentInvitation.objects.filter(assessment_id=self.kwargs["assessment_id"])
            .select_related("respondent")
            .order_by("-created_at")
        )

    def create(self, request, *args, **kwargs):
        assessment = _get_assessment_for(request, self.kwargs["assessment_id"], roles=WRITE_ROLES)
        respondent_id = request.data.get("respondent")
        if not respondent_id:
            raise ValidationError({"respondent": "This field is required."})
        respondent = get_object_or_404(Respondent, pk=respondent_id)
        invitation = services.create_invitation(
            assessment=assessment,
            respondent=respondent,
            invited_by=request.user,
            due_date=request.data.get("due_date") or None,
        )
        return Response(AssessmentInvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)


# --- Reports -------------------------------------------------------------


class ReportListView(generics.ListAPIView):
    serializer_class = ReportListSerializer

    def get_queryset(self):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=STAFF_ROLES)
        return (
            Report.objects.filter(organization_id=organization_id)
            .select_related("respondent", "respondent__category", "invitation")
            .order_by("-generated_at")
        )


class ReportDetailView(generics.RetrieveUpdateAPIView):
    queryset = Report.objects.select_related("respondent", "respondent__category", "invitation")

    def get_serializer_class(self):
        return ReportShareUpdateSerializer if self.request.method in ("PATCH", "PUT") else ReportDetailSerializer

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT") else STAFF_ROLES
        assert_org_member(self.request.user, obj.organization_id, roles=roles)
        return obj

    def update(self, request, *args, **kwargs):
        report = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_report_share_status(report, serializer.validated_data["share_status"], request.user)
        return Response(ReportDetailSerializer(report).data)


# --- Respondent-facing ("my") views --------------------------------------


def _my_respondent_ids(user):
    """Respondent records the signed-in user is linked to, through their active
    memberships. A respondent may be invited by several organizations, so this
    can span orgs — but never reaches a respondent the user isn't linked to."""
    return OrganizationMembership.objects.filter(
        user=user,
        status=MembershipStatus.ACTIVE,
        respondent__isnull=False,
    ).values_list("respondent_id", flat=True)


class MyInvitationListView(generics.ListAPIView):
    """Every assessment the signed-in respondent was invited to."""

    serializer_class = MyInvitationSerializer

    def get_queryset(self):
        queryset = (
            AssessmentInvitation.objects.filter(respondent_id__in=_my_respondent_ids(self.request.user))
            .select_related("organization", "assessment", "assessment__category", "respondent", "report")
            .order_by("-created_at")
        )
        organization_id = self.request.query_params.get("organization")
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset


class MyReportListView(generics.ListAPIView):
    """Scores for the signed-in respondent, once an admin has shared them."""

    serializer_class = MyReportSerializer

    def get_queryset(self):
        queryset = (
            Report.objects.filter(
                respondent_id__in=_my_respondent_ids(self.request.user),
                share_status=ReportShareStatus.SHARED,
            )
            .select_related("organization", "respondent", "respondent__category", "invitation__assessment")
            .order_by("-generated_at")
        )
        organization_id = self.request.query_params.get("organization")
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset


@api_view(["GET"])
def my_report_detail(request, pk):
    """One shared report, with its capability scores and recommendations."""
    report = get_object_or_404(
        Report.objects.select_related(
            "organization", "respondent", "respondent__category", "invitation", "invitation__assessment"
        ),
        pk=pk,
        respondent_id__in=_my_respondent_ids(request.user),
        share_status=ReportShareStatus.SHARED,
    )
    return Response(MyReportDetailSerializer(report).data)


def _my_invitation_or_404(request, pk):
    return get_object_or_404(
        AssessmentInvitation.objects.select_related(
            "assessment", "assessment__category", "organization", "respondent"
        ),
        pk=pk,
        respondent_id__in=_my_respondent_ids(request.user),
    )


@api_view(["GET"])
def my_assessment_detail(request, pk):
    """The questionnaire plus whatever this respondent has answered so far."""
    invitation = _my_invitation_or_404(request, pk)
    questions = (
        Question.objects.filter(assessment_id=invitation.assessment_id, is_archived=False)
        .prefetch_related("options")
        .order_by("page_no", "display_order")
    )
    capabilities = (
        Capability.objects.filter(assessment_id=invitation.assessment_id, is_archived=False)
        .prefetch_related("sub_capabilities")
        .order_by("display_order")
    )
    responses = invitation.responses.prefetch_related("selected_options").all()
    return Response(
        {
            "invitation": MyInvitationSerializer(invitation).data,
            "capabilities": CapabilitySerializer(capabilities, many=True).data,
            "questions": QuestionnaireQuestionSerializer(questions, many=True).data,
            "responses": MyResponseSerializer(responses, many=True).data,
        }
    )


@api_view(["PUT"])
def my_assessment_answers(request, pk):
    """Save a partial set of answers. Safe to call repeatedly as a draft save."""
    invitation = _my_invitation_or_404(request, pk)
    if invitation.status == InvitationStatus.SUBMITTED:
        raise ValidationError({"detail": "This assessment has already been submitted."})

    serializer = SaveAnswersSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    answers = serializer.validated_data["answers"]

    allowed_questions = {
        q.id: q
        for q in Question.objects.filter(assessment_id=invitation.assessment_id, is_archived=False)
    }

    with transaction.atomic():
        for answer in answers:
            question = allowed_questions.get(answer["question"])
            if question is None:
                raise ValidationError({"question": "Unknown question for this assessment."})
            response, _ = MaResponse.objects.update_or_create(
                invitation=invitation,
                question=question,
                defaults={
                    "answer_value": answer.get("answer_value"),
                    "is_not_applicable": answer.get("is_not_applicable", False),
                },
            )
            option_ids = answer.get("selected_options") or []
            response.selected_options.all().delete()
            if option_ids:
                valid_options = QuestionOption.objects.filter(id__in=option_ids, question=question)
                ResponseSelectedOption.objects.bulk_create(
                    [
                        ResponseSelectedOption(response=response, question_option=option)
                        for option in valid_options
                    ]
                )
        services.touch_in_progress(invitation)

    responses = invitation.responses.prefetch_related("selected_options").all()
    return Response({"responses": MyResponseSerializer(responses, many=True).data})


@api_view(["POST"])
def my_assessment_submit(request, pk):
    """Submit, auto-score, generate the report and alert the org's reviewers."""
    invitation = _my_invitation_or_404(request, pk)
    report, pending_review = services.submit_invitation(invitation, request.user)
    return Response(
        {
            "detail": "Assessment submitted.",
            "pending_review": pending_review,
            "report_generated": True,
            "invitation": MyInvitationSerializer(invitation).data,
        },
        status=status.HTTP_201_CREATED,
    )


# --- Reviewer side of submissions ----------------------------------------


@api_view(["GET"])
def assessment_review_queue(request):
    """Submitted assessments, newest first, with anything still needing points."""
    organization_id = require_organization_id(request)
    assert_org_member(request.user, organization_id, roles=STAFF_ROLES)
    invitations = (
        AssessmentInvitation.objects.filter(
            organization_id=organization_id, status=InvitationStatus.SUBMITTED
        )
        .select_related("respondent", "assessment", "report")
        .order_by("-submitted_at")
    )
    items = []
    for invitation in invitations:
        invitation.pending_review = scoring.pending_review_count(invitation)
        invitation.free_text_count = sum(
            1
            for response in invitation.responses.select_related("question")
            if response.question.question_type == QuestionType.FREE_TEXT and not response.question.is_archived
        )
        items.append(invitation)
    return Response(ReviewQueueItemSerializer(items, many=True).data)


@api_view(["GET"])
def invitation_pending_responses(request, pk):
    """Every free-text answer on one submission. Scored questions can be given
    points; note-only questions are returned so the reviewer can still read them."""
    invitation = get_object_or_404(
        AssessmentInvitation.objects.select_related("organization"), pk=pk
    )
    assert_org_member(request.user, invitation.organization_id, roles=STAFF_ROLES)
    responses = [
        response
        for response in invitation.responses.select_related(
            "question", "question__capability", "invitation__respondent", "invitation__assessment"
        ).all()
        if response.question.question_type == QuestionType.FREE_TEXT and not response.question.is_archived
    ]
    return Response(PendingResponseSerializer(responses, many=True).data)


@api_view(["POST"])
def grade_response(request, pk):
    """Assign points to a free-text answer; the report recomputes immediately."""
    response = get_object_or_404(
        MaResponse.objects.select_related("question", "invitation", "invitation__organization"), pk=pk
    )
    assert_org_member(request.user, response.invitation.organization_id, roles=WRITE_ROLES)
    if response.question.question_type != QuestionType.FREE_TEXT:
        raise ValidationError({"detail": "Only free-text answers are scored manually."})

    serializer = GradeResponseSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    score = serializer.validated_data["reviewer_score"]
    if score > response.question.max_points:
        raise ValidationError(
            {"reviewer_score": f"Cannot exceed this question's {response.question.max_points} max points."}
        )

    response, report, pending = scoring.grade_response(response, score, request.user)
    return Response(
        {
            "response": PendingResponseSerializer(response).data,
            "overall_score": str(report.overall_score),
            "maturity_band_label": report.maturity_band_label,
            "pending_review": pending,
        }
    )
