import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from accounts.managers import UserManager


class UserStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=32, blank=True)
    avatar_url = models.TextField(blank=True)
    locale = models.CharField(max_length=16, default="en")
    status = models.CharField(
        max_length=16,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    mfa_enabled = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_first_login = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        db_table = "accounts_user"
        ordering = ["-date_joined"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=UserStatus.values),
                name="accounts_user_status_valid",
            ),
        ]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())


class OTPPurpose(models.TextChoices):
    EMAIL_VERIFICATION = "email_verification", "Email verification"
    FIRST_LOGIN = "first_login", "First login"
    PASSWORD_RESET = "password_reset", "Password reset"


class OTPChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="otp_challenges",
    )
    purpose = models.CharField(max_length=32, choices=OTPPurpose.choices)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_otp_challenge"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "purpose", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.email} · {self.purpose}"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self):
        return self.consumed_at is not None

    @property
    def is_usable(self):
        return (
            not self.is_consumed
            and not self.is_expired
            and self.attempt_count < self.max_attempts
        )


class AuthEventType(models.TextChoices):
    REGISTERED = "registered", "Registered"
    EMAIL_VERIFIED = "email_verified", "Email verified"
    OTP_SENT = "otp_sent", "OTP sent"
    OTP_FAILED = "otp_failed", "OTP failed"
    LOGIN_SUCCESS = "login_success", "Login success"
    LOGIN_FAILED = "login_failed", "Login failed"
    FIRST_LOGIN_COMPLETED = "first_login_completed", "First login completed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested", "Password reset requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed", "Password reset completed"
    PASSWORD_CHANGED = "password_changed", "Password changed"
    LOGOUT = "logout", "Logout"
    ACCOUNT_LOCKED = "account_locked", "Account locked"


class AuthEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="auth_events",
        null=True,
        blank=True,
    )
    event_type = models.CharField(max_length=40, choices=AuthEventType.choices)
    email = models.EmailField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_auth_event"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} · {self.email or self.user_id}"


class MembershipRole(models.TextChoices):
    ORG_ADMIN = "org_admin", "Organization admin"
    REVIEWER = "reviewer", "Reviewer"
    RESPONDENT = "respondent", "Respondent"


class MembershipStatus(models.TextChoices):
    INVITED = "invited", "Invited"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class PlatformAdmin(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="platform_admin",
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_platform_admins",
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_admins"

    def __str__(self):
        return self.user.email


class OrganizationMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=MembershipRole.choices)
    respondent = models.ForeignKey(
        "core.Respondent",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="memberships",
    )
    job_title = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=MembershipStatus.choices,
        default=MembershipStatus.INVITED,
    )
    invited_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_membership_invites",
    )
    invited_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "organization_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="organization_memberships_org_user_uniq",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(role__in=[MembershipRole.ORG_ADMIN, MembershipRole.REVIEWER]),
                name="memberships_one_staff_org_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=MembershipRole.values),
                name="organization_memberships_role_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=MembershipStatus.values),
                name="organization_memberships_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(role=MembershipRole.RESPONDENT, respondent__isnull=False)
                    | (
                        ~models.Q(role=MembershipRole.RESPONDENT)
                        & models.Q(respondent__isnull=True)
                    )
                ),
                name="membership_respondent_role_consistency",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="ix_memberships_user"),
            models.Index(fields=["organization", "role"], name="ix_memberships_org_role"),
        ]

    def __str__(self):
        return f"{self.user.email} · {self.organization} · {self.role}"


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    refresh_token_hash = models.TextField(unique=True)
    active_organization = models.ForeignKey(
        "core.Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_sessions",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_sessions"
        indexes = [
            models.Index(
                fields=["user"],
                name="ix_sessions_user",
                condition=models.Q(revoked_at__isnull=True),
            ),
        ]

    def __str__(self):
        return f"{self.user.email} session"


class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token_hash = models.TextField(unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "password_reset_tokens"

    def __str__(self):
        return f"reset token · {self.user.email}"
