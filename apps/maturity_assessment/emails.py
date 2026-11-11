from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date


def send_assessment_invitation_email(invitation, temp_password=None):
    respondent = invitation.respondent
    due_date = invitation.due_date
    if isinstance(due_date, str):
        due_date = parse_date(due_date)

    context = {
        "contact_name": respondent.primary_contact_name or respondent.name,
        "respondent_name": respondent.name,
        "assessment_name": invitation.assessment.name,
        "organization_name": invitation.organization.name,
        "inviter_name": invitation.invited_by.full_name if invitation.invited_by else "An admin",
        "due_date": due_date,
        "temp_password": temp_password,
        "site_name": settings.SITE_NAME,
        "login_url": settings.FRONTEND_LOGIN_URL,
    }
    text_body = render_to_string("maturity_assessment/emails/assessment_invitation.txt", context)
    html_body = render_to_string("maturity_assessment/emails/assessment_invitation.html", context)

    message = EmailMultiAlternatives(
        subject=f"{invitation.organization.name} invited you to complete {invitation.assessment.name}",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[respondent.primary_contact_email],
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(using="default")


def send_assessment_submitted_email(invitation, report, pending_review, recipients):
    context = {
        "respondent_name": invitation.respondent.name,
        "assessment_name": invitation.assessment.name,
        "organization_name": invitation.organization.name,
        "overall_score": report.overall_score,
        "maturity_band_label": report.maturity_band_label,
        "pending_review": pending_review,
        "site_name": settings.SITE_NAME,
        "login_url": settings.FRONTEND_LOGIN_URL,
    }
    text_body = render_to_string("maturity_assessment/emails/assessment_submitted.txt", context)
    html_body = render_to_string("maturity_assessment/emails/assessment_submitted.html", context)

    message = EmailMultiAlternatives(
        subject=f"{invitation.respondent.name} submitted {invitation.assessment.name}",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    message.attach_alternative(html_body, "text/html")
    return message.send(using="default")
