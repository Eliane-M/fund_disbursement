from django.urls import path

from apps.platform import views

urlpatterns = [
    path("organizations/", views.organizations_list, name="platform-organizations"),
    path("organizations/<uuid:pk>/", views.organization_detail, name="platform-organization-detail"),
    path("organizations/<uuid:pk>/members/", views.organization_members, name="platform-organization-members"),
    path("users/", views.users_list, name="platform-users"),
    path("users/<uuid:pk>/", views.user_detail, name="platform-user-detail"),
    path("users/<uuid:pk>/reset-password/", views.reset_user_password, name="platform-user-reset-password"),
    path("users/<uuid:pk>/platform-admin/", views.toggle_platform_admin, name="platform-toggle-admin"),
]
