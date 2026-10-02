from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import MembershipRole
from apps.core.models import Respondent
from apps.core.permissions import assert_org_member, require_organization_id
from apps.maturity_assessment import services
from apps.maturity_assessment.models import (
    Assessment,
    AssessmentInvitation,
    Capability,
    Category,
    MaturityBand,
    Question,
    Recommendation,
    Report,
    SubCapability,
)
from apps.maturity_assessment.serializers import (
    AssessmentInvitationSerializer,
    AssessmentListSerializer,
    AssessmentSerializer,
    CapabilitySerializer,
    CategorySerializer,
    MaturityBandSerializer,
    QuestionSerializer,
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
    assert_org_member(request.user, organization_id)
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
        assert_org_member(self.request.user, organization_id)
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
        assert_org_member(self.request.user, organization_id)
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
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT") else None
        assert_org_member(self.request.user, obj.organization_id, roles=roles)
        return obj

    def update(self, request, *args, **kwargs):
        report = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.update_report_share_status(report, serializer.validated_data["share_status"], request.user)
        return Response(ReportDetailSerializer(report).data)
