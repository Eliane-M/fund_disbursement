from django.urls import path

from apps.core import views

urlpatterns = [
    path("organizations/", views.organizations_list, name="core-organizations"),
    path("organizations/<slug:slug>/", views.organization_detail, name="core-organization-detail"),
    path("respondents/", views.RespondentListCreateView.as_view(), name="core-respondents"),
    path("respondents/<uuid:pk>/", views.RespondentDetailView.as_view(), name="core-respondent-detail"),
    path(
        "organizations/<uuid:organization_id>/members/",
        views.organization_members,
        name="core-organization-members",
    ),
    path("memberships/<uuid:pk>/", views.membership_detail, name="core-membership-detail"),
    path("notifications/", views.notifications_list, name="core-notifications"),
    path("notifications/<uuid:pk>/read/", views.notification_mark_read, name="core-notification-read"),
]
