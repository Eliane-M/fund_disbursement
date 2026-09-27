from django.urls import path

from accounts import views

urlpatterns = [
    path("register/", views.register, name="auth-register"),
    path("verify-email/", views.verify_email_view, name="auth-verify-email"),
    path("login/", views.login, name="auth-login"),
    path("verify-first-login/", views.verify_first_login_view, name="auth-verify-first-login"),
    path("resend-otp/", views.resend_otp_view, name="auth-resend-otp"),
    path("password/forgot/", views.password_forgot, name="auth-password-forgot"),
    path("password/reset/", views.password_reset, name="auth-password-reset"),
    path("password/change/", views.password_change, name="auth-password-change"),
    path("token/refresh/", views.token_refresh, name="auth-token-refresh"),
    path("logout/", views.logout, name="auth-logout"),
    path("me/", views.me, name="auth-me"),
]
