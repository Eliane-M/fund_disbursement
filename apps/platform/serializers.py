from rest_framework import serializers

from accounts.models import MembershipRole
from apps.core.models import Organization


class PlatformOrganizationSerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True, default=0)
    respondent_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Organization
        fields = (
            "id",
            "tenant_no",
            "name",
            "slug",
            "sector_focus",
            "org_type",
            "contact_email",
            "phone",
            "location",
            "country_code",
            "default_currency",
            "status",
            "member_count",
            "respondent_count",
            "created_at",
        )
        read_only_fields = ("id", "tenant_no", "slug", "created_at")


class OrganizationAdminSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True, default="")


class PlatformOrganizationCreateSerializer(serializers.ModelSerializer):
    admin = OrganizationAdminSerializer(required=False)

    class Meta:
        model = Organization
        fields = ("name", "sector_focus", "org_type", "contact_email", "phone", "location", "country_code", "default_currency", "admin")

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name is required.")
        return value.strip()


class PlatformOrganizationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("trial", "active", "suspended", "closed"))


class PlatformUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    full_name = serializers.CharField()
    phone_number = serializers.CharField()
    status = serializers.CharField()
    is_platform_admin = serializers.BooleanField()
    membership_count = serializers.IntegerField()
    date_joined = serializers.DateTimeField()


class UpdatePlatformUserSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=("pending", "active", "disabled"), required=False)


class InvitePlatformMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=MembershipRole.choices)


class CreatePlatformAdminSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    phone_number = serializers.CharField(required=False, allow_blank=True, default="")
