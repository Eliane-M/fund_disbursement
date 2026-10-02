from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from accounts.models import OTPPurpose

User = get_user_model()


class MembershipMiniSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    organization = serializers.UUIDField(source="organization_id")
    organization_name = serializers.CharField(source="organization.name")
    role = serializers.CharField()
    status = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    is_platform_admin = serializers.SerializerMethodField()
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "is_email_verified",
            "is_first_login",
            "is_platform_admin",
            "memberships",
            "date_joined",
        )
        read_only_fields = (
            "id",
            "email",
            "is_email_verified",
            "is_first_login",
            "date_joined",
        )

    def get_is_platform_admin(self, user):
        from accounts.permissions import is_platform_admin

        return is_platform_admin(user)

    def get_memberships(self, user):
        memberships = user.memberships.select_related("organization")
        return MembershipMiniSerializer(memberships, many=True).data


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=10, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        return User.objects.normalize_email(value)

    def validate_password(self, value):
        validate_password(value)
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        return User.objects.normalize_email(value)


class OTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)

    def validate_email(self, value):
        return User.objects.normalize_email(value)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must be a 6-digit code.")
        return value


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=OTPPurpose.choices)

    def validate_email(self, value):
        return User.objects.normalize_email(value)


class PasswordForgotSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return User.objects.normalize_email(value)


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=10, trim_whitespace=False)

    def validate_email(self, value):
        return User.objects.normalize_email(value)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must be a 6-digit code.")
        return value

    def validate_new_password(self, value):
        validate_password(value)
        return value


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, min_length=10, trim_whitespace=False)

    def validate_new_password(self, value):
        validate_password(value, user=self.context.get("user"))
        return value


class SetInitialPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=10, trim_whitespace=False)

    def validate_new_password(self, value):
        validate_password(value, user=self.context.get("user"))
        return value


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
