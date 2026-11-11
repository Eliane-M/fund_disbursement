import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.emails import send_otp_email, send_password_reset_by_admin_email, send_welcome_email
from accounts.models import (
    AuthEvent,
    AuthEventType,
    MembershipRole,
    OrganizationMembership,
    OTPChallenge,
    OTPPurpose,
)

User = get_user_model()


def get_client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_user_agent(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:512]


def record_auth_event(event_type, *, user=None, email="", request=None, metadata=None):
    AuthEvent.objects.create(
        user=user,
        event_type=event_type,
        email=email or (user.email if user else ""),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        metadata=metadata or {},
    )


def generate_otp_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code):
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def codes_match(plain_code, code_hash):
    return hmac.compare_digest(hash_otp_code(plain_code), code_hash)


def issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["email"] = user.email
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def lock_account(user):
    user.failed_login_attempts = user.failed_login_attempts + 1
    if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
        user.locked_until = timezone.now() + timedelta(
            minutes=settings.LOGIN_LOCKOUT_MINUTES
        )
        user.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])
        return True
    user.save(update_fields=["failed_login_attempts", "updated_at"])
    return False


def clear_lockout(user):
    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until", "updated_at"])


def ensure_account_available(user):
    if not user.is_active:
        raise PermissionDenied("This account is disabled.")
    if user.is_locked():
        raise PermissionDenied(
            "This account is temporarily locked after too many failed sign-in attempts."
        )


def get_active_otp(user, purpose):
    return (
        OTPChallenge.objects.filter(
            user=user,
            purpose=purpose,
            consumed_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )


def create_and_send_otp(user, purpose, request=None):
    existing = get_active_otp(user, purpose)
    if existing and not existing.is_expired:
        wait_until = existing.created_at + timedelta(seconds=settings.OTP_RESEND_SECONDS)
        remaining = int((wait_until - timezone.now()).total_seconds())
        if remaining > 0:
            raise ValidationError(
                {
                    "detail": f"Please wait {remaining} seconds before requesting a new code."
                }
            )

    OTPChallenge.objects.filter(
        user=user,
        purpose=purpose,
        consumed_at__isnull=True,
    ).update(consumed_at=timezone.now())

    code = generate_otp_code()
    OTPChallenge.objects.create(
        user=user,
        purpose=purpose,
        code_hash=hash_otp_code(code),
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_TTL_MINUTES),
        max_attempts=settings.OTP_MAX_ATTEMPTS,
        request_ip=get_client_ip(request),
    )
    send_otp_email(user, purpose, code)
    record_auth_event(
        AuthEventType.OTP_SENT,
        user=user,
        request=request,
        metadata={"purpose": purpose},
    )
    return code


def verify_otp(user, purpose, code, request=None):
    challenge = get_active_otp(user, purpose)
    if challenge is None:
        record_auth_event(
            AuthEventType.OTP_FAILED,
            user=user,
            request=request,
            metadata={"purpose": purpose, "reason": "not_found"},
        )
        raise ValidationError({"otp": "No active code was found. Request a new one."})

    if challenge.is_expired:
        challenge.consumed_at = timezone.now()
        challenge.save(update_fields=["consumed_at"])
        record_auth_event(
            AuthEventType.OTP_FAILED,
            user=user,
            request=request,
            metadata={"purpose": purpose, "reason": "expired"},
        )
        raise ValidationError({"otp": "This code has expired. Request a new one."})

    challenge.attempt_count += 1
    if not codes_match(code, challenge.code_hash):
        updates = ["attempt_count"]
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.consumed_at = timezone.now()
            updates.append("consumed_at")
        challenge.save(update_fields=updates)
        record_auth_event(
            AuthEventType.OTP_FAILED,
            user=user,
            request=request,
            metadata={"purpose": purpose, "reason": "mismatch"},
        )
        raise ValidationError({"otp": "The code you entered is invalid."})

    challenge.consumed_at = timezone.now()
    challenge.save(update_fields=["attempt_count", "consumed_at"])
    return challenge


@transaction.atomic
def register_user(*, email, password, first_name, last_name, phone_number="", request=None):
    normalized = User.objects.normalize_email(email)
    existing = User.objects.filter(email=normalized).first()
    if existing:
        if existing.is_email_verified:
            raise ValidationError({"email": "An account with this email already exists."})
        existing.first_name = first_name
        existing.last_name = last_name
        existing.phone_number = phone_number
        existing.set_password(password)
        existing.save(
            update_fields=[
                "first_name",
                "last_name",
                "phone_number",
                "password",
                "updated_at",
            ]
        )
        create_and_send_otp(existing, OTPPurpose.EMAIL_VERIFICATION, request=request)
        return existing

    user = User.objects.create_user(
        email=normalized,
        password=password,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
    )
    record_auth_event(AuthEventType.REGISTERED, user=user, request=request)
    create_and_send_otp(user, OTPPurpose.EMAIL_VERIFICATION, request=request)
    return user


