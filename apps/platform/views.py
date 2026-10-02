from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.models import MembershipRole, OrganizationMembership, PlatformAdmin
from accounts.permissions import IsPlatformAdmin, is_platform_admin
from accounts.services import invite_member, reset_password_by_admin
from apps.core.models import Organization, OrganizationModule, PlatformModule
from apps.core.serializers import MembershipSerializer
from apps.platform.serializers import (
    InvitePlatformMemberSerializer,
    PlatformOrganizationCreateSerializer,
    PlatformOrganizationSerializer,
    PlatformOrganizationStatusSerializer,
    PlatformUserSerializer,
    UpdatePlatformUserSerializer,
)

User = get_user_model()


def _unique_slug(name):
    base = slugify(name) or "organization"
    candidate = base
    suffix = 1
    while Organization.objects.filter(slug=candidate).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def _paginate(request, queryset):
    page = max(int(request.query_params.get("page", 1)), 1)
    page_size = min(max(int(request.query_params.get("page_size", 10)), 1), 100)
    count = queryset.count()
    start = (page - 1) * page_size
    items = list(queryset[start : start + page_size])
    return items, {"count": count, "page": page, "page_size": page_size}


@api_view(["GET", "POST"])
@permission_classes([IsPlatformAdmin])
def organizations_list(request):
    if request.method == "POST":
        serializer = PlatformOrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        admin_data = data.pop("admin", None)

        with transaction.atomic():
            organization = Organization.objects.create(
                slug=_unique_slug(data["name"]),
                **data,
            )
            OrganizationModule.objects.create(
                organization=organization, module=PlatformModule.ASSESSMENT, is_enabled=True
            )
            if admin_data:
                invite_member(
                    organization=organization,
                    email=admin_data["email"],
                    role=MembershipRole.ORG_ADMIN,
                    invited_by=request.user,
                    first_name=admin_data["first_name"],
                    last_name=admin_data["last_name"],
                )
        organization.member_count = 1 if admin_data else 0
        organization.respondent_count = 0
        return Response(PlatformOrganizationSerializer(organization).data, status=status.HTTP_201_CREATED)

    organizations = Organization.objects.annotate(
        member_count=Count("memberships", distinct=True),
        respondent_count=Count("respondents", distinct=True),
    ).order_by("-created_at")

    search = request.query_params.get("search", "").strip()
    if search:
        organizations = organizations.filter(Q(name__icontains=search) | Q(contact_email__icontains=search))

    org_status = request.query_params.get("status", "").strip()
    if org_status:
        organizations = organizations.filter(status=org_status)

    items, meta = _paginate(request, organizations)
    return Response({"results": PlatformOrganizationSerializer(items, many=True).data, **meta})


@api_view(["GET", "PATCH"])
@permission_classes([IsPlatformAdmin])
def organization_detail(request, pk):
    organization = get_object_or_404(
        Organization.objects.annotate(
            member_count=Count("memberships", distinct=True),
            respondent_count=Count("respondents", distinct=True),
        ),
        pk=pk,
    )

    if request.method == "PATCH":
        serializer = PlatformOrganizationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization.status = serializer.validated_data["status"]
        organization.save(update_fields=["status", "updated_at"])

    return Response(PlatformOrganizationSerializer(organization).data)


@api_view(["GET", "POST"])
@permission_classes([IsPlatformAdmin])
def organization_members(request, pk):
    organization = get_object_or_404(Organization, pk=pk)

    if request.method == "POST":
        serializer = InvitePlatformMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        membership, is_new_account = invite_member(
            organization=organization,
            email=data["email"],
            role=data["role"],
            invited_by=request.user,
            first_name=data["first_name"],
            last_name=data["last_name"],
        )
        payload = MembershipSerializer(membership).data
        payload["email_sent"] = is_new_account
        return Response(payload, status=status.HTTP_201_CREATED)

    memberships = (
        OrganizationMembership.objects.filter(organization=organization)
        .select_related("user", "respondent")
        .order_by("user__first_name", "user__last_name")
    )
    return Response(MembershipSerializer(memberships, many=True).data)


def _serialize_user(u):
    return {
        "id": u.id,
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "full_name": u.full_name,
        "phone_number": u.phone_number,
        "status": u.status,
        "is_platform_admin": is_platform_admin(u),
        "membership_count": u.membership_count,
        "date_joined": u.date_joined,
    }


@api_view(["GET"])
@permission_classes([IsPlatformAdmin])
def users_list(request):
    users = User.objects.annotate(membership_count=Count("memberships", distinct=True)).order_by("-date_joined")

    search = request.query_params.get("search", "").strip()
    if search:
        users = users.filter(
            Q(email__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search)
        )

    user_status = request.query_params.get("status", "").strip()
    if user_status:
        users = users.filter(status=user_status)

    items, meta = _paginate(request, users)
    data = [_serialize_user(u) for u in items]
    return Response({"results": PlatformUserSerializer(data, many=True).data, **meta})


@api_view(["PATCH", "DELETE"])
@permission_classes([IsPlatformAdmin])
def user_detail(request, pk):
    user = get_object_or_404(User, pk=pk)

    if request.method == "DELETE":
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = UpdatePlatformUserSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    update_fields = []
    for field, value in serializer.validated_data.items():
        setattr(user, field, value)
        update_fields.append(field)
    if "status" in serializer.validated_data:
        # `status` is the user-facing lifecycle label; `is_active` is what the
        # login flow actually enforces (accounts.services.ensure_account_available),
        # so keep them in sync here.
        user.is_active = serializer.validated_data["status"] != "disabled"
        update_fields.append("is_active")
    user.save(update_fields=[*update_fields, "updated_at"])
    user.membership_count = user.memberships.count()
    return Response(_serialize_user(user))


@api_view(["POST"])
@permission_classes([IsPlatformAdmin])
def reset_user_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    reset_password_by_admin(user=user, actor=request.user)
    return Response({"detail": f"A new temporary password was emailed to {user.email}."})


@api_view(["POST", "DELETE"])
@permission_classes([IsPlatformAdmin])
def toggle_platform_admin(request, pk):
    user = get_object_or_404(User, pk=pk)

    if request.method == "DELETE":
        PlatformAdmin.objects.filter(user=user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    PlatformAdmin.objects.get_or_create(user=user, defaults={"granted_by": request.user})
    return Response({"id": str(user.id), "is_platform_admin": True})
