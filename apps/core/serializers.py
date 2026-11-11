from rest_framework import serializers

from accounts.models import MembershipRole
from apps.core.models import Notification, Organization, Respondent


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "id",
            "tenant_no",
            "name",
            "slug",
            "sector_focus",
            "country_code",
            "default_currency",
            "status",
        )
        read_only_fields = fields


class OrganizationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("name", "sector_focus", "country_code", "default_currency")

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name is required.")
        return value.strip()


class CategoryMiniSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class RespondentSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True, default="")

    class Meta:
        model = Respondent
        fields = (
            "id",
            "organization",
            "respondent_type",
            "name",
            "legal_name",
            "registration_no",
            "sector_tag",
            "category",
            "category_name",
            "primary_contact_name",
            "primary_contact_email",
            "primary_contact_phone",
            "country_code",
            "district",
            "address",
            "status",
            "external_reference",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "organization", "created_at")


class MembershipSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    user = serializers.UUIDField(source="user_id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    role = serializers.CharField()
    status = serializers.CharField(read_only=True)
    respondent = serializers.UUIDField(source="respondent_id", read_only=True, default=None)
    respondent_name = serializers.CharField(source="respondent.name", read_only=True, default="")
    invited_at = serializers.DateTimeField(read_only=True)
    accepted_at = serializers.DateTimeField(read_only=True)


class InviteMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField(required=False, allow_blank=True, default="")
    last_name = serializers.CharField(required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=MembershipRole.choices)
    respondent = serializers.UUIDField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if attrs["role"] == MembershipRole.RESPONDENT and not attrs.get("respondent"):
            raise serializers.ValidationError({"respondent": "Choose which respondent this account represents."})
        if attrs["role"] != MembershipRole.RESPONDENT and attrs.get("respondent"):
            raise serializers.ValidationError({"respondent": "Only the respondent role links to a respondent."})
        return attrs


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = (
            "id",
            "organization",
            "template_key",
            "subject",
            "payload",
            "related_entity_type",
            "related_entity_id",
            "status",
            "read_at",
            "created_at",
        )
