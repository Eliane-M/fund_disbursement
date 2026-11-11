from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from accounts.models import MembershipRole, MembershipStatus, OrganizationMembership
from accounts.services import STAFF_ROLES, assert_role_available, invite_member
from apps.core.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    Organization,
    OrganizationModule,
    PlatformModule,
    Respondent,
)
from apps.core.permissions import assert_org_member, require_organization_id
from apps.core.serializers import (
    InviteMemberSerializer,
    MembershipSerializer,
    NotificationSerializer,
    OrganizationCreateSerializer,
    OrganizationSerializer,
    RespondentSerializer,
)

WRITE_ROLES = (MembershipRole.ORG_ADMIN, MembershipRole.REVIEWER)


def _serialize_organization(organization, membership):
    modules = list(
        OrganizationModule.objects.filter(
            organization=organization, is_enabled=True
        ).values_list("module", flat=True)
    )
    return {
        **OrganizationSerializer(organization).data,
        "role": membership.role,
        "modules": modules,
    }


def _unique_slug(name):
    base = slugify(name) or "organization"
    candidate = base
    suffix = 1
    while Organization.objects.filter(slug=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


@api_view(["GET"])
def organizations_list(request):
    # Self-serve org creation (POST) is disabled: organizations are now created
    # by a platform admin via /api/platform/organizations/. Left here commented
    # out so it's a one-line revert if that changes.
    #
    # if request.method == "POST":
    #     serializer = OrganizationCreateSerializer(data=request.data)
    #     serializer.is_valid(raise_exception=True)
    #     with transaction.atomic():
    #         organization = Organization.objects.create(
    #             slug=_unique_slug(serializer.validated_data["name"]),
    #             **serializer.validated_data,
    #         )
    #         OrganizationModule.objects.create(
    #             organization=organization, module=PlatformModule.ASSESSMENT, is_enabled=True
    #         )
    #         membership = OrganizationMembership.objects.create(
    #             organization=organization,
    #             user=request.user,
    #             role=MembershipRole.ORG_ADMIN,
    #             status=MembershipStatus.ACTIVE,
    #         )
    #     return Response(_serialize_organization(organization, membership), status=status.HTTP_201_CREATED)

    memberships = (
        OrganizationMembership.objects.filter(
            user=request.user, status=MembershipStatus.ACTIVE
        )
        .select_related("organization")
        .order_by("organization__name")
    )
    return Response([_serialize_organization(m.organization, m) for m in memberships])


@api_view(["GET"])
def organization_detail(request, slug):
    organization = get_object_or_404(Organization, slug=slug)
    membership = assert_org_member(request.user, organization.id)
    return Response(_serialize_organization(organization, membership))


class RespondentListCreateView(generics.ListCreateAPIView):
    serializer_class = RespondentSerializer

    def get_queryset(self):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=STAFF_ROLES)
        return Respondent.objects.filter(organization_id=organization_id).order_by("name")

    def perform_create(self, serializer):
        organization_id = require_organization_id(self.request)
        assert_org_member(self.request.user, organization_id, roles=WRITE_ROLES)
        category = serializer.validated_data.get("category")
        if category is not None and str(category.organization_id) != str(organization_id):
            raise ValidationError({"category": "Category must belong to the same organization."})
        serializer.save(organization_id=organization_id, created_by=self.request.user)


class RespondentDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = RespondentSerializer
    queryset = Respondent.objects.all()

    def get_object(self):
        obj = super().get_object()
        roles = WRITE_ROLES if self.request.method in ("PATCH", "PUT") else None
        assert_org_member(self.request.user, obj.organization_id, roles=roles)
        return obj


@api_view(["GET", "POST"])
def organization_members(request, organization_id):
    if request.method == "POST":
        assert_org_member(request.user, organization_id, roles=(MembershipRole.ORG_ADMIN,))
        serializer = InviteMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        respondent = None
        if data.get("respondent"):
            respondent = get_object_or_404(Respondent, pk=data["respondent"], organization_id=organization_id)

        organization = get_object_or_404(Organization, pk=organization_id)
        membership, is_new_account = invite_member(
            organization=organization,
            email=data["email"],
            role=data["role"],
            invited_by=request.user,
            first_name=data["first_name"],
            last_name=data["last_name"],
            respondent=respondent,
        )
        payload = MembershipSerializer(membership).data
        payload["email_sent"] = is_new_account
        return Response(payload, status=status.HTTP_201_CREATED)

    assert_org_member(request.user, organization_id)
    memberships = (
        OrganizationMembership.objects.filter(organization_id=organization_id)
        .select_related("user", "respondent")
        .order_by("user__first_name", "user__last_name")
    )
    return Response(MembershipSerializer(memberships, many=True).data)


@api_view(["PATCH", "DELETE"])
def membership_detail(request, pk):
    membership = get_object_or_404(OrganizationMembership.objects.select_related("user"), pk=pk)
    assert_org_member(request.user, membership.organization_id, roles=(MembershipRole.ORG_ADMIN,))

    if request.method == "DELETE":
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    role = request.data.get("role")
    membership_status = request.data.get("status")
    if role and role in MembershipRole.values:
        if role != membership.role:
            assert_role_available(membership.user, role, exclude_membership=membership)
        membership.role = role
    if membership_status and membership_status in MembershipStatus.values:
        membership.status = membership_status
    membership.save(update_fields=["role", "status"])
    return Response(MembershipSerializer(membership).data)


@api_view(["GET"])
def notifications_list(request):
    """In-app notifications for the signed-in user, newest first."""
    notifications = Notification.objects.filter(
        recipient_user=request.user, channel=NotificationChannel.IN_APP
    ).order_by("-created_at")[:50]
    return Response(NotificationSerializer(notifications, many=True).data)


@api_view(["POST"])
def notification_mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient_user=request.user)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.status = NotificationStatus.READ
        notification.save(update_fields=["read_at", "status"])
    return Response(NotificationSerializer(notification).data)
