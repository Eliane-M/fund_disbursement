from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.serializers import (
    LoginSerializer,
    LogoutSerializer,
    OTPVerifySerializer,
    PasswordChangeSerializer,
    PasswordForgotSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    ResendOTPSerializer,
    UserSerializer,
)
from accounts.services import (
    change_password,
    issue_tokens,
    login_user,
    logout_user,
    register_user,
    request_password_reset,
    resend_otp,
    reset_password,
    verify_email,
    verify_first_login,
)
from accounts.throttles import AuthRateThrottle, AuthenticatedUserRateThrottle, OTPRateThrottle


GENERIC_OTP_SENT = "If an account exists for this email, a one-time code has been sent."


def _auth_payload(user, tokens):
    return {
        "user": UserSerializer(user).data,
        **tokens,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    register_user(**serializer.validated_data, request=request)
    return Response(
        {
            "detail": "Account created. Check your email for a verification code.",
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRateThrottle])
def verify_email_view(request):
    serializer = OTPVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    verify_email(**serializer.validated_data, request=request)
    return Response({"detail": "Email verified. You can now sign in."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = login_user(**serializer.validated_data, request=request)
    if result.get("otp_required"):
        return Response(
            {
                "detail": result["detail"],
                "code": result["code"],
                "otp_required": True,
            }
        )
    return Response(_auth_payload(result["user"], result["tokens"]))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRateThrottle])
def verify_first_login_view(request):
    serializer = OTPVerifySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = verify_first_login(**serializer.validated_data, request=request)
    return Response(_auth_payload(user, issue_tokens(user)))


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRateThrottle])
def resend_otp_view(request):
    serializer = ResendOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    resend_otp(**serializer.validated_data, request=request)
    return Response({"detail": GENERIC_OTP_SENT})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRateThrottle])
def password_forgot(request):
    serializer = PasswordForgotSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    request_password_reset(**serializer.validated_data, request=request)
    return Response({"detail": GENERIC_OTP_SENT})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRateThrottle])
def password_reset(request):
    serializer = PasswordResetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    reset_password(**serializer.validated_data, request=request)
    return Response({"detail": "Password updated. You can now sign in."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([AuthenticatedUserRateThrottle])
def password_change(request):
    serializer = PasswordChangeSerializer(
        data=request.data,
        context={"user": request.user},
    )
    serializer.is_valid(raise_exception=True)
    change_password(user=request.user, request=request, **serializer.validated_data)
    return Response({"detail": "Password changed successfully."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    serializer = LogoutSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    logout_user(
        refresh_token=serializer.validated_data["refresh"],
        user=request.user,
        request=request,
    )
    return Response({"detail": "Signed out successfully."})


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def me(request):
    if request.method == "PATCH":
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    return Response(UserSerializer(request.user).data)


token_refresh = TokenRefreshView.as_view()