@transaction.atomic
def verify_email(*, email, otp, request=None):
    user = User.objects.filter(email=User.objects.normalize_email(email)).first()
    if user is None:
        raise ValidationError({"otp": "The code you entered is invalid."})
    if user.is_email_verified:
        raise ValidationError({"detail": "This email is already verified."})

    verify_otp(user, OTPPurpose.EMAIL_VERIFICATION, otp, request=request)
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified", "updated_at"])
    record_auth_event(AuthEventType.EMAIL_VERIFIED, user=user, request=request)
    return user


def resend_otp(*, email, purpose, request=None):
    user = User.objects.filter(email=User.objects.normalize_email(email)).first()
    if user is None:
        return None

    if purpose == OTPPurpose.EMAIL_VERIFICATION and user.is_email_verified:
        raise ValidationError({"detail": "This email is already verified."})
    if purpose == OTPPurpose.FIRST_LOGIN and not user.is_first_login:
        raise ValidationError({"detail": "First-login verification is no longer required."})
    if purpose == OTPPurpose.FIRST_LOGIN and not user.is_email_verified:
        raise ValidationError({"detail": "Verify your email before completing first login."})

    create_and_send_otp(user, purpose, request=request)
    return user


def login_user(*, email, password, request=None):
    normalized = User.objects.normalize_email(email)
    user = User.objects.filter(email=normalized).first()
    dummy = User()
    dummy.set_password(password)

    if user is None:
        dummy.check_password(password)
        record_auth_event(
            AuthEventType.LOGIN_FAILED,
            email=normalized,
            request=request,
            metadata={"reason": "unknown_user"},
        )
        raise AuthenticationFailed("Invalid email or password.")

    ensure_account_available(user)

    if not user.check_password(password):
        locked = lock_account(user)
        record_auth_event(
            AuthEventType.LOGIN_FAILED,
            user=user,
            request=request,
            metadata={"reason": "bad_password"},
        )
        if locked:
            record_auth_event(AuthEventType.ACCOUNT_LOCKED, user=user, request=request)
            raise PermissionDenied(
                "This account is temporarily locked after too many failed sign-in attempts."
            )
        raise AuthenticationFailed("Invalid email or password.")

    if not user.is_email_verified:
        raise PermissionDenied("Verify your email before signing in.")

    clear_lockout(user)

    if user.is_first_login:
        existing = get_active_otp(user, OTPPurpose.FIRST_LOGIN)
        if existing is None or not existing.is_usable:
            create_and_send_otp(user, OTPPurpose.FIRST_LOGIN, request=request)
        return {
            "otp_required": True,
            "detail": "A one-time code was sent to your email to complete your first login.",
            "code": "otp_required",
        }

    record_auth_event(AuthEventType.LOGIN_SUCCESS, user=user, request=request)
    return {
        "otp_required": False,
        "tokens": issue_tokens(user),
        "user": user,
    }


@transaction.atomic
def verify_first_login(*, email, otp, request=None):
    user = User.objects.filter(email=User.objects.normalize_email(email)).first()
    if user is None:
        raise ValidationError({"otp": "The code you entered is invalid."})

    ensure_account_available(user)
    if not user.is_email_verified:
        raise PermissionDenied("Verify your email before signing in.")
    if not user.is_first_login:
        raise ValidationError({"detail": "First-login verification is no longer required."})

    verify_otp(user, OTPPurpose.FIRST_LOGIN, otp, request=request)
    # is_first_login stays True until they set their own password via
    # set_initial_password — it doubles as "activation isn't complete yet".
    record_auth_event(AuthEventType.FIRST_LOGIN_COMPLETED, user=user, request=request)
    record_auth_event(AuthEventType.LOGIN_SUCCESS, user=user, request=request)
    return user


def set_initial_password(*, user, new_password, request=None):
    if not user.is_first_login:
        raise ValidationError({"detail": "Your account is already activated."})

    user.set_password(new_password)
    user.is_first_login = False
    user.password_changed_at = timezone.now()
    user.save(update_fields=["password", "is_first_login", "password_changed_at", "updated_at"])
    record_auth_event(AuthEventType.PASSWORD_CHANGED, user=user, request=request)
    return user


def request_password_reset(*, email, request=None):
    user = User.objects.filter(email=User.objects.normalize_email(email)).first()
    if user is None or not user.is_active:
        return None

    create_and_send_otp(user, OTPPurpose.PASSWORD_RESET, request=request)
    record_auth_event(AuthEventType.PASSWORD_RESET_REQUESTED, user=user, request=request)
    return user


@transaction.atomic
def reset_password(*, email, otp, new_password, request=None):
    user = User.objects.filter(email=User.objects.normalize_email(email)).first()
    if user is None:
        raise ValidationError({"otp": "The code you entered is invalid."})

    verify_otp(user, OTPPurpose.PASSWORD_RESET, otp, request=request)
    user.set_password(new_password)
    user.password_changed_at = timezone.now()
    user.failed_login_attempts = 0
    user.locked_until = None
    user.save(
        update_fields=[
            "password",
            "password_changed_at",
            "failed_login_attempts",
            "locked_until",
            "updated_at",
        ]
    )
    record_auth_event(AuthEventType.PASSWORD_RESET_COMPLETED, user=user, request=request)
    return user


