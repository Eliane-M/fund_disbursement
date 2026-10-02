from django.urls import path

from apps.maturity_assessment import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="assessment-dashboard"),
    path("categories/", views.CategoryListCreateView.as_view(), name="assessment-categories"),
    path("categories/<uuid:pk>/", views.CategoryDetailView.as_view(), name="assessment-category-detail"),
    path("assessments/", views.AssessmentListCreateView.as_view(), name="assessments"),
    path("assessments/<uuid:pk>/", views.AssessmentDetailView.as_view(), name="assessment-detail"),
    path("assessments/<uuid:pk>/publish/", views.assessment_publish, name="assessment-publish"),
    path("assessments/<uuid:pk>/archive/", views.assessment_archive, name="assessment-archive"),
    path(
        "assessments/<uuid:assessment_id>/capabilities/",
        views.CapabilityListCreateView.as_view(),
        name="assessment-capabilities",
    ),
    path("capabilities/<uuid:pk>/", views.CapabilityDetailView.as_view(), name="capability-detail"),
    path(
        "capabilities/<uuid:capability_id>/sub-capabilities/",
        views.SubCapabilityListCreateView.as_view(),
        name="capability-sub-capabilities",
    ),
    path("sub-capabilities/<uuid:pk>/", views.SubCapabilityDetailView.as_view(), name="sub-capability-detail"),
    path(
        "assessments/<uuid:assessment_id>/questions/",
        views.QuestionListCreateView.as_view(),
        name="assessment-questions",
    ),
    path("questions/<uuid:pk>/", views.QuestionDetailView.as_view(), name="question-detail"),
    path(
        "assessments/<uuid:assessment_id>/maturity-bands/",
        views.MaturityBandListCreateView.as_view(),
        name="assessment-maturity-bands",
    ),
    path("maturity-bands/<uuid:pk>/", views.MaturityBandDetailView.as_view(), name="maturity-band-detail"),
    path(
        "capabilities/<uuid:capability_id>/recommendations/",
        views.RecommendationListCreateView.as_view(),
        name="capability-recommendations",
    ),
    path("recommendations/<uuid:pk>/", views.RecommendationDetailView.as_view(), name="recommendation-detail"),
    path(
        "assessments/<uuid:assessment_id>/invitations/",
        views.InvitationListCreateView.as_view(),
        name="assessment-invitations",
    ),
    path("reports/", views.ReportListView.as_view(), name="reports"),
    path("reports/<uuid:pk>/", views.ReportDetailView.as_view(), name="report-detail"),
]
