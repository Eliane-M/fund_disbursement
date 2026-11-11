from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from accounts.models import OTPPurpose

OTP_EMAIL_CONFIG = {
    OTPPurpose.EMAIL_VERIFICATION: {
        "subject": "Verify your Fund Disbursement email",
        "template": "accounts/emails/email_verification",
    },
    OTPPurpose.FIRST_LOGIN: {
        "subject": "Your first-login security code",
        "template": "accounts/emails/first_login",
    },
    OTPPurpose.PASSWORD_RESET: {
        "subject": "Reset your Fund Disbursement password",
        "template": "accounts/emails/password_reset",
    },
}


def send_otp_email(user, purpose, code):
    config = OTP_EMAIL_CONFIG[purpose]
    context = {
        "user": user,
        "code": code,
        "minutes": settings.OTP_TTL_MINUTES,
        "site_name": settings.SITE_NAME,
    }
    text_body = render_to_string(f"{config['template']}.txt", context)
    html_body = render_to_string(f"{config['template']}.html", context)

    message = EmailMultiAlternatives(
        subject=config["subject"],
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(using="default")


def send_password_reset_by_admin_email(user, actor, temp_password):
    context = {
        "user": user,
        "actor_name": actor.full_name if actor else "An admin",
        "temp_password": temp_password,
        "site_name": settings.SITE_NAME,
        "login_url": settings.FRONTEND_LOGIN_URL,
    }
    text_body = render_to_string("accounts/emails/password_reset_by_admin.txt", context)
    html_body = render_to_string("accounts/emails/password_reset_by_admin.html", context)

    message = EmailMultiAlternatives(
        subject=f"Your {settings.SITE_NAME} password was reset",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(using="default")


def send_welcome_email(user, organization, inviter, temp_password):
    context = {
        "user": user,
        "organization_name": organization.name,
        "inviter_name": inviter.full_name if inviter else "An admin",
        "temp_password": temp_password,
        "site_name": settings.SITE_NAME,
        "login_url": settings.FRONTEND_LOGIN_URL,
    }
    text_body = render_to_string("accounts/emails/welcome.txt", context)
    html_body = render_to_string("accounts/emails/welcome.html", context)

    message = EmailMultiAlternatives(
        subject=f"You've been added to {organization.name}",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(using="default")
