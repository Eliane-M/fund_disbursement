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
    path("my/assessments/", views.MyInvitationListView.as_view(), name="my-assessments"),
    path("my/reports/", views.MyReportListView.as_view(), name="my-reports"),
    path("my/reports/<uuid:pk>/", views.my_report_detail, name="my-report-detail"),
    path("my/assessments/<uuid:pk>/", views.my_assessment_detail, name="my-assessment-detail"),
    path("my/assessments/<uuid:pk>/answers/", views.my_assessment_answers, name="my-assessment-answers"),
    path("my/assessments/<uuid:pk>/submit/", views.my_assessment_submit, name="my-assessment-submit"),
    path("review-queue/", views.assessment_review_queue, name="assessment-review-queue"),
    path(
        "invitations/<uuid:pk>/pending-responses/",
        views.invitation_pending_responses,
        name="invitation-pending-responses",
    ),
    path("responses/<uuid:pk>/score/", views.grade_response, name="response-score"),
    path("reports/", views.ReportListView.as_view(), name="reports"),
    path("reports/<uuid:pk>/", views.ReportDetailView.as_view(), name="report-detail"),
]