def change_password(*, user, current_password, new_password, request=None):
    if not user.check_password(current_password):
        raise ValidationError({"current_password": "Current password is incorrect."})
    if user.check_password(new_password):
        raise ValidationError(
            {"new_password": "The new password must be different from the current password."}
        )

    user.set_password(new_password)
    user.password_changed_at = timezone.now()
    user.save(update_fields=["password", "password_changed_at", "updated_at"])
    record_auth_event(AuthEventType.PASSWORD_CHANGED, user=user, request=request)
    return user


STAFF_ROLES = (MembershipRole.ORG_ADMIN, MembershipRole.REVIEWER)


def assert_role_available(user, role, *, exclude_membership=None):
    """Staff (org admins and reviewers) may belong to only one organization;
    respondents may belong to any number of organizations."""
    if user is None or role not in STAFF_ROLES:
        return

    existing = OrganizationMembership.objects.filter(user=user, role__in=STAFF_ROLES).select_related(
        "organization"
    )
    if exclude_membership is not None:
        existing = existing.exclude(pk=exclude_membership.pk)
    other = existing.first()
    if other is not None:
        article = "an" if other.role == MembershipRole.ORG_ADMIN else "a"
        raise ValidationError(
            {
                "role": (
                    f"This person is already {article} {MembershipRole(other.role).label.lower()} of "
                    f"{other.organization.name}. Staff can belong to only one organization."
                )
            }
        )


def _create_invited_user(email, first_name="", last_name=""):
    """Create an account with a temporary password; the first-login OTP +
    set-password flow takes over when they sign in. Returns (user, temp_password)."""
    temp_password = secrets.token_urlsafe(9)
    user = User.objects.create_user(
        email=email,
        password=temp_password,
        first_name=first_name or "",
        last_name=last_name or "",
        is_email_verified=True,
    )
    record_auth_event(AuthEventType.REGISTERED, user=user, request=None, metadata={"invited": True})
    return user, temp_password


def ensure_respondent_account(*, respondent, invited_by):
    """Make sure the respondent's primary contact can sign in as a respondent
    of the respondent's organization. Returns (user, temp_password), where
    temp_password is None if the account already existed."""
    from accounts.models import MembershipStatus

    email = User.objects.normalize_email(respondent.primary_contact_email)
    user = User.objects.filter(email=email).first()
    temp_password = None

    if user is None:
        first_name, _, last_name = (respondent.primary_contact_name or respondent.name).strip().partition(" ")
        user, temp_password = _create_invited_user(email, first_name, last_name)

    if not OrganizationMembership.objects.filter(organization_id=respondent.organization_id, user=user).exists():
        OrganizationMembership.objects.create(
            organization_id=respondent.organization_id,
            user=user,
            role=MembershipRole.RESPONDENT,
            respondent=respondent,
            status=MembershipStatus.ACTIVE,
            invited_by=invited_by,
            accepted_at=timezone.now(),
        )
    return user, temp_password


def invite_member(*, organization, email, role, invited_by, first_name="", last_name="", respondent=None):
    """Add a user to an organization with a role.

    If no account exists for the email yet, one is created with a generated
    temporary password and `is_first_login=True` — the existing login ->
    first-login-OTP flow (already built) handles activation. The temporary
    password is emailed directly to the invited user (never returned to the
    inviter); on first sign-in they verify an OTP and are then required to
    set their own password. Returns (membership, is_new_account).
    """
    from accounts.models import MembershipStatus, OrganizationMembership

    normalized = User.objects.normalize_email(email)
    user = User.objects.filter(email=normalized).first()
    is_new_account = user is None
    assert_role_available(user, role)

    if user is None:
        user, temp_password = _create_invited_user(normalized, first_name, last_name)
        send_welcome_email(user, organization, invited_by, temp_password)

    if OrganizationMembership.objects.filter(organization=organization, user=user).exists():
        raise ValidationError({"email": "This person is already a member of the organization."})

    membership = OrganizationMembership.objects.create(
        organization=organization,
        user=user,
        role=role,
        respondent=respondent,
        status=MembershipStatus.ACTIVE,
        invited_by=invited_by,
        accepted_at=timezone.now(),
    )
    return membership, is_new_account


def reset_password_by_admin(*, user, actor, request=None):
    """An admin-initiated password reset: generate a new temp password, force
    re-activation through the first-login OTP + set-password flow (same as a
    brand-new invite), and email the user directly — the admin never sees it.
    """
    temp_password = secrets.token_urlsafe(9)
    user.set_password(temp_password)
    user.is_first_login = True
    user.save(update_fields=["password", "is_first_login", "updated_at"])
    send_password_reset_by_admin_email(user, actor, temp_password)
    record_auth_event(AuthEventType.PASSWORD_RESET_REQUESTED, user=user, request=request, metadata={"by_admin": True})
    return user


def logout_user(*, refresh_token, user=None, request=None):
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except Exception as exc:
        raise ValidationError({"refresh": "Invalid or expired refresh token."}) from exc

    record_auth_event(AuthEventType.LOGOUT, user=user, request=request)
